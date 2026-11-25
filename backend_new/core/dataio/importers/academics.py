"""
Courses & Subjects import / export (core - always on).

Courses
  One row per course: name + number of years. Importing creates the course
  and its Year rows (1..N). Updating can ADD years, never remove them -
  removing a year would delete its subjects, so that stays a manual action.

Subjects
  One row per subject: course, year, semester, name (+ code, credits,
  weekly hours, elective, department). A subject is identified by
  course + year + semester + name - the same rule as the database
  (unique_subject_per_semester). The course year must already exist.
  Saved through SubjectSerializer, the same code the Courses page uses.
"""

from core.academics.models import Course, CourseCategory, Regulation, Subject, Year
from core.users.models import Department

from .. import fields as F
from ..engine import SKIP, Importer, RowError
from ..registry import register
from .users import _serializer_errors


# same rule the REST API uses (core/academics/permissions.py)
from core.academics.permissions import can_manage_academics  # noqa: E402


SUBJECT_KIND = {"theory": "theory", "practical": "practical", "project": "project", "lab": "practical"}
YES_NO = {"yes": True, "y": True, "true": True, "1": True, "no": False, "n": False, "false": False, "0": False}


# ===================== COURSES =====================
class CourseImporter(Importer):
    key = "courses"
    label = "courses"
    description = "Add courses and their years."
    file_stem = "courses"
    match_column = "name"
    match_label = "course name"

    columns = [
        F.Column("name", "Course name", "always", "B.E Mechanical", "Exactly as it should appear everywhere."),
        F.Column("years", "Number of years", "add", "4",
                 "1 to 6. Years 1..N are created. An update can add years but never removes them.",
                 F.parse_int(1, 6, "number of years")),
    ]

    def can_use(self, user):
        return can_manage_academics(user)

    def prepare(self, user, options=None):
        return {"courses": {c.name.strip().lower(): c for c in Course.objects.prefetch_related("years")}}

    def find_existing(self, values, ctx):
        return ctx["courses"].get(values.get("name", "").strip().lower())

    def row_title(self, values, existing):
        return values.get("name", "")

    def check_row(self, values, existing, ctx, user):
        if existing is not None and "years" in values:
            have = max([y.year_number for y in existing.years.all()] or [0])
            if values["years"] < have:
                raise RowError([f"This course already has {have} years. Import can add years but not remove them."])
        return values

    def save_row(self, payload, existing, ctx, user):
        course = existing or Course.objects.create(name=payload["name"].strip())
        for n in range(1, (payload.get("years") or 0) + 1):
            Year.objects.get_or_create(course=course, year_number=n)
        return None

    def export_queryset(self, user, params, options=None):
        return Course.objects.prefetch_related("years").order_by("name")

    def export_row(self, c):
        return {"name": c.name, "years": max([y.year_number for y in c.years.all()] or [0]) or ""}



