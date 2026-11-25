

from decimal import Decimal

from modules.exams.services import get_academic_standing


def check_eligibility(student, job_role, standing=None, ctx=None):
  
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

    # A role with no rule set is open to every final-year student (the
    # college rules below still apply). Deliberate: a company with no cutoff
    # - "everyone can apply" - is simply a role with no limits filled in.
    if rule is None:
        rule = _EmptyRule()

    # ---------------- COLLEGE RULE: FINAL YEAR ONLY ----------------
    # Checked for every role, before anything the company asked for.
    # ctx: optional dict shared across many checks in one refresh, so the
    # policy, each course's final year and each student's best offer are
    # read once - not once per student per role. The rules don't change.
    ctx = {} if ctx is None else ctx
    if "policy" not in ctx:
        from .tiers import current_policy
        ctx["policy"] = current_policy()
    policy = ctx["policy"]
    if policy.final_year_only:
        final_year = _final_year_of(student, ctx)
        if final_year is None:
            record("Final year", "Final-year student", "Year or course not set", False,
                   "Your year or course is not set in your profile. Please contact the office.")
        else:
            passed = student.year == final_year
            record("Final year", f"Year {final_year}", f"Year {student.year}", passed,
                   "" if passed else "Placement is open to final-year students only.")

    # ---------------- PRIOR ACADEMICS ----------------
    # 10th / 12th / diploma marks matter ONLY when this role sets a limit on
    # them (or refuses lateral entry, which needs the entry type). A company
    # that only asks for CGPA or arrears - or nothing at all - must not block
    # a student whose marksheet the coordinator hasn't verified yet. CGPA and
    # arrears come from published results, which are official already.
    needs_prior = (
        rule.min_tenth_percent is not None
        or rule.min_twelfth_percent is not None
        or not rule.allow_lateral_entry
    )
    prior = getattr(student, "prior_academics", None)
    if needs_prior:
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

        # UNVERIFIED MARKS ARE NEVER ELIGIBLE (when the role uses them).
        # Students type their own marks. Without this check anyone enters 95%
        # and applies, and the coordinator's verification step means nothing.
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
        record("10th", "No minimum", prior.tenth_percent if prior else "—", True)

    # ---------------- 12TH / DIPLOMA ----------------
    # qualifying_percent is 12th for a regular student and diploma for a
    # lateral entry one. That rule lives in the model property alone -- it is
    # never re-implemented here.
    label = "Diploma" if (prior and prior.is_lateral_entry) else "12th"
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
        record(label, "No minimum", prior.qualifying_percent if prior else "—", True)

    # ---------------- LATERAL ENTRY ----------------
    if not rule.allow_lateral_entry and prior.is_lateral_entry:
        record("Entry type", "Regular entry only", "Lateral entry", False,
               "This company does not accept lateral entry students.")
    else:
        record("Entry type", "Any" if rule.allow_lateral_entry else "Regular entry only",
               ("Lateral" if prior.is_lateral_entry else "Regular") if prior else "—", True)


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
        from modules.placement.models import Offer

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

    # ---------------- COLLEGE RULE: SAME OR HIGHER PACKAGE ----------------
    # A student who has ACCEPTED an offer may apply only to roles paying the
    # same or more. Unaccepted offers don't count. A role with no package
    # entered can't be shown to be higher, so it stays closed to them.
    if policy.higher_package_only:
        best = _best_offer(student, ctx)
        if best is None or best.package_lpa is None:
            record("Current offer", "Any (not placed yet)", "No accepted offer", True)
        else:
            company = best.application.job_role.drive.company.name
            role_pkg = job_role.package_lpa
            passed = role_pkg is not None and Decimal(str(role_pkg)) >= Decimal(str(best.package_lpa))
            if passed:
                reason = ""
            elif role_pkg is None:
                reason = (f"You have accepted a {best.package_lpa} LPA offer from {company}. "
                          f"This role has no package listed, so it can't be shown to be higher.")
            else:
                reason = (f"You have accepted a {best.package_lpa} LPA offer from {company}. "
                          f"Only roles paying {best.package_lpa} LPA or more are open to you.")
            record("Current offer",
                   f"{best.package_lpa} LPA or more",
                   f"{role_pkg} LPA role" if role_pkg is not None else "Package not listed",
                   passed, reason)


    # ---------------- OFFER TIER (dream / super dream) ----------------
    # College-wide rule from PlacementPolicy, on top of the role's own cap.
    from .tiers import tier_check
    tier = tier_check(student, job_role, policy, best=_best_offer(student, ctx)) if policy.tiers_enabled else None
    if tier is not None:
        record("Offer tier", tier["required"], tier["actual"], tier["passed"], tier["reason"])

    eligible = all(c["passed"] for c in checks)

    return {"eligible": eligible, "checks": checks, "blockers": blockers}


# ===================== NO-RULE FALLBACK =====================
class _EmptyRule:
    """
    Stands in for a job role whose eligibility has not been set up.

    Everything is None (no limit), so only the college rules apply
    (final year, same-or-higher package, offer tiers).
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


# ===================== FINAL YEAR =====================
def _best_offer(student, ctx):
    """The student's best ACCEPTED offer, read once per student per ctx."""
    cache = ctx.setdefault("best_offer", {})
    if student.id not in cache:
        from .tiers import best_accepted_offer
        cache[student.id] = best_accepted_offer(student)
    return cache[student.id]


def _final_year_of(student, ctx=None):
    """
    The last year of the student's course (B.E 4, M.E / MBA 2), from the
    course's Year rows - the same course duration get_passing_year() uses.
    None when the student has no course or year set.
    """
    if not getattr(student, "course_id", None) or not getattr(student, "year", None):
        return None
    cache = (ctx if ctx is not None else {}).setdefault("final_year", {})
    if student.course_id not in cache:
        from django.db.models import Max
        cache[student.course_id] = student.course.years.aggregate(m=Max("year_number"))["m"]
    return cache[student.course_id]

