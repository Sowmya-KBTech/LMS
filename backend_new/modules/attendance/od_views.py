# On-Duty (OD) requests: student apply, tutor + HOD approval.
# Moved here from users/views.py so that `users` (core) no longer depends on attendance.
# URLs are unchanged (/api/users/od/...) - see attendance/users_urls.py.
# ===================== IMPORTS =====================

from django.utils import timezone

from rest_framework.decorators import (api_view, permission_classes)
from rest_framework.response import Response
from rest_framework.permissions import (IsAuthenticated)

from core.users.models import (User, Department)
from core.users.views import _tutor_student_ids
from core.notifications.services import notify, notify_parents   # FIX #11


def _d(x):
    return x.strftime("%d-%m-%Y") if x else ""


def _od_text(od):
    """'Paper presentation · 29-10-2026' or '... 29-10-2026 to 30-10-2026'"""
    kind = od.get_category_display()
    if od.from_date == od.to_date:
        return f"{kind} · {_d(od.from_date)}"
    return f"{kind} · {_d(od.from_date)} to {_d(od.to_date)}"


def _tutors_of(student):
    """Class tutor(s) of this student's course + year."""
    from core.academics.models import YearTutor
    return [t.teacher for t in YearTutor.objects.filter(
        course_id=student.course_id, year__year_number=student.year
    ).select_related("teacher")]


def _hod_of(student):
    # #50 ACTING HOD: the current HOD of the student's department
    from core.users.acting_hod import current_hod
    dept = getattr(student, "department", None)
    return current_hod(dept) if dept else None


def _hod_student_ids(user):
    """Student ids in this HOD's department(s). Matches my_department scoping."""
    from core.users.acting_hod import hod_department_ids   # #50 ACTING HOD
    dept_ids = hod_department_ids(user)
    return User.objects.filter(
        role="student", department_id__in=dept_ids
    ).values_list("id", flat=True)


def _mark_od_attendance(od):
    """HOD approval -> set existing attendance rows in range to duty_leave."""
    from modules.attendance.models import Attendance
    Attendance.objects.filter(
        student=od.student,
        date__gte=od.from_date,
        date__lte=od.to_date,
    ).update(status="duty_leave", marked_by=od.hod_reviewed_by)


# ?show=decided on the review lists: the latest requests this reviewer already decided
DECIDED_LIMIT = 100


