"""
IA marks and Semester results - import / export through the shared engine
(core/dataio). Registered from ExamsConfig.ready(), so when the exams module
is switched off for a college these imports don't exist.

Both follow the SAME rules as the manual entry screens:
  IA marks  - teacher: own subject only; a locked IA can't be changed;
              only students enrolled in the subject are accepted.
  Results   - exam admin; grade + pass/fail computed on the server
              (services.compute_grade); the semester comes from the SUBJECT,
              never from the browser; only students of that class accepted.

Marks column (same in both):
  42    -> 42 marks
  AB    -> absent
  blank -> left as it is (nothing typed = nothing changed)
"""

import re

from core.academics.models import Enrollment, TeachingAssignment
from core.dataio import fields as F
from core.dataio.engine import SKIP, Importer, OptionError, RowError
from core.users.models import User

from .models import IAMark, InternalAssessment, ResultEntry, SemesterResult
from .services import compute_grade

ABSENT = "AB"


def parse_marks(text):
    t = str(text).strip()
    if t.upper() in ("AB", "A", "ABS", "ABSENT"):
        return ABSENT
    try:
        n = float(t)
    except ValueError:
        raise F.CellError(f"'{text}' is not a number (type AB for absent)")
    if n != n:   # NaN
        raise F.CellError(f"'{text}' is not a number")
    return n


def _int_option(raw, name, lo, hi, default=None):
    if raw in (None, ""):
        if default is None:
            raise OptionError(f"{name} is required.")
        return default
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        raise OptionError(f"{name} must be a number.")
    if not lo <= n <= hi:
        raise OptionError(f"{name} must be between {lo} and {hi}.")
    return n


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-")[:40] or "marks"


def _name(u):
    return u.display_name


def _marks_cell(value, absent=False):
    if absent:
        return ABSENT
    if value is None:
        return ""
    return int(value) if float(value).is_integer() else value


ROLL = F.Column("roll_number", "Roll number", "always", "25ME001", "Don't change - it identifies the student.")
NAME = F.Column("first_name", "Name", False, "Aarthi R", "For your reference only - not saved.")


class _MarksImporter(Importer):
    modes = ("upsert",)
    match_column = "roll_number"
    match_label = "roll number"

    def unique_in_file(self):
        return ["roll_number"]

    def row_title(self, values, existing):
        return values.get("first_name", "")

    def template_example(self):
        return [["25ME001", "Aarthi R", ""]]

    def instructions(self):
        rows = super().instructions()
        rows.append(["Marks", "", "Type the marks, AB for absent, or leave blank to leave that student unchanged.", ""])
        return rows

    def _student(self, values, ctx):
        roll = values.get("roll_number")
        s = ctx["roster"].get(str(roll).strip().lower())
        if s is None:
            raise F.CellError(f"Roll number '{roll}' {ctx['not_in']}")
        return s


