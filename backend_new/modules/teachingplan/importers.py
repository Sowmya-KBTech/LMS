"""
COURSE PLAN (Part C) - Excel template, import and export of a teacher's plan.

Plugs into the shared import/export engine (core/dataio). One row per
timetable session (date + period). The template and the export are the same
file: every session of this semester's timetable, already filled with what is
planned, so a teacher can download it, fill it in Excel and upload it back.

Rules
  * Only the teacher's own subject; only while the plan is a draft or sent back.
  * A row must be a session in the teacher's timetable (date + period).
  * A row without a topic is a "not yet planned" session and is skipped.
  * Empty cells never erase what is already planned (the engine's "update" mode).
  * Labels or codes are both accepted: "Lab / practical" or "lab", "Unit 3" or "3".
"""
from datetime import date

from django.apps import apps

from core.dataio import fields as F
from core.dataio.engine import SKIP, Importer, OptionError, RowError

from .models import (BEYOND_ACTIVITIES, CLASS_ACTIVITIES, MAX_UNITS, TEACHING_METHODS, TEACHING_MODES,
                     CourseOutcome, PlanUnit, TeachingPlan)

class Day(date):
    """A date that prints as DD-MM-YYYY, so the import preview shows dates the way the file does."""

    def __str__(self):
        return self.strftime("%d-%m-%Y")


def parse_day(text):
    d = F.parse_date(text)
    return Day(d.year, d.month, d.day)


def _choices(pairs):
    """Accept the code or the label, without case."""
    m = {}
    for code, label in pairs:
        m[code.lower()] = code
        m[label.lower()] = code
    return m


def _labels(pairs):
    return ", ".join(label for _, label in pairs)


def parse_unit(text):
    t = str(text).strip().lower().replace("unit", "").strip()
    return F.parse_int(1, MAX_UNITS, "unit")(t)


def parse_codes(text):
    """'CO1, CO3' / 'co1;co3' / 'CO1 CO3' -> ['CO1', 'CO3']"""
    parts = [p.strip().upper() for p in str(text).replace(";", ",").replace(" ", ",").split(",") if p.strip()]
    for p in parts:
        if not (p.startswith("CO") and p[2:].isdigit()):
            raise F.CellError(f"'{p}' is not an outcome code - write CO1, CO2 ...")
    return parts


def find_plan(teacher, subject):
    """The plan this page edits: teacher + subject + the class from the timetable."""
    from .serializers import class_labels_for
    labels = class_labels_for(teacher, subject)
    qs = TeachingPlan.objects.filter(teacher=teacher, subject=subject)
    if labels:
        qs = qs.filter(class_section=labels[0])
    return qs.order_by("-updated_at").first()


def create_plan(teacher, subject):
    """A new draft plan for this teacher's subject (class, semester and hours from the timetable)."""
    from .serializers import class_labels_for
    from .views import timetable_sessions
    allotted, _ = timetable_sessions(teacher, subject.id)
    labels = class_labels_for(teacher, subject)
    return TeachingPlan.objects.create(
        teacher=teacher, subject=subject, department=getattr(teacher, "department", None),
        class_section=labels[0] if labels else "", allotted_hours=allotted,
        semester=f"Semester {subject.semester}" if getattr(subject, "semester", None) else "",
        status="draft")


