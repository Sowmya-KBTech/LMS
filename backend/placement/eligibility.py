

from decimal import Decimal

from exams.services import get_academic_standing


def check_eligibility(student, job_role, standing=None):
  
    checks = []
    blockers = []

    def jsonable(value):
        """
        Decimal -> float, so the result can be stored in a JSONField.

        Percentages and CGPA are Decimals by design (float drift would break a
        `>= 60` comparison), but JSON has no Decimal type. Converting HERE
        rather than at each call site means every caller that saves a snapshot
        gets a storable dict -- Application.eligibility_snapshot failed on
        exactly this.
        """
        if isinstance(value, Decimal):
            return float(value)
        return value

    def record(criterion, required, actual, passed, reason=""):
        checks.append({
            "criterion": criterion,
            "required": jsonable(required),
            "actual": jsonable(actual),
            "passed": passed,
            "reason": reason,
        })
        if not passed and reason:
            blockers.append(reason)

    # Eligibility hangs off the ROLE. Reading it from a drive would find no
    # such attribute, fall through to _EmptyRule below, and quietly mark every
    # student eligible for everything.
    rule = getattr(job_role, "eligibility", None)

    # A role with no rule set is open to everyone who has verified marks.
    # Deliberate: an officer who has not filled in the cutoffs yet should see
    # the role working, not silently matching nobody.
    if rule is None:
        rule = _EmptyRule()

    # ---------------- PRIOR ACADEMICS ----------------
    prior = getattr(student, "prior_academics", None)

    if prior is None:
        record(
            "Academic details",
            "Entered and verified",
            "Not entered",
            False,
            "You have not entered your 10th / 12th details yet.",
        )
        # Nothing else about school marks can be judged without this record,
        # so return early rather than reporting a cascade of failures that all
        # have the same single cause.
        return {"eligible": False, "checks": checks, "blockers": blockers}

    # UNVERIFIED MARKS ARE NEVER ELIGIBLE.
    # Students type their own marks. Without this check anyone enters 95% and
    # applies, and the coordinator's verification step means nothing.
    if not prior.verified:
        record(
            "Verification",
            "Verified by coordinator",
            "Waiting for verification",
            False,
            "Your academic details are waiting for your coordinator to verify them.",
        )
    else:
        record("Verification", "Verified by coordinator", "Verified", True)

    # ---------------- CGPA ----------------
    if standing is None:
        standing = get_academic_standing(student)

    cgpa = standing.get("cgpa")
    cgpa_reason = standing.get("cgpa_reason")

    if rule.min_cgpa is not None:
        if cgpa is None:
            # get_cgpa refuses to return a number it cannot trust. Say which
            # case it is rather than showing a bare "not eligible".
            explain = {
                "no_results": "No published results yet.",
                "no_credits": "Credits are missing on some subjects — contact the office.",
                "bad_grade": "A grade could not be read — contact the office.",
            }.get(cgpa_reason, "CGPA is not available.")

            record("CGPA", f"{rule.min_cgpa} or above", "Not available", False, explain)
        else:
            passed = float(cgpa) >= float(rule.min_cgpa)
            record(
                "CGPA",
                f"{rule.min_cgpa} or above",
                cgpa,
                passed,
                "" if passed else f"CGPA {cgpa} is below the required {rule.min_cgpa}.",
            )
    else:
        record("CGPA", "No minimum", cgpa if cgpa is not None else "—", True)

    # ---------------- ARREARS ----------------
    arrears = standing.get("arrears", 0)

    if rule.max_arrears is not None:
        passed = arrears <= rule.max_arrears
        allowed = (
            "No standing arrears"
            if rule.max_arrears == 0
            else f"At most {rule.max_arrears}"
        )
        record(
            "Arrears",
            allowed,
            arrears,
            passed,
            "" if passed else f"You have {arrears} standing arrear(s).",
        )
    else:
        record("Arrears", "No limit", arrears, True)

    # ---------------- 10TH ----------------
    if rule.min_tenth_percent is not None:
        actual = prior.tenth_percent
        if actual is None:
            record("10th", f"{rule.min_tenth_percent}% or above", "Not entered", False,
                   "Your 10th percentage is missing.")
        else:
            passed = float(actual) >= float(rule.min_tenth_percent)
            record(
                "10th",
                f"{rule.min_tenth_percent}% or above",
                f"{actual}%",
                passed,
                "" if passed else f"10th {actual}% is below the required {rule.min_tenth_percent}%.",
            )
    else:
        record("10th", "No minimum", prior.tenth_percent, True)

    # ---------------- 12TH / DIPLOMA ----------------
    # qualifying_percent is 12th for a regular student and diploma for a
    # lateral entry one. That rule lives in the model property alone -- it is
    # never re-implemented here.
    label = "Diploma" if prior.is_lateral_entry else "12th"

    if rule.min_twelfth_percent is not None:
        actual = prior.qualifying_percent
        if actual is None:
            record(label, f"{rule.min_twelfth_percent}% or above", "Not entered", False,
                   f"Your {label} percentage is missing.")
        else:
            passed = float(actual) >= float(rule.min_twelfth_percent)
            record(
                label,
                f"{rule.min_twelfth_percent}% or above",
                f"{actual}%",
                passed,
                "" if passed else f"{label} {actual}% is below the required {rule.min_twelfth_percent}%.",
            )
    else:
        record(label, "No minimum", prior.qualifying_percent, True)

    # ---------------- LATERAL ENTRY ----------------
    if prior.is_lateral_entry and not rule.allow_lateral_entry:
        record("Entry type", "Regular entry only", "Lateral entry", False,
               "This company does not accept lateral entry students.")
    else:
        record("Entry type", "Any", "Lateral" if prior.is_lateral_entry else "Regular", True)

    # ---------------- DEPARTMENT ----------------
    allowed_departments = list(rule.allowed_department_ids())

    if allowed_departments:
        dept = student.department
        passed = bool(dept and dept.id in allowed_departments)
        record(
            "Branch",
            rule.allowed_department_names(),
            dept.name if dept else "None",
            passed,
            "" if passed else "This role is not open to your branch.",
        )
    else:
        record("Branch", "All branches", student.department.name if student.department else "—", True)

    # ---------------- PASSING YEAR ----------------
    if rule.passing_year is not None:
        actual = standing.get("passing_year")
        passed = actual == rule.passing_year
        record(
            "Passing year",
            rule.passing_year,
            actual if actual else "Unknown",
            passed,
            "" if passed else f"This role is for the {rule.passing_year} batch.",
        )
    else:
        record("Passing year", "Any", standing.get("passing_year") or "—", True)

    # ---------------- ALREADY PLACED ----------------
    # A student holding an ACCEPTED offer at or above the cap is done, and the
    # college stops them attending further drives.
    #
    # Only ACCEPTED counts. An unaccepted 7 LPA offer means the student has
    # not decided yet, and blocking them would force a choice the company has
    # not asked for.
    #
    # This replaced a boolean `allow_already_placed`. The real rule is "6 LPA
    # and above", not "placed or not" -- a student on 4 LPA is still looking,
    # one on 7 LPA is done, and a flag cannot tell those apart.
    if rule.placed_package_cap is not None:
        from placement.models import Offer

        best = (
            Offer.objects
            .filter(
                application__student=student,
                status="accepted",
                package_lpa__gte=rule.placed_package_cap,
            )
            .select_related("application__job_role__drive__company")
            .order_by("-package_lpa")
            .first()
        )

        if best:
            company = best.application.job_role.drive.company.name
            record(
                "Already placed",
                f"No accepted offer at {rule.placed_package_cap} LPA or above",
                f"{best.package_lpa} LPA at {company}",
                False,
                f"You have accepted a {best.package_lpa} LPA offer from {company}.",
            )
        else:
            record(
                "Already placed",
                f"Below {rule.placed_package_cap} LPA",
                "Not placed",
                True,
            )
    else:
        record("Already placed", "No limit", "—", True)

    eligible = all(c["passed"] for c in checks)

    return {"eligible": eligible, "checks": checks, "blockers": blockers}


# ===================== NO-RULE FALLBACK =====================
class _EmptyRule:
    """
    Stands in for a job role whose eligibility has not been set up.

    Everything is None (no limit), so only the verification check applies.
    Written as a class rather than scattering `if rule and rule.min_cgpa`
    through the function above -- that pattern is where a missed `if` turns
    into a crash on a half-configured role.
    """
    min_cgpa = None
    max_arrears = None
    min_tenth_percent = None
    min_twelfth_percent = None
    passing_year = None
    allow_lateral_entry = True
    placed_package_cap = None

    def allowed_department_ids(self):
        return []

    def allowed_department_names(self):
        return "All branches"