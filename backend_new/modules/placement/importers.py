"""
Placement import / export (shared engine in core/dataio). Meeting point 2.

  prior_academics  10th / 12th / diploma marks, one row per student
  drive_attendance who attended a drive (one job role)
  offers           offers made for one job role
  round_results    who cleared one selection round

Every importer uses the SAME rules as the placement screens:
  * who may see which students  -> permissions.scope_students_for()
  * what a write does           -> services.mark_drive_attendance(),
                                   services.record_offer(),
                                   services.save_round_result()
so a file can never do something the screen would refuse.
"""
import decimal

from django.utils import timezone

from core.dataio import fields as F
from core.dataio.engine import SKIP, Importer, OptionError, RowError
from core.users.models import PriorAcademics, User

from .models import Application, DriveRound, JobRole
from .permissions import can_manage_placement, can_view_placement_staff, scope_students_for

YES_NO = {"yes": True, "y": True, "true": True, "1": True,
          "no": False, "n": False, "false": False, "0": False}


def parse_decimal(lo, hi, name):
    def _p(text):
        try:
            d = decimal.Decimal(str(text).replace("%", "").strip())
        except (decimal.InvalidOperation, ValueError):
            raise F.CellError(f"'{text}' is not a {name}")
        if not lo <= d <= hi:
            raise F.CellError(f"{name.capitalize()} must be between {lo} and {hi}")
        return d.quantize(decimal.Decimal("0.01"))
    return _p


def _name(s):
    return ((s.get_full_name() or "").strip() or s.username) if s else ""


def _role_option(user, raw):
    try:
        role_id = int(raw.get("job_role") or 0)
    except (TypeError, ValueError):
        role_id = 0
    if not role_id:
        raise OptionError("Choose a job role first.")
    role = JobRole.objects.select_related("drive__company").filter(pk=role_id).first()
    if role is None:
        raise OptionError("Job role not found.", 404)
    return role


def _role_file_name(role, stem):
    if not role:
        return stem
    import re
    company = re.sub(r"[^A-Za-z0-9]+", "-", role.drive.company.name).strip("-")[:30]
    return f"{company}-{stem}"


class _RosterImporter(Importer):
    """Rows are students already on a list (applicants / a round). Matched by roll number."""
    match_column = "roll_number"
    match_label = "roll number"
    modes = ("upsert",)

    def _roster(self, user, options):
        raise NotImplementedError

    def unique_in_file(self):
        return ["roll_number"]

    def _app(self, values, ctx):
        roll = str(values.get("roll_number", "")).strip().lower()
        app = ctx["by_roll"].get(roll)
        if app is None:
            raise F.CellError(f"Roll number '{values.get('roll_number')}' is not on this list "
                              f"(not applied, not in this round, or not a student you manage)")
        return app

    def row_title(self, values, existing):
        return values.get("name", "")

    def prepare(self, user, options=None):
        apps = list(self._roster(user, options))
        return {**options, "apps": apps,
                "by_roll": {a.student.roll_number.strip().lower(): a for a in apps if a.student.roll_number}}


