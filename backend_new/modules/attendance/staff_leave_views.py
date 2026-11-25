# Staff leave: apply, preview, covering warnings, HOD approval,
# and (WAVE 2 Part 1b) the Principal's approval of an HOD's own leave.
# Moved here from users/views.py so that `users` (core) no longer depends on attendance.
# URLs are unchanged (/api/users/staff-leave/...) - see attendance/users_urls.py.
# ===================== IMPORTS =====================

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.decorators import (api_view, permission_classes)
from rest_framework.response import Response
from rest_framework.permissions import (IsAuthenticated)

from core.users.models import (Department)
from core.notifications.services import notify   # FIX #11


def _d(x):
    return x.strftime("%d-%m-%Y") if x else ""


def _leave_text(leave):
    """'Casual leave · 02-11-2026' or '... 02-11-2026 to 04-11-2026'"""
    kind = leave.get_leave_type_display()
    if leave.from_date == leave.to_date:
        return f"{kind} · {_d(leave.from_date)}"
    return f"{kind} · {_d(leave.from_date)} to {_d(leave.to_date)}"


# =====================================================
#  STAFF LEAVE: HELPERS
# =====================================================
def _hod_department_ids(user):
    """IDs of departments where this user is the HOD. [] if not an HOD."""
    # #50 ACTING HOD: the current HOD (Acting HOD during their dates)
    from core.users.acting_hod import hod_department_ids
    return hod_department_ids(user)


def _staff_leave_or_404(pk):
    """One leave request with its related users loaded, or a 404."""
    from modules.attendance.models import StaffLeaveRequest
    return get_object_or_404(
        StaffLeaveRequest.objects.select_related(
            "teacher", "department", "hod", "backup", "decided_by"
        ),
        pk=pk,
    )


def _can_view_staff_leave(user, leave):
    """
    Who may open a leave record or download its proof:
      - the teacher who applied
      - the HOD it was routed to
      - any HOD of the department it belongs to
      - the backup teacher covering an HOD's leave
      - the current Principal, for an HOD's leave (WAVE 2 Part 1b)
      - admin
    """
    if leave.teacher_id == user.id:
        return True
    if leave.hod_id and leave.hod_id == user.id:
        return True
    if leave.backup_id and leave.backup_id == user.id:
        return True
    if leave.department_id and leave.department_id in _hod_department_ids(user):
        return True
    if leave.level == leave.Level.PRINCIPAL:
        from core.users.principal import is_principal
        if is_principal(user):
            return True
    return user.is_superuser or getattr(user, "role", "") == "admin"


