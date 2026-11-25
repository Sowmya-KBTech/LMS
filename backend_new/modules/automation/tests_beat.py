"""Step 8.1 / 8.2 - Celery Beat schedule and "only one run at a time" locks."""
from io import StringIO

from celery.schedules import crontab
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from config import celery_app
from config.db_locks import _key, advisory_lock
from modules.automation.models import JobRun
from modules.automation.tasks import run_daily_jobs, send_email_queue


class HeldLock:
    """Hold a lock from a SECOND database connection, like another running process."""

    def __init__(self, name):
        self.key = _key(name)
        self.other = connection.copy()

    def __enter__(self):
        self.other.connect()
        with self.other.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", [self.key])
        return self

    def __exit__(self, *exc):
        with self.other.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", [self.key])
        self.other.close()


class BeatScheduleTests(TestCase):

    def test_schedule_has_both_jobs_at_the_right_times(self):
        s = settings.CELERY_BEAT_SCHEDULE
        self.assertEqual(s["nightly-jobs"]["task"], "automation.run_daily_jobs")
        self.assertEqual(s["nightly-jobs"]["schedule"], crontab(hour=0, minute=15))
        self.assertEqual(s["email-queue"]["task"], "notifications.send_email_queue")
        self.assertEqual(s["email-queue"]["schedule"], 600.0)
        self.assertEqual(celery_app.conf.timezone, "Asia/Kolkata")

    def test_tasks_are_registered(self):
        for name in ("automation.run_daily_jobs", "notifications.send_email_queue"):
            self.assertIn(name, celery_app.tasks)

    def test_nightly_task_runs_all_jobs_and_fills_the_diary(self):
        # multi-college: Beat's task goes through every active college
        # (run_for_all_colleges); the test platform has one, "test"
        summary = run_daily_jobs()
        self.assertEqual(summary, "Ran 'run_daily_jobs' for 1 college(s): 1 ok, 0 failed.")
        self.assertGreater(JobRun.objects.count(), 0)                # the diary of the test college

    def test_email_task_runs(self):
        self.assertEqual(send_email_queue(),
                         "Ran 'send_notification_emails' for 1 college(s): 1 ok, 0 failed.")


class OneRunAtATimeTests(TestCase):

    def run_cmd(self, *args):
        out = StringIO()
        call_command(*args, stdout=out, no_color=True)
        return out.getvalue()

    def test_lock_is_free_then_taken_then_free(self):
        with advisory_lock("demo") as first:
            self.assertTrue(first)
            with HeldLock("other-name"):
                pass                                   # a different name never blocks
        with HeldLock("demo"):
            with advisory_lock("demo") as second:
                self.assertFalse(second)               # someone else holds it
        with advisory_lock("demo") as third:
            self.assertTrue(third)                     # released again

    def test_email_run_skips_while_another_is_sending(self):
        with HeldLock("email_queue"):
            self.assertIn("still sending; skipped", self.run_cmd("send_notification_emails"))
        self.assertNotIn("skipped", self.run_cmd("send_notification_emails"))

    def test_nightly_run_skips_while_another_is_running(self):
        with HeldLock("daily_jobs"):
            out = self.run_cmd("run_daily_jobs")
            self.assertIn("still running; skipped", out)
            self.assertEqual(JobRun.objects.count(), 0)    # nothing ran
        self.assertIn("Done:", self.run_cmd("run_daily_jobs"))

    def test_dry_run_and_list_are_never_blocked(self):
        with HeldLock("daily_jobs"), HeldLock("email_queue"):
            self.assertIn("fee_due_soon", self.run_cmd("run_daily_jobs", "--list"))
            self.assertNotIn("skipped", self.run_cmd("run_daily_jobs", "--dry-run"))
            self.assertNotIn("skipped", self.run_cmd("send_notification_emails", "--dry-run"))

    def test_locks_are_per_college(self):
        from django_tenants.utils import schema_context
        with schema_context("college_a"):
            a = _key("email_queue")
        with schema_context("college_b"):
            b = _key("email_queue")
        self.assertNotEqual(a, b)