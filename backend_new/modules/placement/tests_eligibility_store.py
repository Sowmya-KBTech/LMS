"""
Saved placement eligibility (meeting point 10):

  * a separate table holds each student's result per job role
  * it refreshes when a drive is published and whenever something the rules
    read changes (rule edited, offer accepted, marks verified, policy
    switched, student promoted), plus a nightly command / Refresh button
  * publishing a drive sends ONE in-app notice per eligible student per role
  * screens read the table; APPLY still checks live, so a stale row can
    never let an ineligible student in

Run:  python manage.py test modules.placement -v 2
"""
import datetime
import decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Year
from core.notifications.models import Notification
from core.users.models import Department, PriorAcademics, User
from modules.placement.models import (Application, Company, Drive, EligibilityRule, JobRole,
                                      Offer, PlacementEligibility, PlacementPolicy)

D = decimal.Decimal


class StoreTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mechanical")
        for n in (1, 2, 3, 4):
            Year.objects.create(course=self.course, year_number=n)
        self.officer = User.objects.create_user(username="officer", password="x", role="admin",
                                                sub_role="placement_officer")
        self.s1 = User.objects.create_user(username="s1", password="x", role="student", department=dept,
                                           course=self.course, year=4, semester=7, first_name="Aarthi")
        self.s2 = User.objects.create_user(username="s2", password="x", role="student", department=dept,
                                           course=self.course, year=4, semester=7, first_name="Bala")
        self.third = User.objects.create_user(username="t3", password="x", role="student", department=dept,
                                              course=self.course, year=3, semester=5)
        self.company = Company.objects.create(name="Acme Engineering", category="core")
        self.drive = Drive.objects.create(company=self.company, status="draft",
                                          drive_date=datetime.date.today() + datetime.timedelta(days=10))
        self.gte = JobRole.objects.create(drive=self.drive, title="Graduate engineer trainee", package_lpa=D("6"))
        self.design = JobRole.objects.create(drive=self.drive, title="Design engineer", package_lpa=D("4.5"))

    def row(self, student, role):
        return PlacementEligibility.objects.filter(student=student, job_role=role).first()

    def publish(self):
        self.client.force_authenticate(user=self.officer)
        return self.client.patch(f"/api/placement/drives/{self.drive.id}/", {"status": "published"}, format="json")

    def placed(self, student, package):
        other = Drive.objects.create(company=Company.objects.create(name=f"Zen {package}", category="service"),
                                     status="completed")
        r = JobRole.objects.create(drive=other, title="Earlier", package_lpa=D(str(package)))
        app = Application.objects.create(student=student, job_role=r, status="applied")
        return Offer.objects.create(application=app, package_lpa=D(str(package)), status="offered")


# ======================================================================
class PublishTests(StoreTestBase):

    def test_preview_counts_students_to_notify(self):
        self.client.force_authenticate(user=self.officer)
        r = self.client.get(f"/api/placement/drives/{self.drive.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["eligibility_summary"]["to_notify"], 2)     # s1, s2 - not the 3rd year

    def test_publish_fills_table_and_notifies_once_per_role(self):
        r = self.publish()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["notified"], 2)
        self.assertTrue(self.row(self.s1, self.gte).eligible)
        self.assertIsNone(self.row(self.third, self.gte))      # only final-years are stored
        notes = Notification.objects.filter(recipient=self.s1, notification_type="placement")
        self.assertEqual(notes.count(), 2)                                  # one per role
        self.assertIn("You're eligible for Acme Engineering", notes.first().title)
        self.assertFalse(Notification.objects.filter(recipient=self.third).exists())

    def test_republishing_never_duplicates(self):
        self.publish()
        self.client.patch(f"/api/placement/drives/{self.drive.id}/", {"status": "closed"}, format="json")
        r = self.publish()
        self.assertEqual(r.data["notified"], 0)
        self.assertEqual(Notification.objects.filter(recipient=self.s1).count(), 2)

    def test_placed_student_only_notified_for_higher_role(self):
        offer = self.placed(self.s1, 5)
        offer.status = "accepted"
        offer.save()
        self.publish()
        titles = list(Notification.objects.filter(recipient=self.s1).values_list("message", flat=True))
        self.assertEqual(len(titles), 1)
        self.assertIn("Graduate engineer trainee", titles[0])               # 6 LPA, not the 4.5 LPA role

    def test_other_edits_do_not_notify(self):
        self.client.force_authenticate(user=self.officer)
        self.client.patch(f"/api/placement/drives/{self.drive.id}/", {"title": "Campus drive"}, format="json")
        self.assertFalse(Notification.objects.exists())


