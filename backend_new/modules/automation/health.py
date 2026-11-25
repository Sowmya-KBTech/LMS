"""
STEP 8.4: is the background system alive?

Each part is checked SEPARATELY, because one can be fine while another is dead:
  - Redis (broker)  : reachable?
  - Worker          : answers a ping?
  - Waiting queue   : are jobs piling up (Beat sends, but no worker takes them)?
  - Beat            : did its 5-minute heartbeat run recently?
  - Nightly jobs    : did run_daily_jobs run in the last 26 hours, any failed / stuck?

Read-only: nothing here sends reminders or emails.
The heartbeat time is kept in the broker Redis (not the cache, whose errors are
ignored): if that Redis is down, Beat cannot send jobs anyway and the Redis
check shows the problem.
"""
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

HEARTBEAT_EVERY = 300                       # Beat sends the heartbeat every 5 minutes
BEAT_LATE_AFTER = 3 * HEARTBEAT_EVERY       # 3 missed beats (15 min) = problem
NIGHTLY_LATE_AFTER = timedelta(hours=26)    # runs at 12:15 AM; 2 hours of grace
STUCK_AFTER = timedelta(hours=1)            # a job "running" this long has died
QUEUE_WARN_AT = 20                          # waiting tasks before we warn

OK, WARNING, PROBLEM, UNKNOWN = "ok", "warning", "problem", "unknown"
_RANK = {OK: 0, UNKNOWN: 1, WARNING: 2, PROBLEM: 3}


def _broker():
    url = getattr(settings, "CELERY_BROKER_URL", "")
    if not url:
        return None
    import redis
    return redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def _heartbeat_key():
    # ONE Beat serves every college, so its heartbeat is a platform-wide key
    return "lms:platform:beat_heartbeat"


def record_heartbeat(now=None):
    r = _broker()
    if r is not None:
        r.set(_heartbeat_key(), str(now if now is not None else time.time()))


def _ping_workers():
    from config import celery_app
    return celery_app.control.ping(timeout=1.0) or []


def _minutes(seconds):
    m = int(seconds // 60)
    return "less than a minute" if m < 1 else f"{m} minute{'s' if m != 1 else ''}"


def _check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def _broker_checks(now_ts):
    r = _broker()
    if r is None:
        msg = "Celery is not set up (CELERY_BROKER_URL is empty); jobs run inside the request."
        return [_check(n, UNKNOWN, msg) for n in ("Redis (broker)", "Worker", "Waiting queue", "Beat")]

    try:
        r.ping()
    except Exception as exc:
        return [_check("Redis (broker)", PROBLEM, f"Not reachable ({type(exc).__name__}). "
                       "No background job can start until Redis is back.")] + [
            _check(n, UNKNOWN, "Cannot check while Redis is down.")
            for n in ("Worker", "Waiting queue", "Beat")]

    out = [_check("Redis (broker)", OK, "Reachable.")]

    try:
        replies = _ping_workers()
    except Exception as exc:
        replies, err = [], type(exc).__name__
    else:
        err = ""
    if replies:
        out.append(_check("Worker", OK, f"{len(replies)} worker(s) answered."))
    else:
        out.append(_check("Worker", PROBLEM, "No worker answered. It is stopped, or busy with "
                          "one long job (a --pool=solo worker cannot answer while working)."
                          + (f" ({err})" if err else "")))

    waiting = r.llen("celery")
    if waiting >= QUEUE_WARN_AT:
        out.append(_check("Waiting queue", WARNING, f"{waiting} jobs waiting. The worker is "
                          "not keeping up, or is stopped."))
    else:
        out.append(_check("Waiting queue", OK, f"{waiting} job(s) waiting."))

    raw = r.get(_heartbeat_key())
    if raw is None:
        out.append(_check("Beat", PROBLEM, "No heartbeat yet. Beat is not running (or "
                          "has not ticked since Redis restarted)."))
    else:
        age = max(0.0, now_ts - float(raw))
        if age > BEAT_LATE_AFTER:
            out.append(_check("Beat", PROBLEM, f"Last heartbeat {_minutes(age)} ago. Beat "
                              "has stopped, or the worker is not taking its jobs."))
        else:
            out.append(_check("Beat", OK, f"Last heartbeat {_minutes(age)} ago."))
    return out


def _nightly_checks(now):
    from modules.automation.models import JobRun
    from modules.automation.views import LABELS

    real = JobRun.objects.filter(dry_run=False)
    last = real.order_by("-started_at").first()
    if last is None:
        return [_check("Nightly jobs", WARNING, "Never ran (not a dry run) yet.")], None

    age = now - last.started_at
    when = timezone.localtime(last.started_at).strftime("%d-%m-%Y %I:%M %p")
    if age > NIGHTLY_LATE_AFTER:
        out = [_check("Nightly jobs", PROBLEM, f"Last real run was {when}, more than 26 "
                      "hours ago. Tonight's reminders may not go out.")]
    else:
        out = [_check("Nightly jobs", OK, f"Last real run {when}.")]

    # the last batch = real runs started within an hour of the newest one
    batch = real.filter(started_at__gte=last.started_at - timedelta(hours=1))
    failed = list(batch.filter(status="failed"))
    if failed:
        lines = "; ".join(f"{LABELS.get(j.job, j.job)}: {j.message}" for j in failed)
        out.append(_check("Last run failures", PROBLEM, f"{len(failed)} job(s) failed: {lines}"))
    else:
        out.append(_check("Last run failures", OK, "No failed jobs in the last run."))

    stuck = real.filter(status="running", started_at__lt=now - STUCK_AFTER).count()
    if stuck:
        out.append(_check("Stuck jobs", WARNING, f"{stuck} job(s) still 'running' after an "
                          "hour. The run was probably killed (worker stopped or time limit)."))
    return out, last.started_at


def _every_college_nightly(now):
    """Outside any college (the task_health command): each college's diary in turn."""
    from django_tenants.utils import get_public_schema_name, schema_context
    from core.tenants.models import College
    checks, last = [], None
    colleges = (College.objects.exclude(schema_name=get_public_schema_name())
                .filter(is_active=True).order_by("id"))
    for college in colleges:
        with schema_context(college.schema_name):
            nightly, when = _nightly_checks(now)
        for c in nightly:
            c["name"] = f"{c['name']} ({college.schema_name})"
        checks += nightly
        last = max(filter(None, [last, when]), default=None)
    if not checks:
        checks = [_check("Nightly jobs", WARNING, "No active college yet.")]
    return checks, last


def check(now=None):
    """
    Inside a college (the System health card): that college's nightly run.
    Outside any college (manage.py task_health): every college's nightly run.
    Redis, the worker and Beat are shared by all colleges.
    """
    from django.db import connection
    from django_tenants.utils import get_public_schema_name
    now = now or timezone.now()
    checks = _broker_checks(now.timestamp())
    if getattr(connection, "schema_name", None) in (None, get_public_schema_name()):
        nightly, last_run = _every_college_nightly(now)
    else:
        nightly, last_run = _nightly_checks(now)
    checks += nightly
    overall = max((c["status"] for c in checks), key=_RANK.get)
    return {"overall": overall, "checked_at": now, "last_nightly_run": last_run,
            "checks": checks}