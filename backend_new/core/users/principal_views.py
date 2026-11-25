"""
WAVE 2 - PRINCIPAL endpoints (all under /api/users/).

  GET  principal/                current Principal + past terms (anyone signed in sees
                                 the current one; the main admin also gets history)
  GET  principal/candidates/     main admin: active teachers to choose from
  POST principal/assign/         main admin: {"teacher": id}  (ends the current term)
  POST principal/end/            main admin: end the current term
  GET  principal/dashboard/      the Principal (or the main admin): the whole college
                                 at a glance, department by department

The dashboard only reads data. Every number is limited to modules the college
has switched on.
"""
from collections import defaultdict
from datetime import timedelta

from django.apps import apps
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.notifications.services import notify
from core.users import principal as P
from core.users.acting_hod import current_hod, is_main_admin
from core.users.models import Department, PrincipalTerm, User

LOW_ATTENDANCE = 75.0
HOD_LEAVE_AHEAD_DAYS = 30


def _name(u):
    return (u.get_full_name() or u.username) if u else ""


def _term(t):
    return {"id": t.id, "teacher_id": t.teacher_id, "name": _name(t.teacher),
            "department": t.teacher.department.name if t.teacher.department_id else "",
            "start_date": t.start_date, "end_date": t.end_date, "is_current": t.is_current}


def _pct(a, b):
    return round(a * 100.0 / b, 1) if b else None