# ======================================================================
class RefreshTriggerTests(StoreTestBase):
    """Each change refreshes the saved rows once the transaction commits."""

    def setUp(self):
        super().setUp()
        self.publish()                                   # table filled, everyone eligible

    def test_rule_edit_refreshes_role(self):
        with self.captureOnCommitCallbacks(execute=True):
            EligibilityRule.objects.create(job_role=self.gte, min_tenth_percent=D("60"))
        self.assertFalse(self.row(self.s1, self.gte).eligible)               # no 10th marks entered
        self.assertTrue(self.row(self.s1, self.design).eligible)             # other role untouched

    def test_marks_verified_refreshes_student(self):
        with self.captureOnCommitCallbacks(execute=True):
            EligibilityRule.objects.create(job_role=self.gte, min_tenth_percent=D("60"))
        with self.captureOnCommitCallbacks(execute=True):
            PriorAcademics.objects.create(student=self.s1, tenth_percent=D("80"),
                                          twelfth_percent=D("85"), verified=True)
        self.assertTrue(self.row(self.s1, self.gte).eligible)

    def test_offer_accepted_closes_lower_package_role(self):
        offer = self.placed(self.s1, 5)
        with self.captureOnCommitCallbacks(execute=True):
            offer.status = "accepted"
            offer.save()
        self.assertFalse(self.row(self.s1, self.design).eligible)            # 4.5 < 5
        self.assertTrue(self.row(self.s1, self.gte).eligible)                # 6 >= 5
        with self.captureOnCommitCallbacks(execute=True):
            offer.status = "declined"
            offer.save()
        self.assertTrue(self.row(self.s1, self.design).eligible)

    def test_policy_switch_refreshes_everything(self):
        with self.captureOnCommitCallbacks(execute=True):
            p = PlacementPolicy.current()
            p.final_year_only = False
            p.save()
        self.assertTrue(self.row(self.third, self.gte).eligible)

    def test_promotion_refreshes_student(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.third.year = 4
            self.third.semester = 7
            self.third.save()
        self.assertTrue(self.row(self.third, self.gte).eligible)

    def test_command_and_refresh_button(self):
        PlacementEligibility.objects.all().delete()
        out = StringIO()
        call_command("refresh_placement_eligibility", stdout=out)
        self.assertIn("refreshed", out.getvalue())
        self.assertEqual(PlacementEligibility.objects.filter(job_role=self.gte).count(), 2)   # final-years
        self.client.force_authenticate(user=self.officer)
        r = self.client.post("/api/placement/eligibility/refresh/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["students"], 2)

    def test_only_officer_can_refresh(self):
        self.client.force_authenticate(user=self.s1)
        self.assertEqual(self.client.post("/api/placement/eligibility/refresh/", {}, format="json").status_code, 403)


# ======================================================================
class ReadPathTests(StoreTestBase):

    def setUp(self):
        super().setUp()
        self.publish()

    def test_student_list_reads_saved_answer(self):
        PlacementEligibility.objects.filter(student=self.s1, job_role=self.gte).update(
            eligible=False, blockers=["saved-answer marker"])
        self.client.force_authenticate(user=self.s1)
        r = self.client.get("/api/placement/my-drives/")
        role = next(x for d in r.data["results"] for x in d["job_roles"] if x["id"] == self.gte.id)
        self.assertEqual(role["blockers"], ["saved-answer marker"])

    def test_stale_eligible_row_cannot_be_used_to_apply(self):
        """Safety: a wrong saved 'eligible' never lets a 3rd year apply."""
        PlacementEligibility.objects.filter(student=self.third, job_role=self.gte).update(eligible=True, blockers=[])
        self.client.force_authenticate(user=self.third)
        r = self.client.post(f"/api/placement/roles/{self.gte.id}/apply/", {"status": "applied"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Application.objects.filter(student=self.third, job_role=self.gte).exists())

    def test_missing_row_is_worked_out_and_saved(self):
        PlacementEligibility.objects.filter(student=self.s2).delete()
        self.client.force_authenticate(user=self.s2)
        r = self.client.get("/api/placement/my-drives/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.row(self.s2, self.gte).eligible)

    def test_officer_matches_read_table(self):
        self.client.force_authenticate(user=self.officer)
        r = self.client.get(f"/api/placement/roles/{self.gte.id}/matches/")
        self.assertEqual(r.data["eligible"], 2)
        self.assertEqual(r.data["not_eligible"], 0)          # 3rd years aren't in the officer's list


# ======================================================================
class FinalYearOnlyStorageTests(StoreTestBase):
    """With "final-year only" on, the table holds final-years only (speed)."""

    def test_third_year_sees_reason_live_and_nothing_is_stored(self):
        self.publish()
        self.client.force_authenticate(user=self.third)
        r = self.client.get("/api/placement/my-drives/")
        role = next(x for d in r.data["results"] for x in d["job_roles"] if x["id"] == self.gte.id)
        self.assertFalse(role["eligible"])
        self.assertIn("Placement is open to final-year students only.", role["blockers"])
        self.assertFalse(PlacementEligibility.objects.filter(student=self.third).exists())

    def test_switching_rule_back_on_removes_rows(self):
        self.publish()
        with self.captureOnCommitCallbacks(execute=True):
            p = PlacementPolicy.current()
            p.final_year_only = False
            p.save()
        self.assertTrue(self.row(self.third, self.gte).eligible)
        with self.captureOnCommitCallbacks(execute=True):
            p.final_year_only = True
            p.save()
        self.assertIsNone(self.row(self.third, self.gte))

    def test_login_does_not_refresh(self):
        from unittest import mock
        with mock.patch("modules.placement.eligibility_store.queue") as q:
            self.s1.save(update_fields=["last_login"])
        q.assert_not_called()



class NightlyRunnerTests(StoreTestBase):
    """Point 12's nightly runner includes the placement eligibility re-check."""

    def test_run_daily_jobs_refreshes_placement_eligibility(self):
        PlacementEligibility.objects.all().delete()
        out = StringIO()
        call_command("run_daily_jobs", "--only", "placement_eligibility", stdout=out, no_color=True)
        self.assertIn("re-checked 2 students x 2 roles", out.getvalue())     # final-years only
        self.assertTrue(self.row(self.s1, self.gte).eligible)
        self.assertIsNone(self.row(self.third, self.gte))

    def test_dry_run_changes_nothing(self):
        PlacementEligibility.objects.all().delete()
        out = StringIO()
        call_command("run_daily_jobs", "--dry-run", "--only", "placement_eligibility", stdout=out, no_color=True)
        self.assertIn("would re-check 2 students x 2 open roles", out.getvalue())
        self.assertFalse(PlacementEligibility.objects.exists())