# ===================== DEPARTMENTS =====================
class DepartmentImporter(Importer):
    """
    One row per department: name (+ short code, + HOD).
    Matched by name. The code must be unique across departments (it is used
    in roll numbers). The HOD is optional - departments are usually imported
    BEFORE staff exist; fill the HOD column later and import again with
    "Add and update". The HOD must be an active teacher of that department.
    """
    key = "departments"
    label = "departments"
    description = "Add departments, their short codes and HODs."
    file_stem = "departments"
    match_column = "name"
    match_label = "department name"

    columns = [
        F.Column("name", "Department name", "always", "Computer Science and Engineering",
                 "Exactly as it should appear everywhere. Subject and staff files use this name."),
        F.Column("code", "Code", False, "CSE",
                 "Short code, up to 10 letters (CSE, ECE, MATH). Every department needs a different code."),
        F.Column("hod", "HOD", False, "",
                 "Optional. The HOD's Employee ID, username or email. Must be a teacher of this department. "
                 "Leave empty if staff are not added yet."),
    ]

    def can_use(self, user):
        return can_manage_academics(user)

    def prepare(self, user, options=None):
        from core.users.models import User
        teachers = {}
        for t in User.objects.filter(role="teacher", is_active=True).select_related("department"):
            for v in (t.employee_id, t.username, t.email):
                if v:
                    teachers[str(v).strip().lower()] = t
        depts = list(Department.objects.all())
        return {
            "departments": {d.name.strip().lower(): d for d in depts},
            "codes": {d.code.strip().upper(): d for d in depts if d.code},
            "teachers": teachers,
        }

    def find_existing(self, values, ctx):
        return ctx["departments"].get(values.get("name", "").strip().lower())

    def row_title(self, values, existing):
        return values.get("name", "")

    def unique_in_file(self):
        return ["name", "code"]

    def check_lookups(self, values, existing, ctx):
        hod = str(values.get("hod") or "").strip()
        if hod and hod.lower() not in ctx["teachers"]:
            return [f"HOD '{hod}' is not an active teacher (check the Employee ID, username or email)."]
        return []

    def check_row(self, values, existing, ctx, user):
        problems = []
        name = values["name"].strip()
        if len(name) > 100:
            problems.append("Department name can be at most 100 characters.")
        payload = {"name": name}

        if values.get("code") not in (None, ""):
            code = str(values["code"]).strip().upper()
            owner = ctx["codes"].get(code)
            if len(code) > 10:
                problems.append("Code can be at most 10 characters.")
            elif owner is not None and (existing is None or owner.pk != existing.pk):
                problems.append(f"Code '{code}' already belongs to {owner.name}.")
            else:
                payload["code"] = code

        hod = str(values.get("hod") or "").strip()
        if hod:
            teacher = ctx["teachers"].get(hod.lower())
            if teacher is None:
                problems.extend(self.check_lookups(values, existing, ctx))
            else:
                if teacher.department_id and (existing is None or teacher.department_id != existing.pk):
                    problems.append(f"{teacher.get_full_name() or teacher.username} belongs to "
                                    f"{teacher.department.name}, not this department.")
                else:
                    payload["hod"] = teacher

        if problems:
            raise RowError(problems)
        return payload

    def save_row(self, payload, existing, ctx, user):
        dept = existing or Department(name=payload["name"])
        if "code" in payload:
            dept.code = payload["code"]
        if "hod" in payload:
            dept.hod = payload["hod"]
        dept.save()
        ctx["departments"][dept.name.strip().lower()] = dept
        if dept.code:
            ctx["codes"][dept.code] = dept
        return None

    def export_queryset(self, user, params, options=None):
        return Department.objects.select_related("hod").order_by("name")

    def export_row(self, d):
        hod = d.hod
        return {
            "name": d.name,
            "code": d.code or "",
            "hod": (hod.employee_id or hod.username) if hod else "",
        }


