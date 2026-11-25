"""Step 6.2 - BackgroundJob table, helpers and status API."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from modules.automation.background import (
    STUCK_AFTER_MINUTES, JobAlreadyRunning, expire_stuck, mark_done,
    mark_failed, mark_running, start_job,
)
from modules.automation.models import BackgroundJob

User = get_user_model()
LOCK = "timetable:1:3"


class BackgroundJobHelperTests(TestCase):

    def setUp(self):
        self.hod = User.objects.create_user("bj_hod", "h@example.com", "pw", role="teacher")

    def test_start_job_creates_queued_job(self):
        job = start_job("timetable_autofill", self.hod, LOCK, {"year": 1, "semester": 3})
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.college, "test")            # the college schema it was started in
        self.assertEqual(job.created_by, self.hod)
        self.assertEqual(job.params, {"year": 1, "semester": 3})

    def test_second_job_same_lock_is_refused(self):
        first = start_job("timetable_autofill", self.hod, LOCK)
        with self.assertRaises(JobAlreadyRunning) as ctx:
            start_job("timetable_autofill", self.hod, LOCK)
        self.assertEqual(ctx.exception.job.id, first.id)
        self.assertEqual(BackgroundJob.objects.count(), 1)

    def test_refused_while_running_too(self):
        first = start_job("timetable_autofill", self.hod, LOCK)
        self.assertTrue(mark_running(first.id))
        with self.assertRaises(JobAlreadyRunning):
            start_job("timetable_autofill", self.hod, LOCK)

    def test_new_job_allowed_after_done_or_failed(self):
        a = start_job("timetable_autofill", self.hod, LOCK)
        mark_done(a.id, {"created": 5})
        b = start_job("timetable_autofill", self.hod, LOCK)
        mark_failed(b.id, "boom")
        c = start_job("timetable_autofill", self.hod, LOCK)
        self.assertEqual(c.status, "queued")

    def test_different_classes_can_run_together(self):
        start_job("timetable_autofill", self.hod, "timetable:1:3")
        start_job("timetable_autofill", self.hod, "timetable:2:5")
        self.assertEqual(BackgroundJob.objects.count(), 2)

    def test_empty_lock_key_has_no_limit(self):
        start_job("export", self.hod)
        start_job("export", self.hod)
        self.assertEqual(BackgroundJob.objects.count(), 2)

    def test_mark_running_only_once(self):
        job = start_job("timetable_autofill", self.hod, LOCK)
        self.assertTrue(mark_running(job.id))
        self.assertFalse(mark_running(job.id))       # a duplicate delivery must not run it again

    def test_done_and_failed_record_result_and_time(self):
        a = start_job("x", self.hod)
        mark_done(a.id, {"created": 7})
        a.refresh_from_db()
        self.assertEqual((a.status, a.result["created"]), ("done", 7))
        self.assertIsNotNone(a.finished_at)
        b = start_job("x", self.hod)
        mark_failed(b.id, "Solver error")
        b.refresh_from_db()
        self.assertEqual((b.status, b.error), ("failed", "Solver error"))

    def test_stuck_job_is_expired_and_frees_the_lock(self):
        old = start_job("timetable_autofill", self.hod, LOCK)
        BackgroundJob.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(minutes=STUCK_AFTER_MINUTES + 1))
        new = start_job("timetable_autofill", self.hod, LOCK)    # allowed: old one expired
        old.refresh_from_db()
        self.assertEqual(old.status, "failed")
        self.assertIn("took too long", old.error)
        self.assertEqual(new.status, "queued")

    def test_fresh_job_is_not_expired(self):
        start_job("timetable_autofill", self.hod, LOCK)
        self.assertEqual(expire_stuck(), 0)


class JobStatusApiTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user("bj_owner", "o@example.com", "pw", role="teacher")
        self.other = User.objects.create_user("bj_other", "x@example.com", "pw", role="teacher")
        self.admin = User.objects.create_user("bj_admin", "a@example.com", "pw", role="admin")
        self.job = start_job("timetable_autofill", self.owner, LOCK, {"year": 1})

    def get(self, user, job_id=None):
        headers = {}
        if user:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(user).access_token}"
        return self.client.get(f"/api/jobs/{job_id or self.job.id}/", **headers)

    def test_owner_sees_status(self):
        r = self.get(self.owner)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data["id"], data["status"], data["kind"]),
                         (str(self.job.id), "queued", "timetable_autofill"))

    def test_shows_result_when_done(self):
        mark_done(self.job.id, {"created": 12, "message": "Placed all 12"})
        data = self.get(self.owner).json()
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["result"]["created"], 12)

    def test_main_admin_can_see_any_job(self):
        self.assertEqual(self.get(self.admin).status_code, 200)

    def test_other_user_gets_404(self):
        self.assertEqual(self.get(self.other).status_code, 404)

    def test_unknown_job_404(self):
        self.assertEqual(self.get(self.owner, "00000000-0000-0000-0000-000000000000").status_code, 404)

    def test_login_required(self):
        self.assertEqual(self.get(None).status_code, 401)

    def test_stuck_job_shows_failed(self):
        later = timezone.now() + timedelta(minutes=STUCK_AFTER_MINUTES + 1)
        with mock.patch("modules.automation.background.timezone.now", return_value=later):
            data = self.get(self.owner).json()
        self.assertEqual(data["status"], "failed")
        self.assertIn("took too long", data["error"])