# ============================== TEACHER =====================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_leave_create(request):
    from django.contrib.auth import get_user_model
    from modules.attendance.leave_service import approver_for, is_department_hod
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    user = request.user
    if getattr(user, "role", "") != "teacher":
        return Response({"detail": "Only teaching staff can apply here."}, status=403)

    # ── HOD's own leave: a backup covers; the Principal approves (WAVE 2 Part 1b).
    #    With no Principal set (or when the HOD IS the Principal) it is recorded, no approval.
    if is_department_hod(user):
        backup_id = request.data.get("backup")
        if not backup_id:
            return Response(
                {"detail": "Choose who will cover your work during this leave."},
                status=400,
            )
        UserModel = get_user_model()
        try:
            backup = UserModel.objects.get(
                pk=backup_id, role="teacher",
                department=user.department, is_active=True,
            )
        except (UserModel.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Choose a teacher from your own department as backup."},
                status=400,
            )
        if backup.id == user.id:
            return Response({"detail": "You cannot choose yourself as backup."}, status=400)

        ser = StaffLeaveRequestSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        # #50 ACTING HOD (Step 3b): the regular HOD may nominate the backup as
        # Acting HOD. If the nomination breaks a rule, NOTHING is saved.
        nominate = str(request.data.get("nominate_acting", "")).lower() in ("1", "true", "yes", "on")
        from django.db import transaction
        from core.users import acting_hod
        nomination = None
        from core.users.principal import current_principal
        principal = current_principal()
        to_principal = bool(principal and principal.id != user.id)
        with transaction.atomic():
            if to_principal:
                leave = ser.save(
                    teacher=user, department=user.department, hod=principal,
                    backup=backup, status=StaffLeaveRequest.Status.PENDING,
                    level=StaffLeaveRequest.Level.PRINCIPAL,
                )
            else:
                leave = ser.save(
                    teacher=user, department=user.department, hod=None,
                    backup=backup, status=StaffLeaveRequest.Status.RECORDED,
                )
            if nominate:
                try:
                    nomination = acting_hod.nominate(user, leave)
                except acting_hod.ActingHODError as e:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": f"Your leave was not saved: {e} "
                                   "Untick 'Nominate as Acting HOD' to record the leave alone."},
                        status=400,
                    )

        # FIX #11: tell the backup they are covering
        notify([backup], f"You are covering for {user.username}",
               f"{_leave_text(leave)}. {user.username} (HOD) chose you as backup."
               + (" The Principal still has to approve this leave." if to_principal else "")
               + (" You are also nominated as Acting HOD (waiting for admin approval)."
                  if nomination else ""),
               "leave", link="/teacher/leave")
        # WAVE 2 Part 1b: the Principal approves an HOD's leave
        if to_principal:
            notify([principal], f"HOD leave request from {user.username}",
                   f"{_leave_text(leave)}. Backup: {backup.username}. Reason: {leave.reason[:120]}",
                   "leave", link="/principal")
        return Response(StaffLeaveRequestSerializer(leave, context={"request": request}).data, status=201)

    # ── Normal teacher leave: goes to the HOD for approval ──
    hod, error = approver_for(user)
    if error:
        return Response({"detail": error}, status=400)

    ser = StaffLeaveRequestSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    leave = ser.save(teacher=user, department=user.department, hod=hod)
    # FIX #11: tell the HOD a request is waiting
    notify([hod], f"Leave request from {user.username}",
           f"{_leave_text(leave)}. Reason: {leave.reason[:120]}",
           "leave", link="/my-department?tab=staffleave")
    return Response(ser.data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_leave_my(request):
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    qs = StaffLeaveRequest.objects.filter(teacher=request.user).select_related(
        "teacher", "department", "hod", "backup"
    )
    return Response(
        StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_leave_detail(request, pk):
    from modules.attendance.serializers import StaffLeaveRequestDetailSerializer

    leave = _staff_leave_or_404(pk)
    if not _can_view_staff_leave(request.user, leave):
        return Response({"detail": "Not yours to view."}, status=403)
    return Response(
        StaffLeaveRequestDetailSerializer(leave, context={"request": request}).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_leave_cancel(request, pk):
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    leave = _staff_leave_or_404(pk)
    if leave.teacher_id != request.user.id:
        return Response({"detail": "Not yours to cancel."}, status=403)
    if leave.status not in (
        StaffLeaveRequest.Status.PENDING, StaffLeaveRequest.Status.RECORDED
    ):
        return Response(
            {"detail": "Only a pending or recorded leave can be cancelled."},
            status=400,
        )

    was = leave.status
    leave.status = StaffLeaveRequest.Status.CANCELLED
    leave.save(update_fields=["status"])

    # #50 ACTING HOD (Step 3b): cancel the nomination / assignment made with this leave
    from core.users.acting_hod import leave_cancelled
    leave_cancelled(leave.id, request.user)

    # FIX #11: the HOD (pending request) or the backup (HOD's own leave) is told
    # #50 ACTING HOD: tell the CURRENT HOD (who sees the request now), not the saved one
    from core.users.acting_hod import current_hod
    now_hod = current_hod(leave.department) if leave.department_id else leave.hod
    if leave.level == StaffLeaveRequest.Level.PRINCIPAL:
        # WAVE 2 Part 1b: an HOD's leave - the Principal (if it was waiting) and the backup
        from core.users.principal import current_principal
        principal = current_principal()
        if was == StaffLeaveRequest.Status.PENDING and principal and principal.id != request.user.id:
            notify([principal], f"HOD leave request cancelled by {request.user.username}",
                   _leave_text(leave), "leave", link="/principal")
        if leave.backup_id:
            notify([leave.backup], f"Cover no longer needed for {request.user.username}",
                   f"{_leave_text(leave)} was cancelled.", "leave", link="/teacher/leave")
    elif (was == StaffLeaveRequest.Status.PENDING and now_hod
            and now_hod.id != request.user.id):
        notify([now_hod], f"Leave request cancelled by {request.user.username}",
               _leave_text(leave), "leave", link="/my-department?tab=staffleave")
    elif was == StaffLeaveRequest.Status.RECORDED and leave.backup_id:
        notify([leave.backup], f"Cover no longer needed for {request.user.username}",
               f"{_leave_text(leave)} was cancelled.", "leave", link="/teacher/leave")
    return Response(
        StaffLeaveRequestSerializer(leave, context={"request": request}).data
    )


def _covering_warning_for_me(user, from_date, to_date):
    """Same warning as the HOD sees, but written to the teacher themselves."""
    from modules.attendance.leave_service import covering_warning

    text = covering_warning(user, from_date, to_date)
    if not text:
        return None
    text = text.replace(f"{user.username} is the backup", "You are the backup", 1)
    return f"{text} You can still submit. Your HOD will see this warning."


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_leave_preview(request):
    """
    Feeds the "Classes during this leave" box on the apply form.
    GET /api/users/staff-leave/preview/?from=2026-09-21&to=2026-09-23&session=full
    """
    from datetime import date
    from modules.attendance.leave_service import (
        affected_periods, approver_for, backup_options,
        count_leave_days, is_department_hod,
    )

    def parse(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    from_date = parse(request.GET.get("from"))
    to_date = parse(request.GET.get("to"))
    session = request.GET.get("session", "full")
    if not from_date or not to_date or to_date < from_date:
        return Response({"detail": "Send a valid from and to date."}, status=400)

    is_hod = is_department_hod(request.user)
    # An HOD's leave goes to the Principal (WAVE 2 Part 1b), or is recorded when
    # none is set, so approver_for's "no HOD above you" error must not block it.
    hod, error = (None, None) if is_hod else approver_for(request.user)
    principal = None
    if is_hod:
        from core.users.principal import current_principal
        principal = current_principal()
        if principal and principal.id == request.user.id:
            principal = None

    from core.users.acting_hod import can_nominate   # #50 ACTING HOD
    from core.users.hris import balance, leave_problem   # HRIS PART A
    leave_type = request.GET.get("leave_type")
    days = count_leave_days(from_date, to_date, session)
    return Response({
        "balance": balance(request.user, from_date.year),
        "balance_problem": leave_problem(request.user, leave_type, days, from_date.year) if leave_type else None,
        "is_hod": is_hod,
        "can_nominate": can_nominate(request.user),
        "backup_options": backup_options(request.user) if is_hod else [],
        "covering_warning": _covering_warning_for_me(request.user, from_date, to_date),
        "days": count_leave_days(from_date, to_date, session),
        "periods": affected_periods(request.user, from_date, to_date, session),
        "approver": hod.username if hod else (principal.username if principal else None),
        "approver_role": "hod" if hod else ("principal" if principal else None),
        "approver_department": (
            request.user.department.name if request.user.department and hod else None
        ),
        "blocked_reason": error,
        "substitute_note": (
            "These classes may need a substitute teacher. "
            "Approving leave does not assign one."
        ),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_leave_covering(request):
    """HOD leaves this user is covering — today or later. Ends after to_date."""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    qs = (
        StaffLeaveRequest.objects
        .filter(
            backup=request.user,
            status__in=[StaffLeaveRequest.Status.RECORDED, StaffLeaveRequest.Status.APPROVED],
            to_date__gte=timezone.localdate(),
        )
        .select_related("teacher", "department", "backup")
        .order_by("from_date")
    )
    return Response(
        StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data
    )


# ================================= HOD ======================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_staff_leave_pending(request):
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    dept_ids = _hod_department_ids(request.user)
    if not dept_ids:
        return Response({"detail": "You are not an HOD."}, status=403)

    qs = (
        StaffLeaveRequest.objects
        .filter(department_id__in=dept_ids, status=StaffLeaveRequest.Status.PENDING,
                level=StaffLeaveRequest.Level.HOD)     # an HOD's own leave goes to the Principal
        .exclude(teacher=request.user)          # nobody approves their own leave
        .select_related("teacher", "department", "hod")
        .order_by("from_date")
    )
    return Response(
        StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_staff_leave_history(request):
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    dept_ids = _hod_department_ids(request.user)
    if not dept_ids:
        return Response({"detail": "You are not an HOD."}, status=403)

    qs = (
        StaffLeaveRequest.objects
        .filter(
            department_id__in=dept_ids,
            level=StaffLeaveRequest.Level.HOD,
            status__in=[
                StaffLeaveRequest.Status.APPROVED,
                StaffLeaveRequest.Status.REJECTED,
            ],
        )
        .select_related("teacher", "department", "hod")
        .order_by("-decided_at")
    )
    return Response(
        StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_staff_leave_on_leave_today(request):
    """Small panel on the HOD screen: who is away right now."""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    dept_ids = _hod_department_ids(request.user)
    if not dept_ids:
        return Response({"detail": "You are not an HOD."}, status=403)

    today = timezone.localdate()
    qs = (
        StaffLeaveRequest.objects
        .filter(
            department_id__in=dept_ids,
            status=StaffLeaveRequest.Status.APPROVED,
            from_date__lte=today,
            to_date__gte=today,
        )
        .select_related("teacher", "department", "hod")
    )
    return Response(
        StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_staff_leave_action(request, pk):
    """Body: {"action": "approve" | "reject", "remark": "..."}"""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    action = request.data.get("action")
    remark = (request.data.get("remark") or "").strip()

    leave = _staff_leave_or_404(pk)

    if leave.department_id not in _hod_department_ids(request.user):
        return Response(
            {"detail": "You are not the HOD of that teacher's department."}, status=403
        )
    if leave.teacher_id == request.user.id:
        return Response({"detail": "You cannot decide your own leave."}, status=403)
    if leave.level == StaffLeaveRequest.Level.PRINCIPAL:
        return Response({"detail": "An HOD's leave is decided by the Principal."}, status=403)
    if not leave.is_pending:
        return Response({"detail": "This request has already been decided."}, status=400)

    if action == "approve":
        leave.status = StaffLeaveRequest.Status.APPROVED
    elif action == "reject":
        if not remark:
            return Response(
                {"detail": "Add a remark so the teacher knows why it was rejected."},
                status=400,
            )
        leave.status = StaffLeaveRequest.Status.REJECTED
    else:
        return Response({"detail": "action must be approve or reject."}, status=400)

    leave.hod_remark = remark
    leave.decided_by = request.user
    leave.decided_at = timezone.now()
    leave.save(update_fields=["status", "hod_remark", "decided_by", "decided_at"])

    # FIX #11: tell the teacher the decision
    # #50 ACTING HOD (Step 5): say so when the Acting HOD decided
    from core.users.acting_hod import was_acting_hod
    as_acting = " (Acting HOD)" if was_acting_hod(request.user, leave.department_id, leave.decided_at) else ""
    if action == "approve":
        notify([leave.teacher], "Leave approved",
               f"{_leave_text(leave)} was approved by {request.user.username}{as_acting}."
               + (f" Remark: {remark}" if remark else ""),
               "leave", link="/teacher/leave")
    else:
        notify([leave.teacher], "Leave rejected",
               f"{_leave_text(leave)} was rejected. Remark: {remark}",
               "leave", link="/teacher/leave")

    return Response(
        StaffLeaveRequestSerializer(leave, context={"request": request}).data
    )


# ============================ PRINCIPAL (WAVE 2 Part 1b) =====================
def _principal_or_403(user):
    from core.users.principal import is_principal
    if not is_principal(user):
        return Response({"detail": "Only the Principal decides an HOD's leave."}, status=403)
    return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def principal_staff_leave_pending(request):
    """HOD leave waiting for the Principal, earliest first."""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    denied = _principal_or_403(request.user)
    if denied:
        return denied
    qs = (StaffLeaveRequest.objects
          .filter(level=StaffLeaveRequest.Level.PRINCIPAL, status=StaffLeaveRequest.Status.PENDING)
          .exclude(teacher=request.user)
          .select_related("teacher", "department", "hod", "backup")
          .order_by("from_date"))
    return Response(StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def principal_staff_leave_history(request):
    """HOD leave the Principal has decided, latest first (last 50)."""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    denied = _principal_or_403(request.user)
    if denied:
        return denied
    qs = (StaffLeaveRequest.objects
          .filter(level=StaffLeaveRequest.Level.PRINCIPAL,
                  status__in=[StaffLeaveRequest.Status.APPROVED, StaffLeaveRequest.Status.REJECTED])
          .select_related("teacher", "department", "hod", "backup", "decided_by")
          .order_by("-decided_at")[:50])
    return Response(StaffLeaveRequestSerializer(qs, many=True, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def principal_staff_leave_action(request, pk):
    """Body: {"action": "approve" | "reject", "remark": "..."} - an HOD's own leave."""
    from modules.attendance.models import StaffLeaveRequest
    from modules.attendance.serializers import StaffLeaveRequestSerializer

    denied = _principal_or_403(request.user)
    if denied:
        return denied
    action = request.data.get("action")
    remark = (request.data.get("remark") or "").strip()[:255]
    leave = _staff_leave_or_404(pk)
    if leave.level != StaffLeaveRequest.Level.PRINCIPAL:
        return Response({"detail": "This leave is decided by the department HOD."}, status=403)
    if leave.teacher_id == request.user.id:
        return Response({"detail": "You cannot decide your own leave."}, status=403)
    if not leave.is_pending:
        return Response({"detail": "This request has already been decided."}, status=400)
    if action == "approve":
        leave.status = StaffLeaveRequest.Status.APPROVED
    elif action == "reject":
        if not remark:
            return Response({"detail": "Add a remark so the HOD knows why it was rejected."}, status=400)
        leave.status = StaffLeaveRequest.Status.REJECTED
    else:
        return Response({"detail": "action must be approve or reject."}, status=400)

    leave.hod_remark = remark
    leave.decided_by = request.user
    leave.decided_at = timezone.now()
    leave.save(update_fields=["status", "hod_remark", "decided_by", "decided_at"])

    who = request.user.username
    if action == "approve":
        notify([leave.teacher], "Leave approved by the Principal",
               f"{_leave_text(leave)} was approved by {who}." + (f" Remark: {remark}" if remark else ""),
               "leave", link="/teacher/leave")
        if leave.backup_id:
            notify([leave.backup], f"You are covering for {leave.teacher.username}",
                   f"{_leave_text(leave)} was approved. You handle {leave.teacher.username}'s work "
                   f"during the leave.", "leave", link="/teacher/leave")
    else:
        # #50 ACTING HOD: a nomination made with this leave is no longer needed
        from core.users.acting_hod import leave_cancelled
        leave_cancelled(leave.id, request.user)
        notify([leave.teacher], "Leave rejected by the Principal",
               f"{_leave_text(leave)} was rejected. Remark: {remark}", "leave", link="/teacher/leave")
        if leave.backup_id:
            notify([leave.backup], f"Cover no longer needed for {leave.teacher.username}",
                   f"{_leave_text(leave)} was not approved.", "leave", link="/teacher/leave")
    return Response(StaffLeaveRequestSerializer(leave, context={"request": request}).data)


# ================================ PROOF =====================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_leave_proof(request, pk):
    """
    Serves the uploaded file through a permission check, so a medical
    certificate is not readable by anyone who guesses the /media/ URL.
    """
    leave = _staff_leave_or_404(pk)
    if not _can_view_staff_leave(request.user, leave):
        return Response({"detail": "Not yours to view."}, status=403)
    if not leave.proof:
        return Response({"detail": "No proof attached."}, status=404)

    return FileResponse(
        leave.proof.open("rb"),
        filename=leave.proof.name.split("/")[-1],
    )
