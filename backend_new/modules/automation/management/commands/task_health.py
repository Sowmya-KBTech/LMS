"""
STEP 8.4: show the health of the background system in the terminal.

    python manage.py task_health

Redis, the worker and Beat are shared by every college; the nightly-job lines
are shown once per active college. Exit code 1 when something is a PROBLEM,
so a server monitor can call it.
"""
import sys

from django.core.management.base import BaseCommand

from modules.automation.health import PROBLEM, check

MARK = {"ok": "OK     ", "warning": "WARNING", "problem": "PROBLEM", "unknown": "UNKNOWN"}


class Command(BaseCommand):
    help = "Check Redis, the Celery worker, Beat and the nightly jobs."

    def handle(self, *args, **options):
        result = check()
        for c in result["checks"]:
            self.stdout.write(f"{MARK[c['status']]}  {c['name']:<26} {c['detail']}")
        self.stdout.write(f"Overall: {result['overall'].upper()}")
        if result["overall"] == PROBLEM:
            sys.exit(1)