# ===================== SUBJECTS =====================
class SubjectImporter(Importer):
    key = "subjects"
    label = "subjects"
    description = "Add or update subjects for each course, year and semester."
    file_stem = "subjects"
    match_column = "name"
    match_label = "course, year, semester and subject name"

    columns = [
        F.course("always"),
        F.year("always"),
        F.semester("always"),
        F.Column("name", "Subject name", "always", "Engineering Graphics"),
        F.Column("code", "Subject code", False, "ME3101", "University subject code."),
        F.Column("credits", "Credits", False, "4", "0 to 30, whole or half (1.5).", F.parse_half(0, 30, "credits")),
        F.Column("weekly_hours", "Weekly hours", False, "5", "Periods per week, 0 to 20.", F.parse_int(0, 20, "weekly hours")),
        F.Column("is_elective", "Elective", False, "No", "Yes or No.", F.parse_choice(YES_NO, "answer", "Yes or No")),
        F.department(),
        # WAVE 3 PART 1A (CBCS)
        F.Column("category", "Category", False, "PCC", "Course category code, as in Credits and categories."),
        F.Column("kind", "Type", False, "Theory", "Theory, Practical or Project.",
                 F.parse_choice(SUBJECT_KIND, "type", "Theory, Practical or Project")),
        F.Column("lecture_hours", "L", False, "3", "Lecture hours a week, 0 to 20.", F.parse_int(0, 20, "L")),
        F.Column("tutorial_hours", "T", False, "1", "Tutorial hours a week, 0 to 20.", F.parse_int(0, 20, "T")),
        F.Column("practical_hours", "P", False, "0", "Practical hours a week, 0 to 40.", F.parse_int(0, 40, "P")),
        F.Column("regulation", "Regulation", False, "R2021", "Regulation name. Empty = the default regulation."),
    ]

    def can_use(self, user):
        return can_manage_academics(user)

    def unique_in_file(self):
        return []          # duplicates are checked on the full key in find_existing

    def prepare(self, user, options=None):
        return {
            "courses": F.Lookup(Course.objects.all(), "name", name="course"),
            "departments": F.Lookup(Department.objects.all(), "name", "code", name="department"),
            "years": {(y.course_id, y.year_number): y for y in Year.objects.all()},
            "subjects": {
                (s.year_id, s.semester, s.name.strip().lower()): s
                for s in Subject.objects.select_related("year")
            },
            "seen": set(),
            # WAVE 3 PART 1A
            "categories": {c.code.upper(): c for c in CourseCategory.objects.all()},
            "regulations": {r.name.upper(): r for r in Regulation.objects.all()},
        }

    def _year(self, values, ctx):
        course = ctx["courses"].find(values.get("course", ""))
        y = ctx["years"].get((course.id, values.get("year")))
        if y is None:
            raise F.CellError(f"{course.name} has no Year {values.get('year')}. Add the year to the course first.")
        return y

    def find_existing(self, values, ctx):
        if not all(k in values for k in ("course", "year", "semester", "name")):
            return None          # "required" checks report what's missing
        year = self._year(values, ctx)
        key = (year.id, values["semester"], values["name"].strip().lower())
        if key in ctx["seen"]:
            raise F.CellError("The same subject (course, year, semester and name) appears more than once in the file")
        ctx["seen"].add(key)
        return ctx["subjects"].get(key)

    def check_lookups(self, values, existing, ctx):
        msgs = []
        for key, lookup in (("course", "courses"), ("department", "departments")):
            if key in values:
                try:
                    ctx[lookup].find(values[key])
                except F.CellError as e:
                    msgs.append(str(e))
        try:
            F.semester_fits_year(values.get("year"), values.get("semester"))
        except F.CellError as e:
            msgs.append(str(e))
        return msgs

    def row_title(self, values, existing):
        return values.get("name", "")

    def check_row(self, values, existing, ctx, user):
        F.semester_fits_year(values["year"], values["semester"])
        data = {"year": self._year(values, ctx).id, "semester": values["semester"], "name": values["name"].strip()}
        for k in ("code", "credits", "weekly_hours", "is_elective",
                  "kind", "lecture_hours", "tutorial_hours", "practical_hours"):
            if k in values:
                data[k] = values[k]
        if "department" in values:
            data["department"] = ctx["departments"].find(values["department"]).id
        # WAVE 3 PART 1A: category and regulation by code / name
        problems = []
        if "category" in values:
            cat = ctx["categories"].get(str(values["category"]).strip().upper())
            if cat is None:
                problems.append(f"Category '{values['category']}' does not exist. Add it in Credits and categories.")
            else:
                data["category"] = cat.id
        if "regulation" in values:
            reg = ctx["regulations"].get(str(values["regulation"]).strip().upper())
            if reg is None:
                problems.append(f"Regulation '{values['regulation']}' does not exist.")
            else:
                data["regulation"] = reg.id
        if problems:
            raise RowError(problems)
        from core.academics.serializers import SubjectSerializer
        s = SubjectSerializer(existing, data=data, partial=existing is not None)
        if not s.is_valid():
            raise RowError(_serializer_errors(s.errors))
        return data

    def save_row(self, payload, existing, ctx, user):
        from core.academics.serializers import SubjectSerializer
        s = SubjectSerializer(existing, data=payload, partial=existing is not None)
        if not s.is_valid():
            raise RowError(_serializer_errors(s.errors))
        s.save()
        return None

    def export_queryset(self, user, params, options=None):
        qs = Subject.objects.select_related("year__course", "department", "category", "regulation").order_by(
            "year__course__name", "year__year_number", "semester", "name")
        if params.get("course"):
            qs = qs.filter(year__course_id=params["course"])
        if params.get("semester"):
            qs = qs.filter(semester=params["semester"])
        return qs

    def export_row(self, s):
        return {
            "course": s.year.course.name,
            "year": s.year.year_number,
            "semester": s.semester,
            "name": s.name,
            "code": s.code or "",
            "credits": f"{s.credits:g}",
            "weekly_hours": s.weekly_hours,
            "is_elective": "Yes" if s.is_elective else "No",
            "department": s.department.name if s.department else "",
            "category": s.category.code if s.category_id else "",
            "kind": s.get_kind_display(),
            "lecture_hours": s.lecture_hours,
            "tutorial_hours": s.tutorial_hours,
            "practical_hours": s.practical_hours,
            "regulation": s.regulation.name if s.regulation_id else "",
        }


