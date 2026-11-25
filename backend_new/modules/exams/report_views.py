"""
WAVE 1 - PROGRESS REPORTS AND RANK LISTS.

  GET /api/reports/classes/                         classes this user may rank (with semesters)
  GET /api/reports/rank-list/?course=&year=&semester=
                                                    one class, one semester (published results)
  GET /api/reports/progress/<student_id>/           one student's progress report
  GET /api/reports/progress/me/                     the signed-in student's own report

Rank rules (the usual university practice)
  * from PUBLISHED semester results only
  * percentage = total marks obtained / total maximum marks
  * only students who cleared EVERY subject get a rank; equal percentages share
    a rank and the next rank is skipped (1, 2, 2, 4)
  * students with arrears are listed after the ranked ones, without a rank

Who may see what
  rank list        the class in-charge of that class, the HOD of the department,
                   the Principal, college admins
  progress report  the student, their parent, their class in-charge, their
                   current mentor, their HOD, the Principal, college admins
"""
from collections import defaultdict

from django.apps import apps
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import is_college_admin
from core.users.models import User

from .models import IAMark, SemesterResult

TOP_PER_SUBJECT = 3

# sub-admins who may see every class: the main admin, exam and academic admins
# (an accounts or placement admin has no business with marks)
REPORT_SUB_ROLES = ("", "exam_admin", "academic_admin")


def _report_admin(user):
    if is_college_admin(user) and (user.is_superuser or (user.sub_role or "") in REPORT_SUB_ROLES):
        return True
    # WAVE 2: the Principal sees every class and every student's report
    from core.users.principal import is_principal
    return is_principal(user)


# ---------------------------------------------------------------- who is who
def _tutor_classes(user):
    from core.academics.models import YearTutor
    return {(t.course_id, t.year.year_number)
            for t in YearTutor.objects.filter(teacher=user).select_related("year")}


def _hod_dept_ids(user):
    if getattr(user, "role", None) != "teacher":
        return set()
    from core.users.acting_hod import hod_department_ids
    return set(hod_department_ids(user))


def _class_students(course_id, year):
    return User.objects.filter(role="student", course_id=course_id, year=year)


def _can_rank(user, course_id, year):
    if _report_admin(user):
        return True
    if (course_id, year) in _tutor_classes(user):
        return True
    depts = _hod_dept_ids(user)
    return bool(depts) and _class_students(course_id, year).filter(department_id__in=depts).exists()


def _can_see_student(user, student):
    if user.id == student.id or _report_admin(user):
        return True
    role = getattr(user, "role", None)
    if role == "parent":
        profile = getattr(user, "parent_profile", None)
        return profile is not None and profile.children.filter(id=student.id).exists()
    if role != "teacher":
        return False
    if (student.course_id, student.year) in _tutor_classes(user):
        return True
    if student.department_id in _hod_dept_ids(user):
        return True
    if apps.is_installed("modules.mentoring"):
        from modules.mentoring.models import MentorAllocation
        if MentorAllocation.objects.filter(student=student, mentor=user, is_active=True).exists():
            return True
    return False


# ---------------------------------------------------------------- rank list core
def _pct(obtained, maximum):
    return round(obtained * 100.0 / maximum, 2) if maximum else 0.0


