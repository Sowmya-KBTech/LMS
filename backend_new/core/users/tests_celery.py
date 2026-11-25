"""Step 6.1 - Celery is set up correctly (no worker needed for these tests)."""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from config import celery_app
from core.users.tasks import ping


class CelerySetupTests(SimpleTestCase):

    def setUp(self):
        # run tasks inside the test, so no worker or Redis is needed
        from config.celery import set_eager      # works on Celery 5.5 and 5.7
        self.addCleanup(set_eager, set_eager(True))

    def test_app_reads_django_settings(self):
        self.assertEqual(celery_app.main, "kbtech_campus")
        self.assertEqual(celery_app.conf.task_serializer, "json")
        self.assertEqual(celery_app.conf.timezone, "Asia/Kolkata")
        self.assertEqual(celery_app.conf.task_time_limit, 300)

    def test_ping_task_is_registered(self):
        self.assertIn("lms.ping", celery_app.tasks)

    def test_ping_runs_and_answers(self):
        self.assertEqual(ping.delay().get(timeout=5)["pong"], True)

    def test_celery_check_command_passes(self):
        out = StringIO()
        call_command("celery_check", stdout=out)
        self.assertIn("Celery check  : OK", out.getvalue())

class CollegeAwareTaskTests(SimpleTestCase):
    """Multi-college: a job runs inside the college that sent it (config/celery.py)."""

    def setUp(self):
        from config.celery import set_eager      # works on Celery 5.5 and 5.7
        self.addCleanup(set_eager, set_eager(True))

    def test_a_job_runs_in_the_college_that_sent_it(self):
        from django.db import connection
        from django_tenants.utils import schema_context
        with schema_context("college_a"):
            answer = ping.delay().get(timeout=5)
        self.assertEqual(answer["college"], "college_a")
        self.assertEqual(connection.schema_name, "test")     # switched back afterwards

    def test_a_job_sent_outside_any_college_runs_on_the_platform(self):
        from django_tenants.utils import schema_context
        with schema_context("public"):
            answer = ping.delay().get(timeout=5)
        self.assertEqual(answer["college"], "public")

    def test_celery_check_proves_the_college(self):
        out = StringIO()
        call_command("celery_check", "--college", "college_b", stdout=out)
        self.assertIn("College       : college_b", out.getvalue())
        self.assertIn("Celery check  : OK", out.getvalue())
