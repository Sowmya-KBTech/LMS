"""
AUTOMATION SCREEN (Point 12, step 8): APIs for Admin -> Automation.

    GET  /api/automation/settings/   settings + job list (with schedule)
    PUT  /api/automation/settings/   save settings
    GET  /api/automation/runs/       the job diary (last 50 runs)
    POST /api/automation/preview/    dry run of tonight's jobs - sends nothing

Only the main admin (superuser, or admin with no sub-role) may use them.
"""
from io import StringIO

from django.core.management import call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jobs import JOBS, describe_when
from .models import AutomationSetting, JobRun

MAIN_ADMIN_SUB_ROLES = ("", "super_admin")
LIMITS = {
    "fee_remind_days_before": (1, 30),
    "fee_grace_days": (0, 60),
    "attendance_alert_weekday": (0, 6),
}
LABELS = {
    "fee_due_soon": "Fee due soon",
    "fee_overdue": "Fee overdue (grace)",
    "fee_grace_ended": "Grace period ended",
    "low_attendance": "Low attendance",
    "assignment_due": "Assignment due",
    "email_queue": "Email queue",
    "placement_eligibility": "Placement eligibility re-check",
}


def _is_main_admin(user):
    if getattr(user, "is_superuser", False):
        return True
    return (getattr(user, "role", None) == "admin"
            and (getattr(user, "sub_role", None) or "") in MAIN_ADMIN_SUB_ROLES)


def _name(u):
    return ((u.get_full_name() or "").strip() or u.username) if u else None


def _settings_payload(s):
    return {
        "fee_reminders_on": s.fee_reminders_on,
        "fee_remind_days_before": s.fee_remind_days_before,
        "fee_grace_days": s.fee_grace_days,
        "attendance_alerts_on": s.attendance_alerts_on,
        "attendance_alert_weekday": s.attendance_alert_weekday,
        "updated_by": _name(s.updated_by),
        "updated_at": s.updated_at,
        "jobs": [{"name": n, "label": LABELS.get(n, n), "when": describe_when(w)} for n, _f, w in JOBS],
    }


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def automation_settings(request):
    if not _is_main_admin(request.user):
        return Response({"detail": "Only the main admin can manage automation."}, status=403)
    s = AutomationSetting.current()
    if request.method == "GET":
        return Response(_settings_payload(s))

    data = request.data
    for field in ("fee_reminders_on", "attendance_alerts_on"):
        if field in data:
            setattr(s, field, bool(data[field]))
    for field, (lo, hi) in LIMITS.items():
        if field in data:
            try:
                value = int(data[field])
            except (TypeError, ValueError):
                return Response({"detail": f"{field} must be a whole number."}, status=400)
            if not lo <= value <= hi:
                return Response({"detail": f"{field} must be between {lo} and {hi}."}, status=400)
            setattr(s, field, value)
    s.updated_by = request.user
    s.save()
    return Response(_settings_payload(s))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def automation_runs(request):
    if not _is_main_admin(request.user):
        return Response({"detail": "Only the main admin can manage automation."}, status=403)
    runs = JobRun.objects.all()[:50]
    return Response([{
        "id": r.id, "job": r.job, "label": LABELS.get(r.job, r.job),
        "started_at": r.started_at, "finished_at": r.finished_at,
        "status": r.status, "sent_count": r.sent_count,
        "dry_run": r.dry_run, "message": r.message,
    } for r in runs])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def automation_health(request):
    """STEP 8.4: is Beat / the worker / Redis alive, did tonight's jobs run? Read-only."""
    if not _is_main_admin(request.user):
        return Response({"detail": "Only the main admin can manage automation."}, status=403)
    from modules.automation.health import check
    return Response(check())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def automation_preview(request):
    """Dry run of tonight's jobs: who WOULD be notified. Sends nothing."""
    if not _is_main_admin(request.user):
        return Response({"detail": "Only the main admin can manage automation."}, status=403)
    out = StringIO()
    call_command("run_daily_jobs", "--dry-run", stdout=out, stderr=out, no_color=True)
    return Response({"output": out.getvalue()})



# =====================================================================
#  STEP 6.2: status of one background job (the browser asks every 2 s)
#  GET /api/jobs/<uuid>/   - only the person who started it, or a main admin
# =====================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_status(request, job_id):
    from .background import expire_stuck, job_payload
    from .models import BackgroundJob

    job = BackgroundJob.objects.filter(id=job_id).first()
    allowed = job is not None and (
        job.created_by_id == request.user.id or _is_main_admin(request.user)
    )
    if not allowed:
        # same answer for "does not exist" and "not yours"
        return Response({"detail": "Job not found."}, status=404)

    if job.status in BackgroundJob.ACTIVE and expire_stuck(lock_key=job.lock_key or None):
        job.refresh_from_db()
    payload = job_payload(job)

    # STEP 7.2: parts of a result marked "_one_time" (e.g. new accounts' temporary
    # passwords) go only to the person who started the job, and only once.
    one_time = (job.result or {}).get("_one_time") if isinstance(job.result, dict) else None
    if one_time:
        result = dict(job.result)
        for key in one_time:
            result.pop(key, None)
        result.pop("_one_time", None)
        if job.created_by_id == request.user.id:
            BackgroundJob.objects.filter(id=job.id).update(result=result)   # gone after this read
        else:
            payload["result"] = result                                       # never shown to others
    return Response(payload)