# ---------------------------------------------------------------- assignment
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def principal_info(request):
    term = P.current_term()
    data = {"current": _term(term) if term else None,
            "is_me": bool(term and term.teacher_id == request.user.id),
            "can_manage": is_main_admin(request.user)}
    if data["can_manage"]:
        data["history"] = [_term(t) for t in PrincipalTerm.objects.filter(is_current=False)
                           .select_related("teacher__department")[:20]]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def principal_candidates(request):
    if not is_main_admin(request.user):
        return Response({"detail": "Only the main admin can choose the Principal."}, status=403)
    qs = (User.objects.filter(role="teacher", is_active=True).select_related("department")
          .order_by("first_name", "username"))
    return Response([{"id": u.id, "name": _name(u), "username": u.username,
                      "department": u.department.name if u.department_id else ""} for u in qs])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def principal_assign(request):
    if not is_main_admin(request.user):
        return Response({"detail": "Only the main admin can choose the Principal."}, status=403)
    old = P.current_principal()
    try:
        term = P.assign(request.data.get("teacher"), request.user)
    except P.PrincipalError as e:
        return Response({"detail": str(e)}, status=400)
    notify([term.teacher], "You are now the Principal",
           "The admin has made you the college Principal. Your college overview is ready.",
           "announcement", link="/principal")
    if old and old.id != term.teacher_id:
        notify([old], "Principal term ended",
               f"{_name(term.teacher)} is now the Principal.", "announcement", link="/notifications")
    return Response(_term(term), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def principal_end(request):
    if not is_main_admin(request.user):
        return Response({"detail": "Only the main admin can end the Principal's term."}, status=403)
    try:
        term = P.end_current(request.user)
    except P.PrincipalError as e:
        return Response({"detail": str(e)}, status=400)
    notify([term.teacher], "Principal term ended",
           "The admin has ended your term as Principal.", "announcement", link="/notifications")
    return Response(_term(term))


# ---------------------------------------------------------------- dashboard parts
def _attendance_today(today):
    """{dept_id: [marked, attended]} for today's register, and the low-attendance count."""
    today_by, low_by = defaultdict(lambda: [0, 0]), defaultdict(int)
    if not apps.is_installed("modules.attendance"):
        return today_by, low_by, False
    from modules.attendance.models import Attendance

    for dept_id, status, n in (Attendance.objects.filter(date=today)
                               .values_list("student__department_id", "status")
                               .annotate(n=Count("id"))):
        today_by[dept_id][0] += n
        if status in ("present", "duty_leave"):
            today_by[dept_id][1] += n

    # this semester, per student: attended / marked (only the student's current semester)
    per_student = defaultdict(lambda: [0, 0, None])
    rows = (Attendance.objects
            .filter(student__role="student", student__is_active=True,
                    teaching_assignment__subject__semester=F("student__semester"))
            .values_list("student_id", "student__department_id", "status")
            .annotate(n=Count("id")))
    for sid, dept_id, status, n in rows:
        rec = per_student[sid]
        rec[2] = dept_id
        rec[1] += n
        if status in ("present", "duty_leave"):
            rec[0] += n
    for attended, total, dept_id in per_student.values():
        if total and attended * 100.0 / total < LOW_ATTENDANCE:
            low_by[dept_id] += 1
    return today_by, low_by, True


def _pending():
    """Requests waiting at HOD level, by department."""
    out = defaultdict(lambda: {"od": 0, "student_leave": 0, "staff_leave": 0})
    if not apps.is_installed("modules.attendance"):
        return out
    from modules.attendance.models import ODRequest, StaffLeaveRequest, StudentLeaveRequest

    for dept_id, n in (ODRequest.objects.filter(status="pending", stage="awaiting_hod")
                       .values_list("student__department_id").annotate(n=Count("id"))):
        out[dept_id]["od"] += n
    for dept_id, n in (StudentLeaveRequest.objects.filter(status="pending", stage="awaiting_hod")
                       .values_list("student__department_id").annotate(n=Count("id"))):
        out[dept_id]["student_leave"] += n
    for dept_id, n in (StaffLeaveRequest.objects.filter(status="pending", level="hod")
                       .values_list("department_id").annotate(n=Count("id"))):
        out[dept_id]["staff_leave"] += n
    return out


def _staff_leave(today):
    """Who is on leave today, and HOD leave coming up."""
    if not apps.is_installed("modules.attendance"):
        return [], [], False
    from modules.attendance.models import StaffLeaveRequest
    taken = [StaffLeaveRequest.Status.APPROVED, StaffLeaveRequest.Status.RECORDED]
    hod_ids = set(Department.objects.exclude(hod=None).values_list("hod_id", flat=True))

    def row(lv):
        return {"id": lv.id, "teacher": _name(lv.teacher), "teacher_id": lv.teacher_id,
                "department": lv.department.name if lv.department_id else "",
                "department_id": lv.department_id, "type": lv.get_leave_type_display(),
                "session": lv.get_session_display(), "from_date": lv.from_date, "to_date": lv.to_date,
                "is_hod": lv.teacher_id in hod_ids, "backup": _name(lv.backup) if lv.backup_id else ""}

    base = StaffLeaveRequest.objects.filter(status__in=taken).select_related("teacher", "department", "backup")
    today_rows = [row(lv) for lv in base.filter(from_date__lte=today, to_date__gte=today)
                  .order_by("department__name", "teacher__username")]
    ahead = today + timedelta(days=HOD_LEAVE_AHEAD_DAYS)
    hod_rows = [row(lv) for lv in base.filter(teacher_id__in=hod_ids, to_date__gte=today, from_date__lte=ahead)
                .order_by("from_date")]
    return today_rows, hod_rows, True


def _results():
    """Published results by department: student-semesters appeared / cleared everything."""
    out = defaultdict(lambda: [0, 0])
    if not apps.is_installed("modules.exams"):
        return out, False
    from modules.exams.models import SemesterResult
    rows = (SemesterResult.objects.filter(is_published=True)
            .annotate(fails=Count("entries", filter=Q(entries__is_pass=False)))
            .values_list("student__department_id", "fails"))
    for dept_id, fails in rows:
        out[dept_id][0] += 1
        if not fails:
            out[dept_id][1] += 1
    return out, True


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def principal_dashboard(request):
    user = request.user
    if not (P.is_principal(user) or is_main_admin(user)):
        return Response({"detail": "The college overview is for the Principal."}, status=403)

    today = timezone.localdate()
    depts = list(Department.objects.select_related("hod").order_by("name"))
    students = dict(User.objects.filter(role="student", is_active=True).values_list("department_id")
                    .annotate(n=Count("id")))
    teachers = dict(User.objects.filter(role="teacher", is_active=True).values_list("department_id")
                    .annotate(n=Count("id")))
    today_by, low_by, has_att = _attendance_today(today)
    pending = _pending()
    on_leave, hod_leave, has_leave = _staff_leave(today)
    results, has_results = _results()
    leave_count = defaultdict(int)
    for r in on_leave:
        leave_count[r["department_id"]] += 1

    rows = []
    for d in depts:
        marked, attended = today_by[d.id]
        hod = current_hod(d)
        appeared, cleared = results[d.id]
        p = pending[d.id]
        rows.append({
            "id": d.id, "name": d.name, "code": d.code or "",
            "hod": _name(hod), "hod_is_acting": bool(hod and d.hod_id != hod.id),
            "students": students.get(d.id, 0), "teachers": teachers.get(d.id, 0),
            "attendance_today": {"marked": marked, "attended": attended, "percentage": _pct(attended, marked)},
            "low_attendance": low_by[d.id],
            "staff_on_leave": leave_count[d.id],
            "pending": {**p, "total": p["od"] + p["student_leave"] + p["staff_leave"]},
            "results": {"appeared": appeared, "all_clear": cleared, "pass_percentage": _pct(cleared, appeared)},
        })

    t_marked = sum(r["attendance_today"]["marked"] for r in rows)
    t_att = sum(r["attendance_today"]["attended"] for r in rows)
    t_app = sum(r["results"]["appeared"] for r in rows)
    t_clear = sum(r["results"]["all_clear"] for r in rows)
    term = P.current_term()
    return Response({
        "today": today,
        "principal": _term(term) if term else None,
        "modules": {"attendance": has_att, "leave": has_leave, "results": has_results},
        "totals": {
            "departments": len(rows),
            "students": sum(students.values()), "teachers": sum(teachers.values()),
            "attendance_today": {"marked": t_marked, "attended": t_att, "percentage": _pct(t_att, t_marked)},
            "low_attendance": sum(r["low_attendance"] for r in rows),
            "staff_on_leave": len(on_leave),
            "pending": sum(r["pending"]["total"] for r in rows),
            "results": {"appeared": t_app, "all_clear": t_clear, "pass_percentage": _pct(t_clear, t_app)},
        },
        "departments": rows,
        "on_leave_today": on_leave,
        "hod_leave_upcoming": hod_leave,
    })