def _rank_rows(course_id, year, semester):
    """Rows for one class + semester, ranked. Also returns per-subject toppers."""
    students = {s.id: s for s in _class_students(course_id, year)}
    results = (SemesterResult.objects
               .filter(student_id__in=students, semester=semester, is_published=True)
               .prefetch_related("entries__subject"))
    rows, by_subject = [], defaultdict(list)
    for sr in results:
        s = students[sr.student_id]
        obtained = maximum = arrears = 0
        for e in sr.entries.all():
            obtained += e.marks_obtained or 0
            maximum += e.max_marks or 0
            if not e.is_pass:
                arrears += 1
            if e.marks_obtained is not None and e.subject_id:
                by_subject[(e.subject_id, e.subject.name, getattr(e.subject, "code", "") or "")].append(
                    (e.marks_obtained, e.max_marks, s))
        rows.append({
            "student_id": s.id, "name": s.get_full_name() or s.username, "username": s.username,
            "roll_number": s.roll_number or "", "total": round(obtained, 2), "max": maximum,
            "percentage": _pct(obtained, maximum), "arrears": arrears, "rank": None,
        })

    cleared = sorted([r for r in rows if r["arrears"] == 0], key=lambda r: (-r["percentage"], r["roll_number"]))
    previous, rank = None, 0
    for position, r in enumerate(cleared, start=1):
        if r["percentage"] != previous:
            rank, previous = position, r["percentage"]
        r["rank"] = rank
    with_arrears = sorted([r for r in rows if r["arrears"]], key=lambda r: (r["arrears"], -r["percentage"]))

    toppers = []
    for (sid, name, code), marks in sorted(by_subject.items(), key=lambda kv: kv[0][1].lower()):
        marks.sort(key=lambda m: -m[0])
        cut = marks[min(TOP_PER_SUBJECT, len(marks)) - 1][0] if marks else None
        top = [m for m in marks if m[0] >= cut][:TOP_PER_SUBJECT + 2]          # ties at the cut stay
        toppers.append({"subject": name, "code": code, "top": [
            {"name": m[2].get_full_name() or m[2].username, "roll_number": m[2].roll_number or "",
             "marks": m[0], "max": m[1]} for m in top]})
    return cleared + with_arrears, toppers


def _semesters_for(course_id, year):
    return sorted(set(SemesterResult.objects
                      .filter(student__in=_class_students(course_id, year), is_published=True)
                      .values_list("semester", flat=True)))


# ---------------------------------------------------------------- endpoints
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_classes(request):
    """The classes this user may rank, each with the semesters that have published results."""
    from core.academics.models import Course
    user = request.user
    pairs = set()
    if _report_admin(user):
        pairs = set(User.objects.filter(role="student", course__isnull=False, year__isnull=False)
                    .values_list("course_id", "year").distinct())
    else:
        pairs |= _tutor_classes(user)
        depts = _hod_dept_ids(user)
        if depts:
            pairs |= set(User.objects.filter(role="student", department_id__in=depts,
                                             course__isnull=False, year__isnull=False)
                         .values_list("course_id", "year").distinct())
    names = dict(Course.objects.filter(id__in={c for c, _ in pairs}).values_list("id", "name"))
    out = [{"course": c, "course_name": names.get(c, ""), "year": y, "semesters": _semesters_for(c, y)}
           for c, y in pairs]
    out.sort(key=lambda r: (r["course_name"].lower(), r["year"]))
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rank_list(request):
    try:
        course_id = int(request.query_params.get("course"))
        year = int(request.query_params.get("year"))
        semester = int(request.query_params.get("semester"))
    except (TypeError, ValueError):
        return Response({"detail": "Choose a class and a semester."}, status=400)
    if not _can_rank(request.user, course_id, year):
        return Response({"detail": "You can't see the rank list of this class."}, status=403)

    rows, toppers = _rank_rows(course_id, year, semester)
    appeared = len(rows)
    cleared = sum(1 for r in rows if r["arrears"] == 0)
    from core.academics.models import Course
    course = Course.objects.filter(id=course_id).first()
    return Response({
        "course": course_id, "course_name": course.name if course else "", "year": year,
        "semester": semester,
        "summary": {
            "appeared": appeared, "all_clear": cleared,
            "pass_percentage": _pct(cleared, appeared),
            "class_average": round(sum(r["percentage"] for r in rows) / appeared, 2) if appeared else 0.0,
        },
        "rows": rows, "toppers": toppers,
    })