# ---------- Student ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def od_create(request):
    from modules.attendance.serializers import ODRequestSerializer
    ser = ODRequestSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    od = ser.save(student=request.user)
    # FIX #11: the class tutor gets it first
    notify(_tutors_of(request.user), f"On-duty request from {request.user.username}",
           f"{_od_text(od)}. Reason: {od.reason[:120]}",
           "od", link="/my-class?tab=requests")
    return Response(ser.data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def od_my_requests(request):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    qs = ODRequest.objects.filter(student=request.user)
    return Response(ODRequestSerializer(qs, many=True, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def od_cancel(request, pk):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    try:
        od = ODRequest.objects.get(pk=pk, student=request.user)
    except ODRequest.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)
    if od.status != ODRequest.Status.PENDING:
        return Response({"detail": "Only pending requests can be cancelled."}, status=400)
    od.status = ODRequest.Status.CANCELLED
    od.stage = ODRequest.Stage.CLOSED
    od.save(update_fields=["status", "stage"])
    return Response(ODRequestSerializer(od, context={"request": request}).data)


# ---------- Tutor ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tutor_od_pending(request):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    students = list(_tutor_student_ids(request.user))
    if request.query_params.get("show") == "decided":      # Student requests -> Already decided
        qs = (ODRequest.objects.filter(student_id__in=students, tutor_reviewed_at__isnull=False)
              .select_related("student").order_by("-tutor_reviewed_at")[:DECIDED_LIMIT])
    else:
        qs = ODRequest.objects.filter(
            student_id__in=students,
            stage=ODRequest.Stage.AWAITING_TUTOR,
            status=ODRequest.Status.PENDING,
        )
    return Response(ODRequestSerializer(qs, many=True, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tutor_od_action(request, pk):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    action = request.data.get("action")
    remark = request.data.get("remark", "")
    try:
        od = ODRequest.objects.get(
            pk=pk,
            student_id__in=list(_tutor_student_ids(request.user)),
            stage=ODRequest.Stage.AWAITING_TUTOR,
            status=ODRequest.Status.PENDING,
        )
    except ODRequest.DoesNotExist:
        return Response({"detail": "Not found or not yours to review."}, status=404)
    if action not in ("approve", "reject"):
        return Response({"detail": "action must be approve or reject."}, status=400)
    od.tutor_reviewed_by = request.user
    od.tutor_remark = remark
    od.tutor_reviewed_at = timezone.now()
    if action == "approve":
        od.stage = ODRequest.Stage.AWAITING_HOD
    else:
        od.status = ODRequest.Status.REJECTED
        od.stage = ODRequest.Stage.CLOSED
    od.save()

    # FIX #11
    s = od.student
    if action == "approve":
        notify([_hod_of(s)], f"Student on-duty request from {s.username}",
               f"{_od_text(od)}. Forwarded by class in-charge {request.user.username}.",
               "od", link="/my-department?tab=requests")
        notify([s], "On-duty request forwarded to HOD",
               f"{_od_text(od)} was approved by your class in-charge and sent to the HOD.",
               "od", link="/student/attendance?tab=onduty")
    else:
        notify([s], "On-duty request rejected",
               f"{_od_text(od)} was rejected by your class in-charge."
               + (f" Remark: {remark}" if remark else ""),
               "od", link="/student/attendance?tab=onduty")
    return Response(ODRequestSerializer(od, context={"request": request}).data)


# ---------- HOD ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_od_pending(request):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    students = list(_hod_student_ids(request.user))
    if request.query_params.get("show") == "decided":      # Student requests -> Already decided
        qs = (ODRequest.objects.filter(student_id__in=students, hod_reviewed_at__isnull=False)
              .select_related("student").order_by("-hod_reviewed_at")[:DECIDED_LIMIT])
    else:
        qs = ODRequest.objects.filter(
            student_id__in=students,
            stage=ODRequest.Stage.AWAITING_HOD,
            status=ODRequest.Status.PENDING,
        )
    return Response(ODRequestSerializer(qs, many=True, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_od_action(request, pk):
    from modules.attendance.models import ODRequest
    from modules.attendance.serializers import ODRequestSerializer
    action = request.data.get("action")
    remark = request.data.get("remark", "")
    try:
        od = ODRequest.objects.get(
            pk=pk,
            student_id__in=list(_hod_student_ids(request.user)),
            stage=ODRequest.Stage.AWAITING_HOD,
            status=ODRequest.Status.PENDING,
        )
    except ODRequest.DoesNotExist:
        return Response({"detail": "Not found or not yours to review."}, status=404)
    if action not in ("approve", "reject"):
        return Response({"detail": "action must be approve or reject."}, status=400)
    od.hod_reviewed_by = request.user
    od.hod_remark = remark
    od.hod_reviewed_at = timezone.now()
    if action == "approve":
        od.status = ODRequest.Status.APPROVED
        od.stage = ODRequest.Stage.CLOSED
        _mark_od_attendance(od)
    else:
        od.status = ODRequest.Status.REJECTED
        od.stage = ODRequest.Stage.CLOSED
    od.save()

    # FIX #11: final decision -> student and parents
    s = od.student
    if action == "approve":
        notify([s], "On-duty approved",
               f"{_od_text(od)} was approved. Those classes count as present.",
               "od", link="/student/attendance?tab=onduty")
        notify_parents(s, "On-duty approved",
                       f"{s.username}: {_od_text(od)} was approved by the HOD.",
                       "od", link="/parent/attendance")
    else:
        notify([s], "On-duty request rejected",
               f"{_od_text(od)} was rejected by the HOD."
               + (f" Remark: {remark}" if remark else ""),
               "od", link="/student/attendance?tab=onduty")
    return Response(ODRequestSerializer(od, context={"request": request}).data)
