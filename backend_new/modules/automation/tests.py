"""
BACKGROUND JOB TESTS (meeting point 12)

Proves the nightly jobs send the right notice, to the right people, on the
right day - and never twice:

  fee_due_soon / fee_overdue / fee_grace_ended   (fees)
  low_attendance                                 (weekly, attendance)
  notify_results_published                       (event: results published)
  run_daily_jobs                                 (the runner itself)

Every test fixes "today" (JobContext(today=...)), so the results never
depend on the date the tests are run.

Run:  python manage.py test modules.automation -v 2
"""
import datetime
from decimal import Decimal
from io import StringIO
from unittest import mock, skipUnless

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from config.module_registry import module_enabled
from core.academics.models import Course, Subject, TeachingAssignment, Year, YearTutor
from core.notifications.models import Notification
from core.users.models import Department, ParentProfile, User
from modules.automation import jobs
from modules.automation.jobs import JobContext, due_today
from modules.automation.models import AutomationSetting, JobRun, ReminderLog

TODAY = datetime.date(2026, 11, 16)          # a Monday
DAY = datetime.timedelta(days=1)


class JobTestBase(TestCase):
    """One student with one parent, plus an accounts admin."""

    def setUp(self):
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mechanical")
        self.year = Year.objects.create(course=self.course, year_number=1)

        self.student = User.objects.create_user(
            username="aarthi", password="x", role="student", department=self.dept,
            course=self.course, year=1, semester=1, first_name="Aarthi",
        )
        self.parent = User.objects.create_user(username="ravi", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

        self.accounts = User.objects.create_user(
            username="accounts1", password="x", role="admin", sub_role="accounts_admin",
        )
        self.rules = AutomationSetting.current()          # defaults: 3 days before, 7 grace days

    # ---------- helpers ----------
    def ctx(self, today=TODAY, dry_run=False):
        return JobContext(today=today, dry_run=dry_run)

    def notices(self, user, title_start):
        return Notification.objects.filter(recipient=user, title__startswith=title_start).count()


# =====================================================================
#  1) FEE REMINDERS
# =====================================================================
@skipUnless(module_enabled("fees"), "fees module is off")
class FeeReminderTests(JobTestBase):

    def fee(self, due, status="pending", paid=0):
        from modules.fees.models import Fee
        return Fee.objects.create(student=self.student, term="Sem 1 Tuition",
                                  amount=Decimal("50000"), paid_amount=Decimal(paid),
                                  due_date=due, status=status)

    # ---- due soon ----
    def test_due_in_3_days_reminds_student_and_parent(self):
        self.fee(TODAY + 3 * DAY)
        sent = jobs.fee_due_soon(self.ctx())
        self.assertEqual(sent, 2)
        self.assertEqual(self.notices(self.student, "Fee due in 3 days"), 1)
        self.assertEqual(self.notices(self.parent, "Fee due in 3 days"), 1)

    def test_due_tomorrow_says_tomorrow(self):
        self.fee(TODAY + DAY)
        jobs.fee_due_soon(self.ctx())
        self.assertEqual(self.notices(self.student, "Fee due tomorrow"), 1)

    def test_due_in_4_days_is_too_early(self):
        self.fee(TODAY + 4 * DAY)
        self.assertEqual(jobs.fee_due_soon(self.ctx()), 0)

    def test_remind_days_before_comes_from_settings(self):
        self.rules.fee_remind_days_before = 5
        self.rules.save()
        self.fee(TODAY + 5 * DAY)
        self.assertEqual(jobs.fee_due_soon(self.ctx()), 2)

    def test_paid_fee_is_never_reminded(self):
        self.fee(TODAY + 2 * DAY, status="paid", paid=50000)
        self.assertEqual(jobs.fee_due_soon(self.ctx()), 0)

    def test_partly_paid_fee_is_reminded_with_the_balance(self):
        self.fee(TODAY + 2 * DAY, status="partial", paid=20000)
        jobs.fee_due_soon(self.ctx())
        n = Notification.objects.get(recipient=self.student, title__startswith="Fee due")
        self.assertIn("30,000", n.message)                 # 50,000 - 20,000

    # ---- no duplicates ----
    def test_running_twice_does_not_send_twice(self):
        self.fee(TODAY + 3 * DAY)
        self.assertEqual(jobs.fee_due_soon(self.ctx()), 2)
        self.assertEqual(jobs.fee_due_soon(self.ctx()), 0)                 # same night again
        self.assertEqual(jobs.fee_due_soon(self.ctx(TODAY + DAY)), 0)      # next night, same stage
        self.assertEqual(self.notices(self.student, "Fee due"), 1)

    def test_dry_run_sends_and_logs_nothing(self):
        self.fee(TODAY + 3 * DAY)
        self.assertEqual(jobs.fee_due_soon(self.ctx(dry_run=True)), 2)     # would send 2
        self.assertEqual(self.notices(self.student, "Fee due"), 0)
        self.assertFalse(ReminderLog.objects.exists())

    # ---- overdue (inside the grace period) ----
    def test_overdue_inside_grace_reminds_with_the_last_date(self):
        self.fee(TODAY - 2 * DAY)                           # grace ends TODAY + 5
        self.assertEqual(jobs.fee_overdue(self.ctx()), 2)
        n = Notification.objects.get(recipient=self.student, title__startswith="Fee overdue")
        self.assertIn((TODAY + 5 * DAY).strftime("%d-%m-%Y"), n.message)

    def test_overdue_stops_when_grace_is_over(self):
        self.fee(TODAY - 7 * DAY)                           # grace ended today
        self.assertEqual(jobs.fee_overdue(self.ctx()), 0)

    # ---- grace ended ----
    def test_grace_ended_tells_student_parent_and_accounts(self):
        self.fee(TODAY - 7 * DAY)
        self.assertEqual(jobs.fee_grace_ended(self.ctx()), 3)
        self.assertEqual(self.notices(self.accounts, "Grace period ended"), 1)

    def test_grace_ended_catches_up_two_missed_nights_only(self):
        self.fee(TODAY - 9 * DAY)                           # 2 nights late: still sent
        self.assertEqual(jobs.fee_grace_ended(self.ctx()), 3)
        self.fee(TODAY - 10 * DAY)                          # 3 nights late: old news, skipped
        self.assertEqual(jobs.fee_grace_ended(self.ctx()), 0)

    def test_grace_days_come_from_settings(self):
        self.rules.fee_grace_days = 10
        self.rules.save()
        self.fee(TODAY - 7 * DAY)
        self.assertEqual(jobs.fee_grace_ended(self.ctx()), 0)   # 3 grace days still left
        self.assertEqual(jobs.fee_overdue(self.ctx()), 2)

    # ---- switched off ----
    def test_fee_reminders_off_stops_every_fee_job(self):
        self.rules.fee_reminders_on = False
        self.rules.save()
        self.fee(TODAY + 3 * DAY)
        self.fee(TODAY - 2 * DAY)
        self.fee(TODAY - 7 * DAY)
        ctx = self.ctx()
        self.assertEqual(jobs.fee_due_soon(ctx) + jobs.fee_overdue(ctx) + jobs.fee_grace_ended(ctx), 0)


# =====================================================================
#  2) WEEKLY LOW-ATTENDANCE ALERT
# =====================================================================
@skipUnless(module_enabled("attendance"), "attendance module is off")
class LowAttendanceTests(JobTestBase):

    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user(username="t1", password="x", role="teacher")
        self.tutor = User.objects.create_user(username="tutor1", password="x", role="teacher")
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.year)
        subject = Subject.objects.create(name="Thermodynamics", year=self.year, semester=1)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                    year=self.year, subject=subject)

    def attendance(self, present, duty_leave=0, total=10):
        from modules.attendance.models import Attendance
        statuses = ["present"] * present + ["duty_leave"] * duty_leave
        statuses += ["absent"] * (total - len(statuses))
        for hour, status in enumerate(statuses, start=1):
            Attendance.objects.create(teaching_assignment=self.ta, student=self.student,
                                      date=TODAY - 3 * DAY, hour=hour, status=status,
                                      marked_by=self.teacher)

    def test_below_minimum_alerts_student_parent_and_tutor(self):
        self.attendance(present=6)                          # 60% < 75%
        self.assertEqual(jobs.low_attendance(self.ctx()), 3)
        self.assertEqual(self.notices(self.student, "Attendance below"), 1)
        self.assertEqual(self.notices(self.parent, "Attendance below"), 1)
        tutor_notice = Notification.objects.get(recipient=self.tutor)
        self.assertIn("aarthi (60%)", tutor_notice.message)

    def test_above_minimum_sends_nothing(self):
        self.attendance(present=9)                          # 90%
        self.assertEqual(jobs.low_attendance(self.ctx()), 0)

    def test_on_duty_counts_as_attended(self):
        self.attendance(present=7, duty_leave=1)            # 80% with OD
        self.assertEqual(jobs.low_attendance(self.ctx()), 0)

    @skipUnless(module_enabled("exams"), "exams module is off")
    def test_minimum_comes_from_the_colleges_eligibility_rule(self):
        from modules.exams.models import EligibilitySetting
        rule = EligibilitySetting.current()
        rule.min_attendance = 50
        rule.save()
        self.attendance(present=6)                          # 60% >= 50%
        self.assertEqual(jobs.low_attendance(self.ctx()), 0)

    def test_once_per_week_then_again_next_week(self):
        self.attendance(present=6)
        self.assertEqual(jobs.low_attendance(self.ctx()), 3)
        self.assertEqual(jobs.low_attendance(self.ctx(TODAY + 2 * DAY)), 0)   # same week
        self.assertEqual(jobs.low_attendance(self.ctx(TODAY + 7 * DAY)), 3)   # next week

    def test_alerts_off_sends_nothing(self):
        self.rules.attendance_alerts_on = False
        self.rules.save()
        self.attendance(present=6)
        self.assertEqual(jobs.low_attendance(self.ctx()), 0)

    def test_runs_only_on_the_weekday_set_in_settings(self):
        self.assertTrue(due_today("weekly:setting", TODAY))            # Monday (default)
        self.assertFalse(due_today("weekly:setting", TODAY + DAY))     # Tuesday
        self.rules.attendance_alert_weekday = 2                        # Wednesday
        self.rules.save()
        self.assertFalse(due_today("weekly:setting", TODAY))
        self.assertTrue(due_today("weekly:setting", TODAY + 2 * DAY))


