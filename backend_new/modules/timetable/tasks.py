"""
Background tasks for the timetable (STEP 6.3, safe save STEP 6.4).

run_autofill(job_id)
    Runs the auto-fill solver for the class saved in the BackgroundJob row,
    then stores the result (or the error) back in that row.
    The browser follows it with GET /api/jobs/<job_id>/.
"""
import hashlib
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection
from django.db.models import Q

from modules.automation.background import mark_done, mark_failed, mark_running
from modules.automation.models import BackgroundJob

from .models import Room, TimetableApproval, TimetableEntry
from .solver import autofill

log = logging.getLogger(__name__)

CHANGED_MESSAGE = ("The timetable was changed while auto-fill was running, so nothing "
                   "was saved. Please run auto-fill again.")
LOCKED_MESSAGE = ("The timetable was submitted while auto-fill was running, so nothing "
                  "was saved.")


class TimetableChanged(Exception):
    """Raised inside the save transaction: nothing is written."""


def class_fingerprint(year_id, semester):
    """
    STEP 6.4: a short summary of one class's timetable (every entry's id, day
    and period). If anything is added, moved or removed, the value changes.
    """
    rows = (TimetableEntry.objects
            .filter(Q(assignment__year_id=year_id, assignment__subject__semester=semester)
                    | Q(class_activity__year_id=year_id, class_activity__semester=semester))
            .order_by("id")
            .values_list("id", "day_of_week", "time_slot_id"))
    return hashlib.sha256(repr(list(rows)).encode()).hexdigest()


def _creator_is_admin(job):
    from .views import is_admin
    return job.created_by is not None and is_admin(job.created_by)


def _make_guard(job, year_id, semester, fingerprint):
    """Runs inside the save transaction, just before the new entries are written."""
    def guard():
        # lock this class's approval row until the save commits
        approval = (TimetableApproval.objects.select_for_update()
                    .filter(year_id=year_id, semester=semester).first())
        if class_fingerprint(year_id, semester) != fingerprint:
            raise TimetableChanged(CHANGED_MESSAGE)
        if (approval and approval.status == TimetableApproval.Status.SUBMITTED
                and not _creator_is_admin(job)):
            raise TimetableChanged(LOCKED_MESSAGE)
    return guard


@shared_task(name="timetable.autofill")
def run_autofill(job_id):
    # queued -> running only once: a second delivery of the same job does nothing
    if not mark_running(job_id):
        return "skipped"

    job = BackgroundJob.objects.get(id=job_id)

    # safety: the task runs inside the college that started it (config/celery.py
    # switches the schema); a job of another college is never touched
    if job.college != connection.schema_name:
        mark_failed(job_id, f"Job belongs to college '{job.college}', "
                            f"this task ran in '{connection.schema_name}'.")
        return "failed"

    p = job.params
    try:
        room = Room.objects.filter(pk=p["room"]).first() if p.get("room") else None
        # STEP 6.4: remember what the class looked like before the solver starts
        before = class_fingerprint(p["year"], p["semester"])
        created, message, not_placed = autofill(
            year_id=p["year"],
            semester=p["semester"],
            room=room,
            subject_ids=p.get("subjects"),
            activity_ids=p.get("activities"),
            before_save=_make_guard(job, p["year"], p["semester"], before),
        )
    except TimetableChanged as e:
        mark_failed(job_id, str(e))
        return "failed"
    except SoftTimeLimitExceeded:
        mark_failed(job_id, "Auto-fill took too long and was stopped. Please try again.")
        return "failed"
    except Exception:
        log.exception("Auto-fill job %s failed", job_id)
        mark_failed(job_id, "Auto-fill failed because of an unexpected error. "
                            "Please try again or contact the admin.")
        return "failed"

    mark_done(job_id, {"created": created, "message": message, "not_placed": not_placed})
    return "done"