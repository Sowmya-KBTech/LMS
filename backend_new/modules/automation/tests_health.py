"""Step 8.4 - health check of Redis, worker, Beat and the nightly jobs (read-only)."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from modules.automation import health
from modules.automation.models import JobRun
from modules.automation.tasks import heartbeat

User = get_user_model()
BROKER = "redis://fake:6379/1"


class FakeRedis:
    """Just enough of Redis for the health check."""

    def __init__(self, up=True, waiting=0):
        self.up, self.waiting, self.data = up, waiting, {}

    def ping(self):
        if not self.up:
            raise ConnectionError("down")
        return True

    def llen(self, _name):
        return self.waiting

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value.encode()


@override_settings(CELERY_BROKER_URL=BROKER)
class HealthCheckTests(TestCase):

    def setUp(self):
        self.redis = FakeRedis()
        self.now = timezone.now()
        p1 = mock.patch.object(health, "_broker", lambda: self.redis)
        p2 = mock.patch.object(health, "_ping_workers", lambda: [{"celery@pc": {"ok": "pong"}}])
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def status(self, name):
        for c in health.check(self.now)["checks"]:
            if c["name"] == name:
                return c["status"], c["detail"]
        return None

    def beat(self, seconds_ago):
        health.record_heartbeat(self.now.timestamp() - seconds_ago)

    def nightly(self, hours_ago, status="ok", job="fee_due_soon", message="", dry=False):
        run = JobRun.objects.create(job=job, status=status, message=message, dry_run=dry)
        JobRun.objects.filter(pk=run.pk).update(started_at=self.now - timedelta(hours=hours_ago))

    # ---- Beat ----
    def test_fresh_heartbeat_is_ok(self):
        self.beat(60)
        self.assertEqual(self.status("Beat")[0], "ok")

    def test_old_heartbeat_is_a_problem(self):
        self.beat(20 * 60)
        st, detail = self.status("Beat")
        self.assertEqual(st, "problem")
        self.assertIn("20 minutes ago", detail)

    def test_no_heartbeat_is_a_problem(self):
        self.assertEqual(self.status("Beat")[0], "problem")

    def test_heartbeat_task_writes_the_time(self):
        heartbeat()
        self.assertEqual(self.status("Beat")[0], "ok")

    def test_heartbeat_is_platform_wide(self):
        # ONE Beat serves every college: its heartbeat counts for all of them
        # (Beat's heartbeat task runs outside any college; every college sees it)
        from django_tenants.utils import schema_context
        self.assertEqual(health._heartbeat_key(), "lms:platform:beat_heartbeat")
        with schema_context("public"):
            heartbeat()
        self.assertEqual(self.status("Beat")[0], "ok")

    # ---- Worker / queue / Redis ----
    def test_worker_not_answering_is_a_problem(self):
        with mock.patch.object(health, "_ping_workers", lambda: []):
            self.assertEqual(self.status("Worker")[0], "problem")
        self.assertEqual(self.status("Worker")[0], "ok")

    def test_jobs_piling_up_is_a_warning(self):
        self.redis.waiting = 25
        self.assertEqual(self.status("Waiting queue")[0], "warning")

    def test_redis_down_is_a_problem_and_the_rest_unknown(self):
        self.redis.up = False
        self.assertEqual(self.status("Redis (broker)")[0], "problem")
        for name in ("Worker", "Waiting queue", "Beat"):
            self.assertEqual(self.status(name)[0], "unknown")

    @override_settings(CELERY_BROKER_URL="")
    def test_without_celery_everything_is_unknown_not_a_problem(self):
        with mock.patch.object(health, "_broker", lambda: None):
            self.assertEqual(self.status("Worker")[0], "unknown")

    # ---- nightly jobs ----
    def test_never_ran_is_a_warning(self):
        self.assertEqual(self.status("Nightly jobs")[0], "warning")

    def test_recent_run_is_ok(self):
        self.nightly(hours_ago=15)
        self.assertEqual(self.status("Nightly jobs")[0], "ok")
        self.assertEqual(self.status("Last run failures")[0], "ok")

    def test_run_older_than_26_hours_is_a_problem(self):
        self.nightly(hours_ago=30)
        self.assertEqual(self.status("Nightly jobs")[0], "problem")

    def test_dry_runs_do_not_count(self):
        self.nightly(hours_ago=1, dry=True)
        self.assertEqual(self.status("Nightly jobs")[0], "warning")

    def test_failed_job_in_last_run_shows_the_error(self):
        self.nightly(hours_ago=5)
        self.nightly(hours_ago=5, status="failed", job="low_attendance", message="KeyError: 'x'")
        st, detail = self.status("Last run failures")
        self.assertEqual(st, "problem")
        self.assertIn("KeyError: 'x'", detail)

    def test_old_failures_from_an_earlier_night_are_not_repeated(self):
        self.nightly(hours_ago=29, status="failed", job="low_attendance", message="old")
        self.nightly(hours_ago=5)
        self.assertEqual(self.status("Last run failures")[0], "ok")

    def test_job_stuck_running_is_a_warning(self):
        self.nightly(hours_ago=3, status="running")
        self.assertEqual(self.status("Stuck jobs")[0], "warning")

    # ---- overall ----
    def test_overall_is_the_worst_status(self):
        self.beat(60)
        self.nightly(hours_ago=5)
        self.assertEqual(health.check(self.now)["overall"], "ok")
        self.redis.waiting = 25
        self.assertEqual(health.check(self.now)["overall"], "warning")
        with mock.patch.object(health, "_ping_workers", lambda: []):
            self.assertEqual(health.check(self.now)["overall"], "problem")

    def test_check_sends_nothing(self):
        before = JobRun.objects.count()
        health.check(self.now)
        self.assertEqual(JobRun.objects.count(), before)

    # ---- terminal command ----
    def test_command_prints_and_exits_1_on_problem(self):
        out = StringIO()
        with self.assertRaises(SystemExit) as e:
            call_command("task_health", stdout=out)
        self.assertEqual(e.exception.code, 1)
        self.assertIn("Overall: PROBLEM", out.getvalue())

    def test_command_ok_when_all_fine(self):
        self.beat(60)
        self.nightly(hours_ago=5)
        out = StringIO()
        call_command("task_health", stdout=out)
        self.assertIn("Overall: OK", out.getvalue())


@override_settings(CELERY_BROKER_URL=BROKER)
class HealthApiTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user("h_admin", "a@example.com", "pw", role="admin")
        self.teacher = User.objects.create_user("h_tch", "t@example.com", "pw", role="teacher")
        p1 = mock.patch.object(health, "_broker", lambda: FakeRedis())
        p2 = mock.patch.object(health, "_ping_workers", lambda: [])
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def get(self, user):
        token = RefreshToken.for_user(user).access_token
        return self.client.get("/api/automation/health/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_main_admin_sees_health(self):
        r = self.get(self.admin)
        self.assertEqual(r.status_code, 200)
        names = [c["name"] for c in r.json()["checks"]]
        self.assertEqual(names[:4], ["Redis (broker)", "Worker", "Waiting queue", "Beat"])
        self.assertEqual(r.json()["overall"], "problem")

    def test_others_get_403(self):
        self.assertEqual(self.get(self.teacher).status_code, 403)

    def test_heartbeat_is_in_the_beat_schedule(self):
        hb = settings.CELERY_BEAT_SCHEDULE["heartbeat"]
        self.assertEqual((hb["task"], hb["schedule"]), ("automation.heartbeat", 300.0))

class TaskHealthAllCollegesTests(TestCase):
    """Multi-college: the task_health command runs outside any college."""

    def test_outside_a_college_every_college_is_checked(self):
        from django_tenants.utils import schema_context
        with schema_context("public"):
            result = health.check()
        names = [c["name"] for c in result["checks"]]
        self.assertIn("Nightly jobs (test)", names)          # the test platform's one college
