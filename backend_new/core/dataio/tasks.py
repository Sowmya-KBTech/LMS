"""
STEP 7.1: Excel/CSV import as a background (Celery) job.

The request reads the uploaded file and stores its rows in the BackgroundJob
row; the worker runs the SAME checks/save as before (engine.run) and stores the
report in the job. The browser follows it with GET /api/jobs/<job_id>/.
"""
import datetime
import json
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection
from django.core.serializers.json import DjangoJSONEncoder

from modules.automation.background import mark_done, mark_failed, mark_running
from modules.automation.models import BackgroundJob

from . import registry
from .engine import OptionError, run

log = logging.getLogger(__name__)


# ---- rows -> JSON and back (Excel dates must survive the trip) ----
def rows_to_json(rows):
    def cell(v):
        if isinstance(v, datetime.date):
            return {"__date__": v.isoformat()}
        return v
    return [[n, {k: cell(v) for k, v in values.items()}] for n, values in rows]


def rows_from_json(data):
    def cell(v):
        if isinstance(v, dict) and "__date__" in v:
            return datetime.date.fromisoformat(v["__date__"])
        return v
    return [(n, {k: cell(v) for k, v in values.items()}) for n, values in data]


def _json_safe(report):
    return json.loads(json.dumps(report, cls=DjangoJSONEncoder))


@shared_task(name="dataio.run_import")
def run_import(job_id):
    # queued -> running only once: a second delivery of the same job does nothing
    if not mark_running(job_id):
        return "skipped"
    try:
        return _run_import(job_id)
    finally:
        # the uploaded rows (names, emails ...) are not kept once the job is over
        _drop_rows(job_id)


def _drop_rows(job_id):
    job = BackgroundJob.objects.filter(id=job_id).first()
    if job and job.params.get("rows"):
        job.params["rows"] = []
        BackgroundJob.objects.filter(id=job_id).update(params=job.params)


def _run_import(job_id):
    job = BackgroundJob.objects.select_related("created_by").get(id=job_id)
    # safety: the task runs inside the college that started it (config/celery.py)
    if job.college != connection.schema_name:
        mark_failed(job_id, f"Job belongs to college '{job.college}', "
                            f"this task ran in '{connection.schema_name}'.")
        return "failed"

    p = job.params
    user = job.created_by
    imp = registry.get(p["key"])
    if imp is None or user is None or not imp.can_use(user):
        mark_failed(job_id, "This import is not available for this user any more.")
        return "failed"

    try:
        options = imp.resolve_options(user, p.get("options") or {})
        blocked = imp.write_blocked(options)
        if blocked:
            mark_failed(job_id, blocked)
            return "failed"
        report = run(imp, user, p["headers"], rows_from_json(p["rows"]),
                     mode=p.get("mode", "add"), commit=p["commit"],
                     file_name=p.get("file_name", ""), options=options)
    except OptionError as e:
        mark_failed(job_id, e.message)
        return "failed"
    except SoftTimeLimitExceeded:
        mark_failed(job_id, "The import took too long and was stopped. Nothing was saved. "
                            "Try a smaller file.")
        return "failed"
    except Exception:
        log.exception("Import job %s failed", job_id)
        mark_failed(job_id, "The import failed because of an unexpected error. Nothing was saved.")
        return "failed"

    # "done" = the check finished. Whether rows were saved is in report["saved"]
    # (an import with errors in the file is done, with saved = false).
    report = _json_safe(report)
    if report.get("extra"):
        # STEP 7.2: new accounts' temporary passwords are shown ONCE to the person
        # who ran the import, then removed (see automation job_status).
        report["_one_time"] = ["extra"]
    mark_done(job_id, report)
    return "done"