# =====================================================================
#  3) RESULTS PUBLISHED  (event, not nightly)
# =====================================================================
@skipUnless(module_enabled("exams"), "exams module is off")
class ResultsPublishedTests(JobTestBase):

    def result(self):
        from modules.exams.models import SemesterResult
        return SemesterResult.objects.create(student=self.student, semester=1)

    def test_student_and_parent_told_once(self):
        r = self.result()
        self.assertEqual(jobs.notify_results_published(r), 2)
        self.assertEqual(jobs.notify_results_published(r), 0)          # published again
        self.assertEqual(self.notices(self.student, "Semester 1 results published"), 1)
        self.assertEqual(self.notices(self.parent, "Semester 1 results published"), 1)

    def test_publish_button_sends_the_notice(self):
        r = self.result()
        admin = User.objects.create_user(username="exam1", password="x", role="admin",
                                         sub_role="exam_admin")
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.post(f"/api/semester-results/{r.id}/publish/")
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", resp))
        self.assertEqual(self.notices(self.student, "Semester 1 results published"), 1)
        self.assertEqual(self.notices(self.parent, "Semester 1 results published"), 1)


# =====================================================================
#  4) THE RUNNER  (manage.py run_daily_jobs)
# =====================================================================
class RunnerTests(JobTestBase):

    def run_jobs(self, *args):
        out = StringIO()
        call_command("run_daily_jobs", *args, stdout=out, no_color=True)
        return out.getvalue()

    def test_list_shows_every_job(self):
        out = self.run_jobs("--list")
        for name, _fn, _when in jobs.JOBS:
            self.assertIn(name, out)

    @skipUnless(module_enabled("fees"), "fees module is off")
    def test_a_run_is_written_to_the_job_diary(self):
        from modules.fees.models import Fee
        import django.utils.timezone as tz
        Fee.objects.create(student=self.student, term="Sem 1 Tuition", amount=Decimal("50000"),
                           due_date=tz.localdate() + 2 * DAY)
        self.run_jobs("--only", "fee_due_soon")
        run = JobRun.objects.get(job="fee_due_soon")
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.sent_count, 2)
        self.assertIsNotNone(run.finished_at)

    def test_one_failing_job_does_not_stop_the_others(self):
        def broken(ctx):
            raise RuntimeError("database went away")

        def fine(ctx):
            return 5

        fake_jobs = [("broken_job", broken, "daily"), ("fine_job", fine, "daily")]
        with mock.patch("modules.automation.management.commands.run_daily_jobs.JOBS", fake_jobs):
            out = self.run_jobs()
        self.assertIn("Done: 1 ok, 1 failed.", out)
        failed = JobRun.objects.get(job="broken_job")
        self.assertEqual(failed.status, "failed")
        self.assertIn("database went away", failed.message)
        self.assertEqual(JobRun.objects.get(job="fine_job").sent_count, 5)

    def test_unknown_job_name_runs_nothing(self):
        err = StringIO()
        call_command("run_daily_jobs", "--only", "no_such_job", stdout=StringIO(), stderr=err)
        self.assertIn("Unknown job", err.getvalue())
        self.assertFalse(JobRun.objects.exists())