# ===================== PRIOR ACADEMICS =====================
class PriorAcademicsImporter(Importer):
    key = "prior_academics"
    label = "10th and 12th marks"
    description = "10th, 12th and diploma marks for each student (used by placement eligibility)."
    file_stem = "prior-academics"
    match_column = "roll_number"
    match_label = "roll number"
    modes = ("upsert",)

    MARK_FIELDS = ("tenth_percent", "tenth_board", "tenth_year", "is_lateral_entry",
                   "twelfth_percent", "twelfth_board", "twelfth_year",
                   "diploma_percent", "diploma_branch", "diploma_year")

    columns = [
        F.roll_number("always", "The student's roll number."),
        F.Column("name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.Column("tenth_percent", "10th %", "add", "88.40", "0 to 100.", parse_decimal(0, 100, "percentage")),
        F.Column("tenth_board", "10th board", False, "State Board"),
        F.Column("tenth_year", "10th year", False, "2021", "Year of passing.", F.parse_int(1980, 2100, "year")),
        F.Column("is_lateral_entry", "Lateral entry", False, "No",
                 "Yes = joined in 2nd year with a diploma (fill Diploma). No = fill 12th.",
                 F.parse_choice(YES_NO, "answer", "Yes or No")),
        F.Column("twelfth_percent", "12th %", False, "91.25", "Required for regular students.",
                 parse_decimal(0, 100, "percentage")),
        F.Column("twelfth_board", "12th board", False, "State Board"),
        F.Column("twelfth_year", "12th year", False, "2023", "Year of passing.", F.parse_int(1980, 2100, "year")),
        F.Column("diploma_percent", "Diploma %", False, "", "Required for lateral entry students.",
                 parse_decimal(0, 100, "percentage")),
        F.Column("diploma_branch", "Diploma branch", False, ""),
        F.Column("diploma_year", "Diploma year", False, "", "Year of passing.", F.parse_int(1980, 2100, "year")),
        F.Column("verified", "Verified", False, "Yes",
                 "Yes = checked against the marksheet. Blank keeps it as it is - but changed marks "
                 "always need verifying again.",
                 F.parse_choice(YES_NO, "answer", "Yes or No")),
    ]

    def can_use(self, user):
        # officer, super admin, and department coordinators (their department only)
        return can_view_placement_staff(user)

    def _students(self, user):
        return scope_students_for(user, User.objects.filter(role="student"))

    def prepare(self, user, options=None):
        students = list(self._students(user).filter(roll_number__isnull=False))
        return {
            "students": {s.roll_number.strip().lower(): s for s in students if s.roll_number},
            "records": {r.student_id: r for r in PriorAcademics.objects.filter(student__in=students)},
        }

    def _student(self, values, ctx):
        s = ctx["students"].get(str(values.get("roll_number", "")).strip().lower())
        if s is None:
            raise F.CellError(f"Roll number '{values.get('roll_number')}' not found, "
                              f"or not a student you manage")
        return s

    def find_existing(self, values, ctx):
        if "roll_number" not in values:
            return None
        return ctx["records"].get(self._student(values, ctx).id)

    def row_title(self, values, existing):
        return values.get("name", "")

    def check_row(self, values, existing, ctx, user):
        from .serializers import MyAcademicsSerializer

        student = self._student(values, ctx)
        data = {k: values[k] for k in self.MARK_FIELDS if k in values}
        changed = existing is None or any(getattr(existing, k) != v for k, v in data.items())
        verified = values.get("verified")      # True / False / None (= leave as it is)

        if not changed and (verified is None or verified == existing.verified):
            return SKIP

        if data:
            s = MyAcademicsSerializer(existing, data=data, partial=existing is not None)
            if not s.is_valid():
                msgs = []
                for field, errs in s.errors.items():
                    for e in (errs if isinstance(errs, list) else [errs]):
                        msgs.append(str(e) if field == "non_field_errors" else f"{field}: {e}")
                raise RowError(msgs)
        return {"student": student, "data": data, "changed": changed and bool(data), "verified": verified}

    def save_row(self, payload, existing, ctx, user):
        from .serializers import MyAcademicsSerializer

        record = existing
        if payload["data"]:
            s = MyAcademicsSerializer(existing, data=payload["data"], partial=existing is not None)
            s.is_valid(raise_exception=True)
            record = s.save(student=payload["student"]) if existing is None else s.save()

        # verification: the same three fields verify_academics() sets
        verified = payload["verified"]
        if verified is None and payload["changed"] and record.verified:
            verified = False                    # changed marks must be checked again
        if verified is True:
            record.verified, record.verified_by, record.verified_at = True, user, timezone.now()
        elif verified is False:
            record.verified, record.verified_by, record.verified_at = False, None, None
        if verified is not None:
            record.save(update_fields=["verified", "verified_by", "verified_at"])
        return None

    def template_rows(self, user, options):
        # students still missing a record - the ones to chase
        have = set(PriorAcademics.objects.values_list("student_id", flat=True))
        return [[s.roll_number, _name(s)] + [""] * (len(self.columns) - 2)
                for s in self._students(user).filter(roll_number__isnull=False).order_by("roll_number")
                if s.id not in have] or self.template_example()

    def export_queryset(self, user, params, options=None):
        qs = self._students(user).filter(roll_number__isnull=False).select_related("prior_academics")
        if params.get("department"):
            qs = qs.filter(department_id=params["department"])
        return qs.order_by("roll_number")

    def export_row(self, s):
        row = {"roll_number": s.roll_number, "name": _name(s)}
        try:
            r = s.prior_academics
        except PriorAcademics.DoesNotExist:
            return row
        for k in self.MARK_FIELDS:
            v = getattr(r, k)
            row[k] = ("Yes" if v else "No") if k == "is_lateral_entry" else ("" if v is None else v)
        row["verified"] = "Yes" if r.verified else "No"
        return row


# ===================== DRIVE ATTENDANCE =====================
STATUS_PA = {"present": "present", "p": "present", "absent": "absent", "a": "absent", "ab": "absent"}


class DriveAttendanceImporter(_RosterImporter):
    key = "drive_attendance"
    label = "drive attendance"
    description = "Who attended the drive. Present creates the approved on-duty automatically."
    file_stem = "drive-attendance"
    option_keys = ["job_role"]

    columns = [
        F.roll_number("always", "Roll number of a student who applied."),
        F.Column("name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.Column("status", "Status", "always", "P", "P = present, A = absent.",
                 F.parse_choice(STATUS_PA, "status", "P or A")),
        F.Column("remarks", "Remarks", False, "", "Optional, up to 255 characters."),
    ]

    def can_use(self, user):
        return can_view_placement_staff(user)       # officer + coordinators (own dept)

    def resolve_options(self, user, raw):
        return {"role": _role_option(user, raw), "user": user}

    def file_name(self, options):
        return _role_file_name(options.get("role"), "drive-attendance")

    def _roster(self, user, options):
        students = scope_students_for(user, User.objects.filter(role="student"))
        return (Application.objects
                .filter(job_role=options["role"], status="applied", student__in=students)
                .select_related("student", "drive_attendance")
                .order_by("student__roll_number"))

    def find_existing(self, values, ctx):
        if "roll_number" not in values:
            return None
        return getattr(self._app(values, ctx), "drive_attendance", None)

    def check_row(self, values, existing, ctx, user):
        app = self._app(values, ctx)
        remarks = (values.get("remarks") or "")[:255]
        if existing is not None and existing.status == values["status"] and \
                ("remarks" not in values or existing.remarks == remarks):
            return SKIP
        if existing is not None and "remarks" not in values:
            remarks = existing.remarks
        return (app, values["status"], remarks)

    def save_row(self, payload, existing, ctx, user):
        from .services import mark_drive_attendance
        app, status, remarks = payload
        mark_drive_attendance(app, status, remarks, user)
        return None

    def template_rows(self, user, options):
        return [[a.student.roll_number, _name(a.student), "", ""]
                for a in self._roster(user, options) if a.student.roll_number] or self.template_example()

    def export_queryset(self, user, params, options=None):
        return self._roster(user, options)

    def export_row(self, a):
        rec = getattr(a, "drive_attendance", None)
        return {"roll_number": a.student.roll_number, "name": _name(a.student),
                "status": {"present": "P", "absent": "A"}.get(rec.status, "") if rec else "",
                "remarks": rec.remarks if rec else ""}


# ===================== OFFERS =====================
class OfferImporter(_RosterImporter):
    key = "offers"
    label = "offers"
    description = "Offers made for this job role. The student still accepts or declines in their portal."
    file_stem = "offers"
    option_keys = ["job_role"]

    columns = [
        F.roll_number("always", "Roll number of a student who applied."),
        F.Column("name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.Column("package_lpa", "Package (LPA)", False, "4.50",
                 "Lakhs per annum. Blank = the role's advertised package (new offers) or unchanged.",
                 parse_decimal(0, 9999, "package")),
        F.date_col("joining_date", "Joining date", "01-07-2027"),
        F.Column("remarks", "Remarks", False, "", "Optional, up to 255 characters."),
    ]

    def can_use(self, user):
        return can_manage_placement(user)           # only the officer records offers

    def resolve_options(self, user, raw):
        return {"role": _role_option(user, raw)}

    def file_name(self, options):
        return _role_file_name(options.get("role"), "offers")

    def _roster(self, user, options):
        students = scope_students_for(user, User.objects.filter(role="student"))
        return (Application.objects
                .filter(job_role=options["role"], status="applied", student__in=students)
                .select_related("student", "offer")
                .order_by("student__roll_number"))

    def find_existing(self, values, ctx):
        if "roll_number" not in values:
            return None
        return getattr(self._app(values, ctx), "offer", None)

    def check_row(self, values, existing, ctx, user):
        app = self._app(values, ctx)
        package = values.get("package_lpa")
        joining = values.get("joining_date")
        remarks = (values["remarks"][:255]) if "remarks" in values else None
        if existing is not None:
            same = ((package is None or existing.package_lpa == package)
                    and (joining is None or existing.joining_date == joining)
                    and (remarks is None or existing.remarks == remarks))
            if same:
                return SKIP
            if package is None:
                package = existing.package_lpa     # blank = unchanged
        return (app, package, joining, remarks)

    def save_row(self, payload, existing, ctx, user):
        from .services import record_offer
        app, package, joining, remarks = payload
        record_offer(app, ctx["role"], user, package=package, joining_date=joining, remarks=remarks)
        return None

    def template_rows(self, user, options):
        return [[a.student.roll_number, _name(a.student), "", "", ""]
                for a in self._roster(user, options)
                if a.student.roll_number and getattr(a, "offer", None) is None] or self.template_example()

    def export_queryset(self, user, params, options=None):
        return [a for a in self._roster(user, options) if getattr(a, "offer", None) is not None]

    def export_row(self, a):
        o = a.offer
        return {"roll_number": a.student.roll_number, "name": _name(a.student),
                "package_lpa": o.package_lpa if o.package_lpa is not None else "",
                "joining_date": F.format_date(o.joining_date), "remarks": o.remarks}


# ===================== ROUND RESULTS =====================
ROUND_STATUS = {"cleared": "cleared", "c": "cleared", "yes": "cleared", "selected": "cleared",
                "not cleared": "not_cleared", "not_cleared": "not_cleared", "nc": "not_cleared",
                "no": "not_cleared", "rejected": "not_cleared",
                "absent": "absent", "ab": "absent", "a": "absent"}
ROUND_LABEL = {"cleared": "Cleared", "not_cleared": "Not cleared", "absent": "Absent"}


class RoundResultImporter(_RosterImporter):
    key = "round_results"
    label = "round results"
    description = "Who cleared this round, from the shortlist the company sent."
    file_stem = "round-results"
    option_keys = ["round"]

    columns = [
        F.roll_number("always", "Roll number of a student in this round."),
        F.Column("name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.Column("status", "Result", "always", "Cleared", "Cleared, Not cleared or Absent.",
                 F.parse_choice(ROUND_STATUS, "result", "Cleared, Not cleared or Absent")),
        F.Column("remarks", "Remarks", False, "", "Optional, up to 255 characters."),
    ]

    def can_use(self, user):
        return can_view_placement_staff(user)

    def resolve_options(self, user, raw):
        try:
            rid = int(raw.get("round") or 0)
        except (TypeError, ValueError):
            rid = 0
        if not rid:
            raise OptionError("Choose a round first.")
        rd = DriveRound.objects.select_related("job_role__drive__company").filter(pk=rid).first()
        if rd is None:
            raise OptionError("Round not found.", 404)
        return {"round": rd}

    def file_name(self, options):
        rd = options.get("round")
        return _role_file_name(rd.job_role if rd else None, f"round-{rd.order}-results" if rd else "round-results")

    def _roster(self, user, options):
        from .views_rounds import _roster
        return _roster(options["round"], user)

    def prepare(self, user, options=None):
        from .models import RoundResult
        ctx = super().prepare(user, options)
        ctx["results"] = {r.application_id: r for r in
                          RoundResult.objects.filter(round=options["round"], application__in=ctx["apps"])}
        return ctx

    def find_existing(self, values, ctx):
        if "roll_number" not in values:
            return None
        return ctx["results"].get(self._app(values, ctx).id)

    def check_row(self, values, existing, ctx, user):
        app = self._app(values, ctx)
        remarks = (values.get("remarks") or "")[:255]
        if existing is not None and "remarks" not in values:
            remarks = existing.remarks
        if existing is not None and existing.status == values["status"] and existing.remarks == remarks:
            return SKIP
        return (app.id, values["status"], remarks)

    def save_row(self, payload, existing, ctx, user):
        from .services import save_round_result
        app_id, status, remarks = payload
        save_round_result(ctx["round"], app_id, status, remarks, user)
        return None

    def template_rows(self, user, options):
        return [[a.student.roll_number, _name(a.student), "", ""]
                for a in self._roster(user, options) if a.student.roll_number] or self.template_example()

    def export_queryset(self, user, params, options=None):
        from .models import RoundResult
        apps = list(self._roster(user, options))
        res = {r.application_id: r for r in RoundResult.objects.filter(round=options["round"], application__in=apps)}
        for a in apps:
            a._result = res.get(a.id)
        return apps

    def export_row(self, a):
        r = getattr(a, "_result", None)
        return {"roll_number": a.student.roll_number, "name": _name(a.student),
                "status": ROUND_LABEL.get(r.status, "") if r else "", "remarks": r.remarks if r else ""}