class CoursePlanImporter(Importer):
    key = "course_plan"
    label = "course plan"
    description = "One row per timetable session: unit, topic, teaching mode and the other columns."
    file_stem = "course-plan"
    modes = ("upsert",)
    match_column = "date"
    match_label = "date and period"
    option_keys = ["subject"]

    columns = [
        F.Column("date", "Date (DD-MM-YYYY)", "always", "12-08-2026", "Date as DD-MM-YYYY.", parse_day),
        F.Column("day", "Day", False, "Wednesday", "For your reference only - not saved."),
        F.Column("period", "Period", "always", "2", "Period number from your timetable.",
                 F.parse_int(1, 12, "period")),
        F.Column("unit_no", "Unit", False, "2", f"Unit of the syllabus, 1 to {MAX_UNITS}.", parse_unit),
        F.Column("topic", "Topic", False, "First law for a closed system",
                 "What you will teach. Leave empty for a session you have not planned yet."),
        F.Column("notes", "Notes", False, "Closed systems, sign convention", "Optional."),
        F.Column("mode", "Teaching mode", False, "Lecture", _labels(TEACHING_MODES),
                 F.parse_choice(_choices(TEACHING_MODES), "teaching mode", _labels(TEACHING_MODES))),
        F.Column("method", "Teaching method", False, "Case study", _labels(TEACHING_METHODS),
                 F.parse_choice(_choices(TEACHING_METHODS), "teaching method", _labels(TEACHING_METHODS))),
        F.Column("class_activity", "Class activity", False, "Quiz", _labels(CLASS_ACTIVITIES),
                 F.parse_choice(_choices(CLASS_ACTIVITIES), "class activity", _labels(CLASS_ACTIVITIES))),
        F.Column("beyond_activity", "Beyond-class activity", False, "Industrial visit", _labels(BEYOND_ACTIVITIES),
                 F.parse_choice(_choices(BEYOND_ACTIVITIES), "beyond-class activity", _labels(BEYOND_ACTIVITIES))),
        F.Column("outcomes", "Outcomes", False, "CO1, CO2",
                 "Course outcome codes this session teaches, separated by commas.", parse_codes),
    ]

    def can_use(self, user):
        return getattr(user, "is_authenticated", False) and user.role == "teacher"

    # ---------- the page's selection ----------
    def resolve_options(self, user, raw):
        try:
            subject_id = int(raw.get("subject") or 0)
        except (TypeError, ValueError):
            subject_id = 0
        if not subject_id:
            raise OptionError("Choose a subject first.")
        Subject = apps.get_model("courses", "Subject")
        subject = Subject.objects.filter(id=subject_id).first()
        if subject is None:
            raise OptionError("Subject not found.", 404)
        TA = apps.get_model("courses", "TeachingAssignment")
        if not TA.objects.filter(teacher=user, subject=subject).exists():
            raise OptionError("This isn't your subject.", 403)
        return {"subject": subject, "plan": find_plan(user, subject)}

    def write_blocked(self, options):
        plan = options.get("plan")
        if plan and plan.status in ("submitted", "approved"):
            return "This plan is with the HOD or approved, so it can't be changed by import."
        return None

    def file_name(self, options):
        s = options.get("subject")
        return f"course-plan-{(s.code or s.name) if s else ''}".replace(" ", "-")[:60]

    # ---------- the timetable sessions, filled with what is planned ----------
    def _sessions(self, user, options):
        from .views import timetable_sessions
        _, days = timetable_sessions(user, options["subject"].id)
        return [d for d in days if not d.get("holiday")]

    def _rows(self, user, options):
        plan = options.get("plan")
        units = {}
        if plan:
            for u in plan.units.all().prefetch_related("outcomes"):
                units[(u.complete_by.isoformat() if u.complete_by else "", u.period_no)] = u
        out = []
        for d in self._sessions(user, options):
            u = units.get((d["date"], d["period_no"]))
            y, m, dd = d["date"].split("-")
            out.append({
                "date": f"{dd}-{m}-{y}", "day": d["weekday"], "period": d["period_no"],
                "unit_no": (u.unit_no or "") if u else "", "topic": u.topic if u else "",
                "notes": u.notes if u else "", "mode": u.get_mode_display() if u else "",
                "method": u.get_method_display() if u else "",
                "class_activity": u.get_class_activity_display() if u else "",
                "beyond_activity": u.get_beyond_activity_display() if u else "",
                "outcomes": ", ".join(o.code for o in u.outcomes.all()) if u else "",
            })
        return out

    def template_rows(self, user, options):
        return [[r[c.key] for c in self.columns] for r in self._rows(user, options)]

    def export_queryset(self, user, params, options=None):
        return self._rows(user, options)

    def export_row(self, obj):
        return obj

    # ---------- import ----------
    def unique_in_file(self):
        return []           # duplicates are checked on date + period

    def prepare(self, user, options=None):
        options = options or {}
        sessions = self._sessions(user, options)
        plan = options.get("plan")
        subject = options["subject"]
        return {
            **options,
            "user": user,
            "slots": {(d["date"], d["period_no"]): (i + 1, d.get("hours") or 1) for i, d in enumerate(sessions)},
            "units": ({(u.complete_by, u.period_no): u for u in plan.units.all()} if plan else {}),
            "codes": {o.code.upper(): o.id for o in CourseOutcome.objects.filter(subject=subject)},
            "seen": set(),
        }

    def find_existing(self, values, ctx):
        if "date" not in values or "period" not in values:
            return None
        key = (values["date"], values["period"])
        if key in ctx["seen"]:
            raise F.CellError("The same date and period appear more than once in the file")
        ctx["seen"].add(key)
        return ctx["units"].get(key)

    def row_title(self, values, existing):
        return values.get("topic") or (existing.topic if existing else "")

    def check_row(self, values, existing, ctx, user):
        day, period = values["date"], values["period"]
        slot = ctx["slots"].get((day.isoformat(), period))
        if slot is None:
            raise RowError([f"There is no class in your timetable on {day:%d-%m-%Y}, period {period}"])
        filled = [k for k in ("unit_no", "notes", "mode", "method", "class_activity", "beyond_activity", "outcomes")
                  if k in values]
        if not values.get("topic") and existing is None:
            if filled:
                raise RowError(["Write a topic - the other cells of this row are filled in"])
            return SKIP                                 # a session not planned yet
        missing = [c for c in values.get("outcomes", []) if c not in ctx["codes"]]
        if missing:
            raise RowError([f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not an outcome of this "
                            f"subject. Add it in the Course outcomes tab first"])
        payload = dict(values)
        payload["slot"] = slot
        if "outcomes" in values:
            payload["outcome_ids"] = [ctx["codes"][c] for c in values["outcomes"]]
        return payload

    def _plan(self, ctx):
        if ctx.get("plan") is None:
            ctx["plan"] = create_plan(ctx["user"], ctx["subject"])
        return ctx["plan"]

    def save_row(self, payload, existing, ctx, user):
        seq, hours = payload["slot"]
        fields = ("unit_no", "topic", "notes", "mode", "method", "class_activity", "beyond_activity")
        if existing is None:
            unit = PlanUnit.objects.create(
                plan=self._plan(ctx), complete_by=payload["date"], period_no=payload["period"],
                hours=hours, sequence_no=seq,
                **{k: payload.get(k, "" if k != "unit_no" else None) for k in fields})
        else:
            unit = existing
            for k in fields:
                if k in payload:
                    setattr(unit, k, payload[k])
            unit.save()
        if "outcome_ids" in payload:
            unit.outcomes.set(payload["outcome_ids"])
        return None