# ===================== TEACHING ASSIGNMENTS =====================
class TeachingAssignmentImporter(Importer):
    """
    Who teaches which subject to which class. One row per teacher + subject.
    The same subject can have more than one teacher (labs), exactly like the
    database rule (unique_teaching_assignment = teacher + course + year +
    subject). Rows that already exist are skipped, never duplicated.
    Enrollments are NOT created here - use "Generate enrollments" after
    importing, the same as after adding assignments by hand.
    """
    key = "teaching_assignments"
    label = "teaching assignments"
    description = "Which teacher takes which subject for each class."
    file_stem = "teaching-assignments"
    match_column = "subject"
    match_label = "teacher, course, year and subject"
    modes = ("upsert",)

    columns = [
        F.course("always"),
        F.year("always"),
        F.semester("always"),
        F.Column("subject", "Subject", "always", "ME3101",
                 "Subject code or name, exactly as in Subjects for that course, year and semester."),
        F.Column("teacher", "Teacher", "always", "TCH001",
                 "The teacher's Employee ID, username or email."),
        F.Column("teacher_name", "Teacher name", False, "Priya R", "For your reference only - not saved."),
    ]

    def can_use(self, user):
        return can_manage_academics(user)

    def unique_in_file(self):
        return []          # duplicates are checked on the full key in find_existing

    def prepare(self, user, options=None):
        from core.academics.models import TeachingAssignment
        from core.users.models import User

        teachers = {}
        for t in User.objects.filter(role="teacher", is_active=True):
            for v in (t.employee_id, t.username, t.email):
                if v:
                    teachers[str(v).strip().lower()] = t
        subjects = {}
        for sub in Subject.objects.select_related("year"):
            for v in (sub.code, sub.name):
                if v:
                    subjects.setdefault((sub.year_id, sub.semester, str(v).strip().lower()), sub)
        return {
            "courses": F.Lookup(Course.objects.all(), "name", name="course"),
            "years": {(y.course_id, y.year_number): y for y in Year.objects.all()},
            "teachers": teachers,
            "subjects": subjects,
            "existing": {(ta.teacher_id, ta.course_id, ta.year_id, ta.subject_id): ta
                         for ta in TeachingAssignment.objects.all()},
            "seen": set(),
        }

    def _resolve(self, values, ctx):
        course = ctx["courses"].find(values.get("course", ""))
        year = ctx["years"].get((course.id, values.get("year")))
        if year is None:
            raise F.CellError(f"{course.name} has no Year {values.get('year')}")
        F.semester_fits_year(values.get("year"), values.get("semester"))
        subject = ctx["subjects"].get((year.id, values["semester"], values["subject"].strip().lower()))
        if subject is None:
            raise F.CellError(f"Subject '{values['subject']}' not found in {course.name} "
                              f"Year {values['year']}, Semester {values['semester']}")
        teacher = ctx["teachers"].get(values["teacher"].strip().lower())
        if teacher is None:
            raise F.CellError(f"Teacher '{values['teacher']}' not found (use Employee ID, username or email "
                              f"of an active teacher)")
        return course, year, subject, teacher

    def find_existing(self, values, ctx):
        if not all(k in values for k in ("course", "year", "semester", "subject", "teacher")):
            return None
        course, year, subject, teacher = self._resolve(values, ctx)
        key = (teacher.id, course.id, year.id, subject.id)
        if key in ctx["seen"]:
            raise F.CellError("The same teacher and subject appear more than once in the file")
        ctx["seen"].add(key)
        return ctx["existing"].get(key)

    def row_title(self, values, existing):
        return f"{values.get('subject', '')} - {values.get('teacher_name') or values.get('teacher', '')}"

    def check_row(self, values, existing, ctx, user):
        if existing is not None:
            return SKIP                       # already assigned - nothing to change
        course, year, subject, teacher = self._resolve(values, ctx)
        return {"teacher": teacher, "course": course, "year": year, "subject": subject}

    def save_row(self, payload, existing, ctx, user):
        from core.academics.models import TeachingAssignment
        ta = TeachingAssignment(**payload)
        ta.clean()                            # year belongs to course, subject to year
        ta.save()
        return None

    def template_example(self):
        return [["B.E Mechanical", "2", "3", "ME3101", "TCH001", "Priya R"]]

    def export_queryset(self, user, params, options=None):
        from core.academics.models import TeachingAssignment
        qs = TeachingAssignment.objects.select_related("course", "year", "subject", "teacher").order_by(
            "course__name", "year__year_number", "subject__semester", "subject__name")
        if params.get("course"):
            qs = qs.filter(course_id=params["course"])
        if params.get("year"):
            qs = qs.filter(year_id=params["year"])
        return qs

    def export_row(self, ta):
        t = ta.teacher
        return {
            "course": ta.course.name,
            "year": ta.year.year_number,
            "semester": ta.subject.semester,
            "subject": ta.subject.code or ta.subject.name,
            "teacher": t.employee_id or t.username,
            "teacher_name": (t.get_full_name() or "").strip() or t.username,
        }


register(DepartmentImporter())
register(CourseImporter())
register(SubjectImporter())
register(TeachingAssignmentImporter())