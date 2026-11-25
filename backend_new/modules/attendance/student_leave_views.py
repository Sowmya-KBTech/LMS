"""
WAVE 1 - STUDENT LEAVE: student applies, class in-charge then HOD approve.

Same road as student on duty (od_views.py), same URLs style (/api/users/...):

  POST /api/users/leave/create/              student applies (multipart: proof optional)
  GET  /api/users/leave/                     student: my requests
  POST /api/users/leave/<id>/cancel/         student: cancel a pending one
  GET  /api/users/tutor/leave/               class in-charge: waiting for me
  POST /api/users/tutor/leave/<id>/action/   approve / reject (reject needs a remark)
  GET  /api/users/hod/leave/                 HOD: waiting for me
  POST /api/users/hod/leave/<id>/action/     approve / reject (final)
  ?show=decided on the two review lists: the latest 100 this reviewer already decided

Approved leave is an EXCUSED absence: the register shows "On leave"
(/api/attendance/od_students/ returns leave_ids too) and the student's own
attendance shows L, but it does NOT count as present. On duty does.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.notifications.services import notify, notify_parents
from core.users.views import _tutor_student_ids

from .models import ODRequest, StudentLeaveRequest
from .od_views import _hod_of, _hod_student_ids, _tutors_of

PROOF_TYPES = (".pdf", ".jpg", ".jpeg", ".png")
STUDENT_LINK = "/student/attendance?tab=leave"


def _d(x):
    return x.strftime("%d-%m-%Y") if x else ""


def _text(lv):
    kind = lv.get_leave_type_display()
    if lv.from_date == lv.to_date:
        return f"{kind} leave · {_d(lv.from_date)}"
    return f"{kind} leave · {_d(lv.from_date)} to {_d(lv.to_date)} ({lv.days} days)"


class StudentLeaveSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.username", read_only=True)
    student_roll_no = serializers.CharField(source="student.roll_number", read_only=True, default="")
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    days = serializers.IntegerField(read_only=True)
    tutor_reviewed_by_name = serializers.CharField(source="tutor_reviewed_by.username", read_only=True, default="")
    hod_reviewed_by_name = serializers.CharField(source="hod_reviewed_by.username", read_only=True, default="")

    class Meta:
        model = StudentLeaveRequest
        fields = [
            "id", "student", "student_name", "student_roll_no",
            "leave_type", "leave_type_label", "from_date", "to_date", "days", "reason", "proof",
            "status", "status_label", "stage", "stage_label",
            "tutor_remark", "tutor_reviewed_at", "tutor_reviewed_by_name",
            "hod_remark", "hod_reviewed_at", "hod_reviewed_by_name",
            "created_at",
        ]
        read_only_fields = [
            "student", "status", "stage", "tutor_remark", "tutor_reviewed_at",
            "hod_remark", "hod_reviewed_at", "created_at",
        ]

    def validate_reason(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Give a reason for the leave.")
        return value[:2000]

    def validate_proof(self, value):
        if value and not value.name.lower().endswith(PROOF_TYPES):
            raise serializers.ValidationError("Proof must be a PDF, JPG or PNG file.")
        return value

    def validate(self, data):
        start, end = data["from_date"], data["to_date"]
        today = timezone.localdate()
        if end < start:
            raise serializers.ValidationError("The end date can't be before the start date.")
        days = (end - start).days + 1
        if days > StudentLeaveRequest.MAX_DAYS:
            raise serializers.ValidationError(
                f"Leave can be at most {StudentLeaveRequest.MAX_DAYS} days in one request.")
        if start < today - timedelta(days=StudentLeaveRequest.BACKDATE_DAYS):
            raise serializers.ValidationError(
                f"Leave can start at most {StudentLeaveRequest.BACKDATE_DAYS} days ago.")
        if (data["leave_type"] == StudentLeaveRequest.LeaveType.SICK
                and days >= StudentLeaveRequest.PROOF_REQUIRED_DAYS and not data.get("proof")):
            raise serializers.ValidationError(
                f"Sick leave of {StudentLeaveRequest.PROOF_REQUIRED_DAYS} days or more needs a "
                "medical certificate.")
        student = self.context["request"].user
        overlap = Q(from_date__lte=end, to_date__gte=start)
        if StudentLeaveRequest.objects.filter(
                overlap, student=student,
                status__in=[StudentLeaveRequest.Status.PENDING, StudentLeaveRequest.Status.APPROVED]).exists():
            raise serializers.ValidationError("You already have a leave request for some of these dates.")
        if ODRequest.objects.filter(
                overlap, student=student,
                status__in=[ODRequest.Status.PENDING, ODRequest.Status.APPROVED]).exists():
            raise serializers.ValidationError("You have an on-duty request for some of these dates.")
        return data


def _out(qs_or_obj, request, many=False):
    return StudentLeaveSerializer(qs_or_obj, many=many, context={"request": request}).data


# ?show=decided on the review lists: the latest requests this reviewer already decided
DECIDED_LIMIT = 100


# ---------------------------------------------------------------- student
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_create(request):
    if getattr(request.user, "role", None) != "student":
        return Response({"detail": "Only students apply for student leave."}, status=403)
    ser = StudentLeaveSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    lv = ser.save(student=request.user)
    tutors = _tutors_of(request.user)
    if tutors:
        notify(tutors, f"Student leave request from {request.user.username}",
               f"{_text(lv)}. Reason: {lv.reason[:120]}", "leave", link="/my-class?tab=requests")
    else:
        # no class in-charge set for this class: go straight to the HOD
        lv.stage = StudentLeaveRequest.Stage.AWAITING_HOD
        lv.save(update_fields=["stage"])
        notify([_hod_of(request.user)], f"Student leave request from {request.user.username}",
               f"{_text(lv)}. Reason: {lv.reason[:120]}", "leave", link="/my-department?tab=requests")
    return Response(_out(lv, request), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def leave_my_requests(request):
    qs = StudentLeaveRequest.objects.filter(student=request.user)
    return Response(_out(qs, request, many=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_cancel(request, pk):
    lv = StudentLeaveRequest.objects.filter(pk=pk, student=request.user).first()
    if lv is None:
        return Response({"detail": "Not found."}, status=404)
    if lv.status != StudentLeaveRequest.Status.PENDING:
        return Response({"detail": "Only pending requests can be cancelled."}, status=400)
    lv.status = StudentLeaveRequest.Status.CANCELLED
    lv.stage = StudentLeaveRequest.Stage.CLOSED
    lv.save(update_fields=["status", "stage"])
    return Response(_out(lv, request))


# ---------------------------------------------------------------- shared review
def _action(request):
    action = request.data.get("action")
    remark = (request.data.get("remark") or "").strip()[:255]
    if action not in ("approve", "reject"):
        return None, None, Response({"detail": "action must be approve or reject."}, status=400)
    if action == "reject" and not remark:
        return None, None, Response({"detail": "Say why you are rejecting it - the student sees this."},
                                    status=400)
    return action, remark, None


# ---------------------------------------------------------------- class in-charge
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tutor_leave_pending(request):
    students = list(_tutor_student_ids(request.user))
    if request.query_params.get("show") == "decided":      # Student requests -> Already decided
        qs = (StudentLeaveRequest.objects.filter(student_id__in=students, tutor_reviewed_at__isnull=False)
              .select_related("student").order_by("-tutor_reviewed_at")[:DECIDED_LIMIT])
    else:
        qs = StudentLeaveRequest.objects.filter(
            student_id__in=students,
            stage=StudentLeaveRequest.Stage.AWAITING_TUTOR, status=StudentLeaveRequest.Status.PENDING,
        ).select_related("student")
    return Response(_out(qs, request, many=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tutor_leave_action(request, pk):
    lv = StudentLeaveRequest.objects.filter(
        pk=pk, student_id__in=list(_tutor_student_ids(request.user)),
        stage=StudentLeaveRequest.Stage.AWAITING_TUTOR, status=StudentLeaveRequest.Status.PENDING,
    ).select_related("student").first()
    if lv is None:
        return Response({"detail": "Not found or not yours to review."}, status=404)
    action, remark, error = _action(request)
    if error:
        return error
    lv.tutor_reviewed_by = request.user
    lv.tutor_remark = remark
    lv.tutor_reviewed_at = timezone.now()
    if action == "approve":
        lv.stage = StudentLeaveRequest.Stage.AWAITING_HOD
    else:
        lv.status = StudentLeaveRequest.Status.REJECTED
        lv.stage = StudentLeaveRequest.Stage.CLOSED
    lv.save()

    s = lv.student
    if action == "approve":
        notify([_hod_of(s)], f"Student leave request from {s.username}",
               f"{_text(lv)}. Forwarded by class in-charge {request.user.username}.",
               "leave", link="/my-department?tab=requests")
        notify([s], "Leave request forwarded to HOD",
               f"{_text(lv)} was approved by your class in-charge and sent to the HOD.",
               "leave", link=STUDENT_LINK)
    else:
        notify([s], "Leave request rejected",
               f"{_text(lv)} was rejected by your class in-charge. Remark: {remark}",
               "leave", link=STUDENT_LINK)
    return Response(_out(lv, request))


# ---------------------------------------------------------------- HOD
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_leave_pending(request):
    students = list(_hod_student_ids(request.user))
    if request.query_params.get("show") == "decided":      # Student requests -> Already decided
        qs = (StudentLeaveRequest.objects.filter(student_id__in=students, hod_reviewed_at__isnull=False)
              .select_related("student").order_by("-hod_reviewed_at")[:DECIDED_LIMIT])
    else:
        qs = StudentLeaveRequest.objects.filter(
            student_id__in=students,
            stage=StudentLeaveRequest.Stage.AWAITING_HOD, status=StudentLeaveRequest.Status.PENDING,
        ).select_related("student")
    return Response(_out(qs, request, many=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_leave_action(request, pk):
    lv = StudentLeaveRequest.objects.filter(
        pk=pk, student_id__in=list(_hod_student_ids(request.user)),
        stage=StudentLeaveRequest.Stage.AWAITING_HOD, status=StudentLeaveRequest.Status.PENDING,
    ).select_related("student").first()
    if lv is None:
        return Response({"detail": "Not found or not yours to review."}, status=404)
    action, remark, error = _action(request)
    if error:
        return error
    lv.hod_reviewed_by = request.user
    lv.hod_remark = remark
    lv.hod_reviewed_at = timezone.now()
    lv.status = (StudentLeaveRequest.Status.APPROVED if action == "approve"
                 else StudentLeaveRequest.Status.REJECTED)
    lv.stage = StudentLeaveRequest.Stage.CLOSED
    lv.save()

    s = lv.student
    if action == "approve":
        notify([s], "Leave approved",
               f"{_text(lv)} was approved. Those days show as On leave (they don't count as present).",
               "leave", link=STUDENT_LINK)
        notify_parents(s, "Leave approved", f"{s.username}: {_text(lv)} was approved by the HOD.",
                       "leave", link="/parent/attendance")
    else:
        notify([s], "Leave request rejected",
               f"{_text(lv)} was rejected by the HOD. Remark: {remark}", "leave", link=STUDENT_LINK)
        notify_parents(s, "Leave request rejected",
                       f"{s.username}: {_text(lv)} was rejected by the HOD.", "leave",
                       link="/parent/attendance")
    return Response(_out(lv, request))


# ---------------------------------------------------------------- for the register
def approved_leave_student_ids(day, student_ids=None):
    qs = StudentLeaveRequest.objects.filter(
        status=StudentLeaveRequest.Status.APPROVED, from_date__lte=day, to_date__gte=day)
    if student_ids is not None:
        qs = qs.filter(student_id__in=student_ids)
    return list(qs.values_list("student_id", flat=True))
