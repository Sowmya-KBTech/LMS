"""
STEP 6.2: helpers for BackgroundJob (jobs started by a user, run by Celery).

    job = start_job("timetable_autofill", user, lock_key="timetable:5:3", params={...})
    ...in the Celery task...
    if mark_running(job.id): do the work, then mark_done(job.id, result) or mark_failed(job.id, msg)

Safety lives in PostgreSQL, not Redis:
  - one active job per lock_key (database constraint "one_active_job_per_lock")
  - mark_running() only succeeds once, so a job is never run twice
  - jobs stuck in queued/running for too long are marked failed, which frees the lock
"""
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .models import BackgroundJob

# A job still queued/running after this long is treated as stuck
# (the Celery hard time limit is 5 minutes).
STUCK_AFTER_MINUTES = 10
STUCK_MESSAGE = ("Stopped: the job took too long or the background worker "
                 "was not running. Please try again.")


class JobAlreadyRunning(Exception):
    """Another job with the same lock_key is queued or running."""

    def __init__(self, job):
        self.job = job
        super().__init__(f"A {job.kind} job is already {job.status} ({job.id}).")


def expire_stuck(lock_key=None, now=None):
    """Mark old queued/running jobs as failed. Returns how many were changed."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=STUCK_AFTER_MINUTES)
    qs = BackgroundJob.objects.filter(status__in=BackgroundJob.ACTIVE, created_at__lt=cutoff)
    if lock_key:
        qs = qs.filter(lock_key=lock_key)
    return qs.update(status=BackgroundJob.Status.FAILED, error=STUCK_MESSAGE, finished_at=now)


def start_job(kind, user, lock_key="", params=None):
    """
    Create a queued job. Raises JobAlreadyRunning if a job with the same
    lock_key is still queued or running.
    """
    if lock_key:
        expire_stuck(lock_key=lock_key)
    try:
        with transaction.atomic():
            return BackgroundJob.objects.create(
                kind=kind,
                college=connection.schema_name,     # the college this job belongs to
                lock_key=lock_key,
                params=params or {},
                created_by=user,
            )
    except IntegrityError:
        existing = (BackgroundJob.objects
                    .filter(lock_key=lock_key, status__in=BackgroundJob.ACTIVE)
                    .first())
        if existing is None:        # it finished in the meantime: try once more
            return start_job(kind, user, lock_key, params)
        raise JobAlreadyRunning(existing)


def mark_running(job_id):
    """queued -> running. Returns True only for the first caller."""
    return BackgroundJob.objects.filter(
        id=job_id, status=BackgroundJob.Status.QUEUED,
    ).update(status=BackgroundJob.Status.RUNNING, started_at=timezone.now()) == 1


def mark_done(job_id, result):
    BackgroundJob.objects.filter(id=job_id).update(
        status=BackgroundJob.Status.DONE, result=result, error="",
        finished_at=timezone.now(),
    )


def mark_failed(job_id, error):
    BackgroundJob.objects.filter(id=job_id).update(
        status=BackgroundJob.Status.FAILED, error=str(error)[:2000],
        finished_at=timezone.now(),
    )


def job_payload(job):
    """What the status API returns."""
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