# ===================== IA MARKS =====================
class IAMarksImporter(_MarksImporter):
    key = "ia_marks"
    label = "IA marks"
    description = "Marks for one internal assessment of one subject."
    file_stem = "ia-marks"
    option_keys = ["teaching_assignment", "number", "max_marks"]

    columns = [
        ROLL,
        NAME,
        F.Column("marks", "Marks", False, "42", "Marks out of the maximum. AB = absent. Blank = unchanged.", parse_marks),
    ]

    def can_use(self, user):
        return getattr(user, "is_authenticated", False) and user.role in ("teacher", "admin")

    def resolve_options(self, user, raw):
        ta_id = _int_option(raw.get("teaching_assignment"), "Subject", 1, 10**9)
        ta = (TeachingAssignment.objects.select_related("subject", "course", "year")
              .filter(id=ta_id).first())
        if ta is None:
            raise OptionError("Subject not found.", 404)
        if user.role == "teacher" and ta.teacher_id != user.id:
            raise OptionError("This isn't your subject.", 403)
        number = _int_option(raw.get("number"), "IA number", 1, 3)
        slot = InternalAssessment.objects.filter(teaching_assignment=ta, number=number).first()
        max_marks = _int_option(raw.get("max_marks"), "Maximum marks", 1, 200,
                                default=slot.max_marks if slot else 50)
        return {"ta": ta, "number": number, "slot": slot, "max_marks": max_marks}

    def write_blocked(self, options):
        slot = options.get("slot")
        if slot and slot.is_locked:
            return "This IA is locked and can no longer be edited."
        if slot and slot.questions.exists():           # CO-PO PART B
            return "This IA has a question paper: enter or import its marks question by question."
        return None

    def file_name(self, options):
        ta = options.get("ta")
        if not ta:
            return self.file_stem
        return f"IA{options['number']}-{_slug(ta.subject.code or ta.subject.name)}"

    def _enrolled(self, ta):
        return [e.student for e in Enrollment.objects.filter(teaching_assignment=ta)
                .select_related("student").order_by("student__roll_number")]

    def prepare(self, user, options=None):
        ta, slot = options["ta"], options["slot"]
        marks = {m.student_id: m for m in IAMark.objects.filter(assessment=slot)} if slot else {}
        return {
            **options,
            "roster": {s.roll_number.strip().lower(): s for s in self._enrolled(ta) if s.roll_number},
            "marks": marks,
            "not_in": "isn't enrolled in this subject",
        }

    def find_existing(self, values, ctx):
        s = self._student(values, ctx)
        return ctx["marks"].get(s.id)

    def check_row(self, values, existing, ctx, user):
        if "marks" not in values:
            return SKIP
        s = self._student(values, ctx)
        m = values["marks"]
        if m == ABSENT:
            return (s, None, True)
        if m < 0 or m > ctx["max_marks"]:
            raise RowError([f"Marks {m:g} is out of range (0 to {ctx['max_marks']})"])
        return (s, m, False)

    def save_row(self, payload, existing, ctx, user):
        student, marks, absent = payload
        slot = ctx.get("_slot")
        if slot is None:
            slot, _ = InternalAssessment.objects.get_or_create(
                teaching_assignment=ctx["ta"], number=ctx["number"],
                defaults={"max_marks": ctx["max_marks"]},
            )
            if slot.is_locked:
                raise RowError(["This IA is locked and can no longer be edited."])
            if slot.max_marks != ctx["max_marks"]:
                slot.max_marks = ctx["max_marks"]
                slot.save(update_fields=["max_marks"])
            ctx["_slot"] = slot
        IAMark.objects.update_or_create(
            assessment=slot, student=student,
            defaults={"marks_obtained": marks, "is_absent": absent},
        )
        return None

    # ---------- template / export ----------
    def template_rows(self, user, options):
        return [[s.roll_number or "", _name(s), ""] for s in self._enrolled(options["ta"])]

    def export_queryset(self, user, params, options=None):
        slot = options["slot"]
        marks = {m.student_id: m for m in IAMark.objects.filter(assessment=slot)} if slot else {}
        return [(s, marks.get(s.id)) for s in self._enrolled(options["ta"])]

    def export_row(self, pair):
        s, m = pair
        return {
            "roll_number": s.roll_number or "",
            "first_name": _name(s),
            "marks": _marks_cell(m.marks_obtained, m.is_absent) if m else "",
        }


