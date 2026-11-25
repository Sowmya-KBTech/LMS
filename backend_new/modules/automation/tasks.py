"""
Redis/Celery work, step 8.1: the scheduled jobs, started by Celery Beat
(replaces the Windows Task Scheduler .bat files). The schedule itself is
CELERY_BEAT_SCHEDULE in config/settings.py.

ONE Beat serves every college: these tasks run outside any college and go
through each active college in turn with run_for_all_colleges (the same
command the old .bat files used). Inside each college, both commands take
that college's database lock, so a run that is still busy is never started
twice (step 8.2).
"""
from io import StringIO

from celery import shared_task
from django.core.management import call_command


def _run(name):
    out = StringIO()
    call_command("run_for_all_colleges", name, stdout=out, stderr=out, no_color=True)
    lines = [line for line in out.getvalue().strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""          # the summary line, shown in the worker log


@shared_task(name="automation.run_daily_jobs")
def run_daily_jobs():
    """Nightly, for every college: fees, attendance, assignment and Acting HOD reminders, placement, email."""
    return _run("run_daily_jobs")


@shared_task(name="notifications.send_email_queue")
def send_email_queue():
    """Every 10 minutes, for every college: send waiting notification emails."""
    return _run("send_notification_emails")


@shared_task(name="automation.heartbeat")
def heartbeat():
    """Every 5 minutes (STEP 8.4): proves Beat AND a worker are alive."""
    from modules.automation.health import record_heartbeat
    record_heartbeat()
    return "ok"  