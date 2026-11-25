"""
Celery app for KB Tech Campus (Redis/Celery work, step 6; made multi-college).

Django sends a job (a "task") to Redis; a separate Celery *worker* program
picks it up and runs it, so the web request does not have to wait.

ONE worker serves EVERY college. Each college has its own PostgreSQL schema,
so a task must know which college it belongs to:

  - A task sent while handling a college's request (auto-fill, an import ...)
    carries that college's schema in a message header ("lms_college"), added
    by CollegeTask.apply_async(). The worker switches to that schema before
    the task runs, and back afterwards.
  - A task sent by Celery Beat has no college (Beat serves the whole platform).
    It runs in the public schema; the nightly job and the email queue then go
    through every active college themselves (run_for_all_colleges).

Start the worker (development, Windows):
    .\\venv\\Scripts\\celery.exe -A config worker --pool=solo -l info
Start Beat (exactly ONE for the whole platform):
    .\\venv\\Scripts\\celery.exe -A config beat -l info

Settings live in config/settings.py (all names start with CELERY_).
"""
import os

from celery import Celery, Task

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

COLLEGE_HEADER = "lms_college"


def _current_college():
    """The schema of the college this code is running in, or None outside any college."""
    from django.db import connection
    from django_tenants.utils import get_public_schema_name
    schema = getattr(connection, "schema_name", None)
    return schema if schema and schema != get_public_schema_name() else None


class CollegeTask(Task):
    """Every task runs inside the college that sent it."""

    def apply_async(self, args=None, kwargs=None, **options):
        headers = dict(options.pop("headers", None) or {})
        if COLLEGE_HEADER not in headers:
            college = _current_college()
            if college:
                headers[COLLEGE_HEADER] = college
        return super().apply_async(args, kwargs, headers=headers, **options)

    def _college(self):
        request = self.request
        college = getattr(request, COLLEGE_HEADER, None)          # worker: headers become attributes
        if not college:
            college = (getattr(request, "headers", None) or {}).get(COLLEGE_HEADER)   # eager mode
        return college

    def __call__(self, *args, **kwargs):
        college = self._college()
        if not college:
            return super().__call__(*args, **kwargs)
        from django_tenants.utils import schema_context
        with schema_context(college):
            return super().__call__(*args, **kwargs)


app = Celery("kbtech_campus", task_cls=CollegeTask)

# Read every CELERY_* setting from Django's settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Find tasks.py in every installed app automatically
app.autodiscover_tasks()


def set_eager(on):
    """
    Tests: run jobs inside the test (True) or send them to the worker (False).
    Returns the previous value. Celery 5.5 (the version for Python 3.9) ignores
    `app.conf.task_always_eager = True` when settings come from Django with the
    CELERY_ prefix, so the value is set under its Django name, which works on
    every Celery version.
    """
    old = bool(app.conf.task_always_eager)
    app.conf["CELERY_TASK_ALWAYS_EAGER"] = bool(on)
    return old


# step 8.4: send one heartbeat as soon as Beat starts, so the health check
# does not show "Beat: problem" for the first 5 minutes after a restart.
from celery.signals import beat_init  # noqa: E402


@beat_init.connect
def _first_heartbeat(sender=None, **kwargs):
    app.send_task("automation.heartbeat")
