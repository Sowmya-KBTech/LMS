"""Step 6.3 - timetable auto-fill as a background (Celery) job."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from config import celery_app
from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department
from modules.automation.background import start_job
from modules.automation.models import BackgroundJob
from modules.timetable.models import TimeSlot, TimetableEntry
from modules.timetable.tasks import run_autofill

User = get_user_model()
START = "/api/timetable/autofill/start/"
OLD = "/api/timetable/autofill/"


class AutofillJobTests(TestCase):

    def setUp(self):
        # run Celery tasks inside the test (no worker needed)
        from config.celery import set_eager      # works on Celery 5.5 and 5.7
        self.addCleanup(set_eager, set_eager(True))

        dept = Department.objects.create(name="Autofill Dept", code="AF")
        course = Course.objects.create(name="B.E Autofill")
        self.year = Year.objects.create(course=course, year_number=1)
        self.admin = User.objects.create_user("af_admin", "a@example.com", "pw", role="admin")
        self.teacher = User.objects.create_user("af_teacher", "t@example.com", "pw",
                                                role="teacher", department=dept)
        self.student = User.objects.create_user("af_student", "s@example.com", "pw", role="student")
        for i, code in enumerate(["AF101", "AF102"]):
            subj = Subject.objects.create(name=f"Subject {i}", code=code, year=self.year,
                                          semester=1, weekly_hours=2)
            TeachingAssignment.objects.create(teacher=self.teacher, course=course,
                                              year=self.year, subject=subj)
        for n in range(1, 5):
            TimeSlot.objects.create(period_no=n, start_time=datetime.time(8 + n, 0),
                                    end_time=datetime.time(8 + n, 50))
        self.body = {"year": self.year.id, "semester": 1}

    def post(self, url, user, body=None):
        return self.client.post(
            url, body if body is not None else self.body, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

    def entries(self):
        return TimetableEntry.objects.filter(assignment__year=self.year).count()

    # ---------------- start endpoint ----------------
    def test_start_returns_job_and_places_periods(self):
        r = self.post(START, self.admin)
        self.assertEqual(r.status_code, 202)
        job = BackgroundJob.objects.get(id=r.json()["job_id"])
        self.assertEqual(job.status, "done")                 # eager mode: already finished
        self.assertEqual(job.kind, "timetable_autofill")
        self.assertEqual(job.lock_key, f"timetable:{self.year.id}:1")
        self.assertEqual(job.result["created"], 4)           # 2 subjects x 2 hours
        self.assertEqual(self.entries(), 4)

    def test_status_api_shows_the_result(self):
        job_id = self.post(START, self.admin).json()["job_id"]
        r = self.client.get(f"/api/jobs/{job_id}/",
                            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.admin).access_token}")
        self.assertEqual(r.json()["status"], "done")
        self.assertIn("Placed", r.json()["result"]["message"])

    def test_second_start_while_running_is_refused(self):
        running = start_job("timetable_autofill", self.admin, f"timetable:{self.year.id}:1")
        r = self.post(START, self.admin)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["job_id"], str(running.id))
        self.assertEqual(self.entries(), 0)

    def test_other_class_is_not_blocked(self):
        start_job("timetable_autofill", self.admin, "timetable:999:1")
        self.assertEqual(self.post(START, self.admin).status_code, 202)

    def test_redis_down_gives_503_and_failed_job(self):
        with mock.patch("modules.timetable.tasks.run_autofill.delay",
                        side_effect=ConnectionError("Redis down")):
            r = self.post(START, self.admin)
        self.assertEqual(r.status_code, 503)
        job = BackgroundJob.objects.get(id=r.json()["job_id"])
        self.assertEqual(job.status, "failed")
        # the lock is free again: a new try is allowed
        self.assertEqual(self.post(START, self.admin).status_code, 202)

    def test_permissions_unchanged(self):
        self.assertEqual(self.post(START, self.student).status_code, 403)
        self.assertEqual(self.post(START, self.teacher).status_code, 403)   # not HOD
        self.assertEqual(BackgroundJob.objects.count(), 0)

    def test_missing_year_is_400(self):
        self.assertEqual(self.post(START, self.admin, {"semester": 1}).status_code, 400)

    # ---------------- the task itself ----------------
    def test_task_records_solver_error(self):
        job = start_job("timetable_autofill", self.admin, "", {"year": self.year.id, "semester": 1})
        with mock.patch("modules.timetable.tasks.autofill", side_effect=RuntimeError("boom")):
            run_autofill(str(job.id))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("unexpected error", job.error)

    def test_task_runs_only_once(self):
        job = start_job("timetable_autofill", self.admin, "", {"year": self.year.id, "semester": 1})
        self.assertEqual(run_autofill(str(job.id)), "done")
        self.assertEqual(run_autofill(str(job.id)), "skipped")   # duplicate delivery
        self.assertEqual(self.entries(), 4)

    def test_task_refuses_job_of_another_college(self):
        # the task runs inside the test college; this job says it belongs to college_a
        job = BackgroundJob.objects.create(kind="timetable_autofill", college="college_a",
                                           params={"year": self.year.id, "semester": 1})
        self.assertEqual(run_autofill(str(job.id)), "failed")
        job.refresh_from_db()
        self.assertIn("college_a", job.error)
        self.assertEqual(self.entries(), 0)

    # ---------------- old waiting endpoint was removed (20-11-2026) ----------------
    def test_old_endpoint_is_gone(self):
        r = self.post(OLD, self.admin)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(TimetableEntry.objects.count(), 0)     # nothing was placed