def _attendance_block(student):
    """This semester's attendance by subject (present + on duty count as attended)."""
    if not apps.is_installed("modules.attendance"):
        return None
    from modules.attendance.models import Attendance
    qs = (Attendance.objects.filter(student=student)
          .select_related("teaching_assignment__subject"))
    if student.semester:
        qs = qs.filter(teaching_assignment__subject__semester=student.semester)
    per = defaultdict(lambda: {"present": 0, "duty": 0, "absent": 0})
    names = {}
    for a in qs:
        subj = a.teaching_assignment.subject
        key = subj.id if subj else 0
        names[key] = (subj.name, getattr(subj, "code", "") or "") if subj else ("Other", "")
        if a.status == "present":
            per[key]["present"] += 1
        elif a.status == "duty_leave":
            per[key]["duty"] += 1
        else:
            per[key]["absent"] += 1
    subjects, tot_att, tot = [], 0, 0
    for key, c in per.items():
        total = c["present"] + c["duty"] + c["absent"]
        attended = c["present"] + c["duty"]
        tot_att += attended
        tot += total
        subjects.append({"subject": names[key][0], "code": names[key][1], "attended": attended,
                         "total": total, "on_duty": c["duty"], "percentage": _pct(attended, total)})
    subjects.sort(key=lambda r: r["subject"].lower())
    leave_days = 0
    if apps.is_installed("modules.attendance"):
        from modules.attendance.models import StudentLeaveRequest
        leave_days = sum(lv.days for lv in StudentLeaveRequest.objects.filter(
            student=student, status=StudentLeaveRequest.Status.APPROVED))
    return {"subjects": subjects, "attended": tot_att, "total": tot,
            "percentage": _pct(tot_att, tot), "approved_leave_days": leave_days}


def _ia_block(student):
    """Declared (locked) IA marks, by subject."""
    marks = (IAMark.objects.filter(student=student, assessment__is_locked=True)
             .select_related("assessment__teaching_assignment__subject"))
    per = {}
    for m in marks:
        subj = m.assessment.teaching_assignment.subject
        row = per.setdefault(subj.id, {"subject": subj.name, "code": getattr(subj, "code", "") or "",
                                       "semester": subj.semester, "tests": {}})
        row["tests"][m.assessment.number] = {
            "obtained": None if m.is_absent else m.marks_obtained,
            "absent": m.is_absent, "max": m.assessment.max_marks}
    rows = sorted(per.values(), key=lambda r: (-r["semester"], r["subject"].lower()))
    for r in rows:
        r["tests"] = [{"number": n, **v} for n, v in sorted(r["tests"].items())]
    return rows


def _results_block(student):
    out = []
    for sr in (SemesterResult.objects.filter(student=student, is_published=True)
               .prefetch_related("entries__subject").order_by("semester")):
        entries, obtained, maximum, arrears = [], 0, 0, 0
        for e in sr.entries.all():
            obtained += e.marks_obtained or 0
            maximum += e.max_marks or 0
            arrears += 0 if e.is_pass else 1
            entries.append({"subject": e.subject.name if e.subject else "", "code":
                            (getattr(e.subject, "code", "") or "") if e.subject else "",
                            "obtained": e.marks_obtained, "max": e.max_marks,
                            "grade": e.grade, "is_pass": e.is_pass})
        rank = class_size = None
        if student.course_id and student.year:
            rows, _ = _rank_rows(student.course_id, student.year, sr.semester)
            class_size = len(rows)
            mine = next((r for r in rows if r["student_id"] == student.id), None)
            rank = mine["rank"] if mine else None
        out.append({"semester": sr.semester, "entries": entries, "total": round(obtained, 2),
                    "max": maximum, "percentage": _pct(obtained, maximum), "arrears": arrears,
                    "rank": rank, "class_size": class_size})
    return out


def _report(student):
    course = getattr(student, "course", None)
    dept = getattr(student, "department", None)
    results = _results_block(student)
    total_obt = sum(r["total"] for r in results)
    total_max = sum(r["max"] for r in results)
    return {
        "student": {
            "id": student.id, "name": student.get_full_name() or student.username,
            "username": student.username, "roll_number": student.roll_number or "",
            "course": course.name if course else "", "department": dept.name if dept else "",
            "year": student.year, "semester": student.semester,
        },
        "attendance": _attendance_block(student),
        "internal_assessments": _ia_block(student),
        "semester_results": results,
        "overall": {"percentage": _pct(total_obt, total_max),
                    "arrears": sum(r["arrears"] for r in results),
                    "semesters": len(results)},
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def progress_report(request, student_id):
    student = User.objects.filter(id=student_id, role="student").select_related(
        "course", "department").first()
    if student is None or not _can_see_student(request.user, student):
        return Response({"detail": "Report not found."}, status=404)
    return Response(_report(student))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_progress_report(request):
    if getattr(request.user, "role", None) != "student":
        return Response({"detail": "Only students have their own progress report."}, status=403)
    return Response(_report(request.user))