# ===================== SEMESTER RESULTS =====================
class ResultsImporter(_MarksImporter):
    key = "results"
    label = "results"
    description = "Final semester marks for one subject. Grades are worked out automatically."
    file_stem = "results"
    option_keys = ["teaching_assignment", "max_marks"]

    columns = [
        ROLL,
        NAME,
        F.Column("marks", "Marks", False, "78", "Total marks out of the maximum. AB = absent. Blank = unchanged.", parse_marks),
        F.Column("grade", "Grade", False, "A", "Filled in automatically - ignored when importing."),
        F.Column("result", "Result", False, "Pass", "Filled in automatically - ignored when importing."),
        # WAVE 3 PART 1B (CBCS): marks split by the student's regulation, grades given by hand
        F.Column("internal", "Internal", False, "32", "Internal marks (with End-sem, instead of Marks). AB = absent.", parse_marks),
        F.Column("end", "End-sem", False, "46", "End-semester marks (with Internal, instead of Marks). AB = absent.", parse_marks),
        F.Column("hand_grade", "Grade by hand", False, "", "Only SA / W style grades from the regulation. Leave empty normally."),
    ]

    def can_use(self, user):
        from .views import is_exam_admin   # same rule as the Results page
        return getattr(user, "is_authenticated", False) and is_exam_admin(user)

    def template_example(self):
        return [["25ME001", "Aarthi R", "", "", "", "", "", ""]]

    def resolve_options(self, user, raw):
        ta_id = _int_option(raw.get("teaching_assignment"), "Subject", 1, 10**9)
        ta = (TeachingAssignment.objects.select_related("subject", "course", "year")
              .filter(id=ta_id).first())
        if ta is None:
            raise OptionError("Subject not found.", 404)
        max_marks = _int_option(raw.get("max_marks"), "Maximum marks", 1, 200, default=100)
        # the semester comes from the subject - never from the browser
        return {
            "ta": ta,
            "subject": ta.subject,
            "semester": ta.subject.semester,
            "course_id": ta.course_id,
            "year": ta.year.year_number,
            "max_marks": max_marks,
        }

    def file_name(self, options):
        subj = options.get("subject")
        if not subj:
            return self.file_stem
        return f"Sem{options['semester']}-{_slug(subj.code or subj.name)}-results"

    def _roster(self, o):
        # same class as the Results page grid (students_by_class)
        return list(User.objects.filter(role="student", course_id=o["course_id"],
                                        year=o["year"], semester=o["semester"]).order_by("roll_number"))

    def prepare(self, user, options=None):
        o = options
        roster = self._roster(o)
        ids = [s.id for s in roster]
        entries = {e.result.student_id: e for e in ResultEntry.objects.filter(
            subject=o["subject"], result__semester=o["semester"], result__student_id__in=ids
        ).select_related("result")}
        published = set(SemesterResult.objects.filter(
            semester=o["semester"], student_id__in=ids, is_published=True
        ).values_list("student_id", flat=True))
        return {
            **o,
            "roster": {s.roll_number.strip().lower(): s for s in roster if s.roll_number},
            "entries": entries,
            "published": published,
            "not_in": "isn't in this class",
        }

    def find_existing(self, values, ctx):
        s = self._student(values, ctx)
        return ctx["entries"].get(s.id)

    def check_row(self, values, existing, ctx, user):
        from .grading import GradingError, grade, rules_for
        split = "internal" in values or "end" in values
        hand = (values.get("hand_grade") or "").strip() or None
        if "marks" not in values and not split and not hand:
            return SKIP
        s = self._student(values, ctx)
        if s.id in ctx["published"]:
            raise RowError(["This student's result is already published. Unpublish it before changing marks."])
        if split and "marks" in values:
            raise RowError(["Fill either Marks, or Internal and End-sem - not both."])
        internal = None if values.get("internal") in (None, ABSENT) else values.get("internal")
        end = None if values.get("end") in (None, ABSENT) else values.get("end")
        absent = (values.get("marks") == ABSENT) or (split and (values.get("internal") == ABSENT or values.get("end") == ABSENT))
        if absent:
            internal = end = None
        total = None if (split or absent or "marks" not in values) else values["marks"]
        if not split and total is not None and (total < 0 or total > ctx["max_marks"]):
            raise RowError([f"Marks {total:g} is out of range (0 to {ctx['max_marks']})"])
        payload = {"internal": internal, "end": end, "total": total, "manual": hand}
        try:
            grade(rules_for(s, ctx["subject"]), max_marks=ctx["max_marks"], **payload)   # checks only
        except GradingError as e:
            raise RowError([str(e)])
        return (s, payload)

    def save_row(self, payload, existing, ctx, user):
        from .grading import GradingError, record_result
        student, data = payload
        result = SemesterResult.objects.filter(student=student, semester=ctx["semester"]).first()
        if result is not None and result.is_published:
            raise RowError(["Result was published while importing. Nothing saved."])
        try:
            record_result(student, ctx["subject"], ctx["semester"], max_marks=ctx["max_marks"], **data)
        except GradingError as e:
            raise RowError([str(e)])
        return None

    # ---------- template / export ----------
    def template_rows(self, user, options):
        return [[s.roll_number or "", _name(s), "", "", "", "", "", ""] for s in self._roster(options)]

    def export_queryset(self, user, params, options=None):
        ctx = self.prepare(user, options)
        return [(s, ctx["entries"].get(s.id)) for s in self._roster(options)]

    def export_row(self, pair):
        s, e = pair
        if not e:
            return {"roll_number": s.roll_number or "", "first_name": _name(s)}
        absent = e.marks_obtained is None
        return {
            "roll_number": s.roll_number or "",
            "first_name": _name(s),
            "marks": "" if e.internal_marks is not None else _marks_cell(e.marks_obtained, absent),
            "grade": e.grade,
            "result": "Pass" if e.is_pass else "Fail",
            "internal": _marks_cell(e.internal_marks) if e.internal_marks is not None else "",
            "end": _marks_cell(e.end_marks) if e.end_marks is not None else "",
            "hand_grade": e.grade if e.outcome in ("arrear", "excluded") else "",
        }


