import datetime

from django.utils import timezone

from config.module_registry import module_enabled
from core.academics.models import Enrollment, TeachingAssignment
from core.dataio import fields as F
from core.dataio.engine import SKIP, Importer, OptionError, RowError

from .models import Attendance, ODRequest

STATUS = {
    "p": "present", "present": "present",
    "a": "absent", "ab": "absent", "absent": "absent",
    "od": "duty_leave", "on duty": "duty_leave", "duty leave": "duty_leave", "duty_leave": "duty_leave",
}
STATUS_TEXT = {"present": "P", "absent": "A", "duty_leave": "OD"}


def _holidays():
    from core.academics.holidays import holiday_map
    days = dict(holiday_map())
    if module_enabled("timetable"):          # same extra source bulk_mark uses
        from modules.timetable.models import Holiday
        for h in Holiday.objects.all():
            days.setdefault(h.date, h.name)
    return days


class AttendanceImporter(Importer):
    key = "attendance"
    label = "attendance"
    description = "Attendance for one subject - one row per student, date and period."
    file_stem = "attendance"
    modes = ("upsert",)
    match_column = "roll_number"
    match_label = "roll number"
    option_keys = ["teaching_assignment"]

    columns = [
        F.Column("roll_number", "Roll number", "always", "25ME001", "Student's roll number."),
        F.Column("first_name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.date_col("date", "Date", "02-09-2026", required="always"),
        F.Column("period", "Period", "always", "1", "Period number, 1 to 12.", F.parse_int(1, 12, "period")),
        F.Column("status", "Status", "always", "P", "P = present, A = absent, OD = on duty.",
                 F.parse_choice(STATUS, "status", "P, A or OD")),
    ]

    def can_use(self, user):
        # teachers (own subjects) and the main admin - not other sub-admins
        if not getattr(user, "is_authenticated", False):
            return False
        return user.role == "teacher" or user.is_superuser or (
            user.role == "admin" and (user.sub_role or "") in ("", "super_admin"))

    def resolve_options(self, user, raw):
        try:
            ta_id = int(raw.get("teaching_assignment") or 0)
        except (TypeError, ValueError):
            ta_id = 0
        if not ta_id:
            raise OptionError("Choose a subject first.")
        ta = TeachingAssignment.objects.select_related("subject").filter(id=ta_id).first()
        if ta is None:
            raise OptionError("Subject not found.", 404)
        if user.role == "teacher" and ta.teacher_id != user.id:
            raise OptionError("This isn't your subject.", 403)
        return {"ta": ta}

    def file_name(self, options):
        ta = options.get("ta")
        if not ta:
            return self.file_stem
        return f"attendance-{ta.subject.code or ta.subject.name}".replace(" ", "-")[:60]

    def _enrolled(self, ta):
        return [e.student for e in Enrollment.objects.filter(teaching_assignment=ta)
                .select_related("student").order_by("student__roll_number")]

    def unique_in_file(self):
        return []          # duplicates are checked on roll + date + period

    def prepare(self, user, options=None):
        ta = options["ta"]
        roster = self._enrolled(ta)
        ids = [s.id for s in roster]
        od = {}
        for r in ODRequest.objects.filter(status=ODRequest.Status.APPROVED, student_id__in=ids):
            od.setdefault(r.student_id, []).append((r.from_date, r.to_date))
        return {
            **options,
            "roster": {s.roll_number.strip().lower(): s for s in roster if s.roll_number},
            "records": {(a.student_id, a.date, a.hour): a for a in Attendance.objects.filter(teaching_assignment=ta)},
            "od": od,
            "holidays": _holidays(),
            "today": timezone.localdate(),
            "seen": set(),
            "sessions": {},      # (date, period) -> session_status, see check_row
        }

    def _session(self, ctx, day, hour):
        """
        ATTENDANCE WINDOW (#46): the same register state the attendance screen
        uses. Worked out once per date + period, before anything is saved
        (the engine checks every row first, then saves), so rows earlier in
        the file can't open a window for rows later in it.
        """
        key = (day, hour)
        if key not in ctx["sessions"]:
            from .attendance_rules import session_status
            ctx["sessions"][key] = session_status(ctx["ta"], day, hour, today=ctx["today"])
        return ctx["sessions"][key]

    def _student(self, values, ctx):
        roll = values.get("roll_number", "")
        s = ctx["roster"].get(str(roll).strip().lower())
        if s is None:
            raise F.CellError(f"Roll number '{roll}' isn't enrolled in this subject")
        return s

    def find_existing(self, values, ctx):
        if not all(k in values for k in ("roll_number", "date", "period")):
            return None
        s = self._student(values, ctx)
        key = (s.id, values["date"], values["period"])
        if key in ctx["seen"]:
            raise F.CellError("The same student, date and period appear more than once in the file")
        ctx["seen"].add(key)
        return ctx["records"].get(key)

    def row_title(self, values, existing):
        return values.get("first_name", "")

    def check_row(self, values, existing, ctx, user):
        s = self._student(values, ctx)
        day = values["date"]
        problems = []
        if day > ctx["today"]:
            problems.append(f"{day:%d-%m-%Y} is in the future")
        if day in ctx["holidays"]:
            problems.append(f"{day:%d-%m-%Y} is a holiday ({ctx['holidays'][day]})")
        on_duty = any(f <= day <= t for f, t in ctx["od"].get(s.id, []))
        if on_duty and values["status"] != "duty_leave":
            problems.append("This student has an approved on-duty request for this date - status must be OD")
        elif not on_duty and values["status"] == "duty_leave":
            # same rule as the register and the tutor's late entry:
            # On duty only comes from an approved OD request
            problems.append("No approved on-duty request for this date - status must be P or A")
        if problems:
            raise RowError(problems)

        # ── ATTENDANCE WINDOW (#46): the file follows the SAME rules as the
        # attendance screen (bulk_mark), for everyone, admin included.
        # Without this, importing a file was a way round the lock and the
        # correction log. Re-sending an unchanged status is always fine.
        st = self._session(ctx, day, values["period"])
        if existing is not None:
            if existing.status == values["status"]:
                return SKIP      # nothing changes - keep the original marked_by
            if existing.status != values["status"]:
                if st["state"] == "locked":
                    why = (f"locked by {st['lock']['by']}" if st.get("lock")
                           else f"locked - the correction window ended on {st['edit_until']:%d-%m-%Y}")
                    raise RowError([f"Period {values['period']} on {day:%d-%m-%Y} is {why}. "
                                    "Only the class in-charge can correct it now (My Class)."])
                if st["state"] == "open_reason":
                    raise RowError([f"Period {values['period']} on {day:%d-%m-%Y} was saved earlier - "
                                    "changing it now needs a reason. Change it on the attendance screen."])
        elif st["state"] in ("late_closed", "locked"):
            raise RowError([f"Late entry is closed for period {values['period']} on {day:%d-%m-%Y} "
                            f"(deadline {st['late_entry_deadline']:%d-%m-%Y}). Ask the class in-charge to enter it."])
        return (s, day, values["period"], values["status"])

    def save_row(self, payload, existing, ctx, user):
        student, day, hour, status = payload
        Attendance.objects.update_or_create(
            teaching_assignment=ctx["ta"], student=student, date=day, hour=hour,
            defaults={"status": status, "marked_by": user},
        )
        return None

    # ---------- template / export ----------
    def template_example(self):
        return [["25ME001", "Aarthi R", "02-09-2026", "1", "P"]]

    def template_rows(self, user, options):
        return [[s.roll_number or "", s.display_name, "", "", ""] for s in self._enrolled(options["ta"])]

    def export_queryset(self, user, params, options=None):
        qs = (Attendance.objects.filter(teaching_assignment=options["ta"])
              .select_related("student").order_by("date", "hour", "student__roll_number"))
        for key, lookup in (("from_date", "date__gte"), ("to_date", "date__lte")):
            if params.get(key):
                try:
                    qs = qs.filter(**{lookup: datetime.date.fromisoformat(str(params[key])[:10])})
                except ValueError:
                    pass
        return qs

    def export_row(self, a):
        return {
            "roll_number": a.student.roll_number or "",
            "first_name": a.student.display_name,
            "date": F.format_date(a.date),
            "period": a.hour,
            "status": STATUS_TEXT.get(a.status, a.status),
        }