"""
python manage.py celery_check

Sends the 'ping' task and waits for the answer, to prove that
Django -> Redis -> Celery worker -> back is working.

    python manage.py celery_check --college abc

also proves the worker ran the job inside that college (multi-college).
"""
from celery.exceptions import TimeoutError as CeleryTimeout
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.celery import app
from core.users.tasks import ping

WORKER_HINT = (
    " Is the Celery worker running? In a new window (inside backend_new):"
    "  .\\venv\\Scripts\\celery.exe -A config worker --pool=solo -l info"
)
REDIS_HINT = " Is Redis running? Start it with: docker start kbtech-redis"


class Command(BaseCommand):
    help = "Check Celery: send a ping job and wait for the worker's answer."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=float, default=10.0,
                            help="Seconds to wait for the worker (default 10).")
        parser.add_argument("--college", default="",
                            help="College code: send the job from inside this college.")

    def handle(self, *args, **opts):
        eager = bool(app.conf.task_always_eager)
        broker = settings.CELERY_BROKER_URL or "(none)"
        self.stdout.write(f"Celery mode   : {'eager (no broker - jobs run inside the request)' if eager else 'worker'}")
        self.stdout.write(f"Broker URL    : {broker}")
        college = (opts.get("college") or "").lower()
        self.stdout.write(f"College       : {college or '(none - platform)'}")

        try:
            if college:
                from django_tenants.utils import schema_context
                with schema_context(college):
                    result = ping.delay()
            else:
                result = ping.delay()
            data = result.get(timeout=opts["timeout"])
        except CeleryTimeout:
            raise CommandError(f"Celery check  : FAILED - no answer in {opts['timeout']:.0f}s." + WORKER_HINT)
        except Exception as e:  # e.g. Redis not reachable
            raise CommandError(f"Celery check  : FAILED - {e.__class__.__name__}: {e}." + REDIS_HINT)

        if not (isinstance(data, dict) and data.get("pong")):
            raise CommandError(f"Celery check  : FAILED - unexpected answer {data!r}")
        if college and data.get("college") != college:
            raise CommandError(f"Celery check  : FAILED - the job ran in '{data.get('college')}', "
                               f"not in '{college}'.")
        self.stdout.write(self.style.SUCCESS("Celery check  : OK"))