# ===================== EXAM SCHEDULE =====================
SESSIONS = {"fn": "FN", "forenoon": "FN", "morning": "FN", "am": "FN",
            "an": "AN", "afternoon": "AN", "pm": "AN"}
SESSION_NAME = {"FN": "FN", "AN": "AN"}


class ExamScheduleImporter(Importer):
    """
    The exam timetable: one row per subject (date + session). Same rules as
    the Hall Ticket page's schedule grid, checked on the server:
      * no exams on Saturday / Sunday, or on a holiday
      * no two exams of the SAME class (course + year + semester) on the
        same date + session - across the whole file AND what is already saved
      * one exam per subject per semester (database rule) - an existing
        subject is updated, never duplicated
    """
    key = "exam_schedule"
    label = "exam schedule"
    description = "Exam date and session (FN / AN) for each subject."
    file_stem = "exam-schedule"
    match_column = "subject"
    match_label = "course, year, semester and subject"

    columns = [
        F.course("always"),
        F.year("always"),
        F.semester("always"),
        F.Column("subject", "Subject", "always", "ME3101",
                 "Subject code or name, exactly as in Subjects for that course, year and semester."),
        F.Column("subject_name", "Subject name", False, "Thermodynamics", "For your reference only - not saved."),
        F.date_col("exam_date", "Exam date", "24-11-2026", required="always"),
        F.Column("session", "Session", False, "FN", "FN (forenoon) or AN (afternoon). Blank = FN for new rows.",
                 F.parse_choice(SESSIONS, "session", "FN or AN")),
    ]

    def can_use(self, user):
        from .views import is_exam_admin          # same rule as the Hall Ticket page
        return getattr(user, "is_authenticated", False) and is_exam_admin(user)

    def unique_in_file(self):
        return []                                 # checked on the full key below

    def prepare(self, user, options=None):
        from core.academics.holidays import holiday_map
        from core.academics.models import Course, Subject, Year
        from .models import ExamSchedule

        subjects = {}
        for sub in Subject.objects.select_related("year"):
            for v in (sub.code, sub.name):
                if v:
                    subjects.setdefault((sub.year_id, sub.semester, str(v).strip().lower()), sub)
        holidays = holiday_map()          # handles the Events module being off
        # WAVE 3 PART 2: the file fills the CURRENT exam session's timetable
        from .exam_sessions import current_session, schedule_rows
        session = current_session()
        return {
            "session": session,
            "courses": F.Lookup(Course.objects.all(), "name", name="course"),
            "years": {(y.course_id, y.year_number): y for y in Year.objects.all()},
            "subjects": subjects,
            "schedules": {(e.subject_id, e.semester): e for e in
                          schedule_rows(session).select_related("subject__year")},
            "holidays": holidays,
            "seen": set(),
        }

    def _subject(self, values, ctx):
        course = ctx["courses"].find(values.get("course", ""))
        year = ctx["years"].get((course.id, values.get("year")))
        if year is None:
            raise F.CellError(f"{course.name} has no Year {values.get('year')}")
        F.semester_fits_year(values.get("year"), values.get("semester"))
        sub = ctx["subjects"].get((year.id, values["semester"], values["subject"].strip().lower()))
        if sub is None:
            raise F.CellError(f"Subject '{values['subject']}' not found in {course.name} "
                              f"Year {values['year']}, Semester {values['semester']}")
        return sub

    def find_existing(self, values, ctx):
        if not all(k in values for k in ("course", "year", "semester", "subject")):
            return None
        sub = self._subject(values, ctx)
        if sub.id in ctx["seen"]:
            raise F.CellError("The same subject appears more than once in the file")
        ctx["seen"].add(sub.id)
        return ctx["schedules"].get((sub.id, sub.semester))

    def row_title(self, values, existing):
        return values.get("subject_name") or values.get("subject", "")

    def check_row(self, values, existing, ctx, user):
        sess = ctx.get("session")
        if sess is not None and sess.timetable_published:
            raise RowError([f"The {sess.name} timetable is published - unpublish it to change exam dates"])
        sub = self._subject(values, ctx)
        day = values["exam_date"]
        session = values.get("session") or (existing.session if existing else "FN")
        problems = []
        if day.weekday() >= 5:
            problems.append(f"{day:%d-%m-%Y} is a {'Saturday' if day.weekday() == 5 else 'Sunday'} - no exams on weekends")
        if day in ctx["holidays"]:
            problems.append(f"{day:%d-%m-%Y} is a holiday ({ctx['holidays'][day]})")
        if problems:
            raise RowError(problems)
        if existing is not None and existing.exam_date == day and existing.session == session:
            return SKIP
        return {"subject": sub, "semester": sub.semester, "exam_date": day, "session": session,
                "class": (sub.year_id, sub.semester)}

    def check_file(self, checked, ctx):
        """Two exams of the same class on the same date + session = clash."""
        # what the schedule will look like after this import
        final = {}      # subject_id -> (class, date, session, name, row_no or None)
        for (sid, _sem), e in ctx["schedules"].items():
            final[sid] = ((e.subject.year_id, e.semester), e.exam_date, e.session, e.subject.name, None)
        for row_no, p, _existing in checked:
            s = p["subject"]
            final[s.id] = (p["class"], p["exam_date"], p["session"], s.name, row_no)
        # rows SKIPped as unchanged are already in `final` from the database

        slots = {}
        for sid, (cls, day, sess, name, row_no) in final.items():
            slots.setdefault((cls, day, sess), []).append((name, row_no))
        errors = {}
        for (cls, day, sess), items in slots.items():
            if len(items) < 2:
                continue
            for name, row_no in items:
                if row_no is None:
                    continue
                others = ", ".join(n for n, r in items if not (n == name and r == row_no))
                errors.setdefault(row_no, []).append(
                    f"Clash - {others} is also on {day:%d-%m-%Y} {SESSION_NAME[sess]} for this class")
        return errors

    def save_row(self, payload, existing, ctx, user):
        from .models import ExamSchedule
        sess = ctx.get("session")
        if sess is not None:
            ExamSchedule.objects.update_or_create(
                exam_session=sess, subject=payload["subject"],
                defaults={"semester": payload["semester"], "exam_date": payload["exam_date"],
                          "session": payload["session"]},
            )
        else:
            ExamSchedule.objects.update_or_create(
                exam_session=None, subject=payload["subject"], semester=payload["semester"],
                defaults={"exam_date": payload["exam_date"], "session": payload["session"]},
            )
        return None

    def template_example(self):
        return [["B.E Mechanical", "2", "3", "ME3101", "Thermodynamics", "24-11-2026", "FN"]]

    def export_queryset(self, user, params, options=None):
        from .models import ExamSchedule
        from .exam_sessions import current_session, schedule_rows
        qs = schedule_rows(current_session()).select_related("subject__year__course").order_by("exam_date", "session")
        if params.get("semester"):
            qs = qs.filter(semester=params["semester"])
        if params.get("course"):
            qs = qs.filter(subject__year__course_id=params["course"])
        if params.get("year"):
            qs = qs.filter(subject__year__year_number=params["year"])
        return qs

    def export_row(self, e):
        s = e.subject
        return {
            "course": s.year.course.name,
            "year": s.year.year_number,
            "semester": e.semester,
            "subject": s.code or s.name,
            "subject_name": s.name,
            "exam_date": F.format_date(e.exam_date),
            "session": e.session,
        }
