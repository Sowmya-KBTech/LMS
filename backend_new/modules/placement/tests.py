"""
Placement eligibility - the college rules agreed for KB Tech Campus:

  1. Only FINAL-YEAR students take part (Year 4 of a 4-year course,
     Year 2 of a 2-year course - worked out from the course).
  2. A student with an ACCEPTED offer may apply only to roles paying the
     SAME OR MORE. Any increase is enough. Offers not yet accepted don't
     count as placed.
  3. Company rules are optional per role: CGPA only, arrears only, both,
     or nothing ("everyone can apply"). 10th/12th marks are needed - and
     must be verified - only when the role sets a 10th/12th limit.
  4. Both college rules can be switched off in the placement policy.

Also: resume upload has been removed.

Run:  python manage.py test modules.placement -v 2
"""
import datetime
import decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Year
from core.users.models import Department, PriorAcademics, User
from modules.placement.eligibility import check_eligibility
from modules.placement.models import (Application, Company, Drive, EligibilityRule, JobRole,
                                      Offer, PlacementPolicy)

D = decimal.Decimal


class EligibilityTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mechanical")
        for n in (1, 2, 3, 4):
            Year.objects.create(course=self.course, year_number=n)
        self.mba = Course.objects.create(name="MBA")
        for n in (1, 2):
            Year.objects.create(course=self.mba, year_number=n)

        self.final = self.student("final1", year=4, semester=7)
        self.third = self.student("third1", year=3, semester=5)

        self.company = Company.objects.create(name="Acme", category="core")
        self.drive = Drive.objects.create(company=self.company, status="published",
                                          drive_date=datetime.date.today() + datetime.timedelta(days=7))

    # ---------- helpers ----------
    def student(self, username, year, semester, course=None):
        return User.objects.create_user(username=username, password="x", role="student",
                                        department=self.dept, course=course or self.course,
                                        year=year, semester=semester)

    def role(self, package, **rule):
        self._n = getattr(self, "_n", 0) + 1
        r = JobRole.objects.create(drive=self.drive, title=f"Role {self._n} ({package})",
                                   package_lpa=None if package is None else D(str(package)))
        if rule:
            EligibilityRule.objects.create(job_role=r, **rule)
        return JobRole.objects.get(pk=r.pk)       # fresh, so .eligibility is loaded

    def accepted_offer(self, student, package, status="accepted"):
        other = Drive.objects.create(company=Company.objects.create(name=f"Co{package}{status}", category="service"),
                                     status="completed")
        r = JobRole.objects.create(drive=other, title="Earlier", package_lpa=D(str(package)))
        app = Application.objects.create(student=student, job_role=r, status="applied")
        return Offer.objects.create(application=app, package_lpa=D(str(package)), status=status)

    def check(self, student, role):
        return check_eligibility(User.objects.get(pk=student.pk), role)

    def failed(self, result):
        return [c["criterion"] for c in result["checks"] if not c["passed"]]


# ======================================================================
class FinalYearRuleTests(EligibilityTestBase):

    def test_final_year_can_apply_to_open_role(self):
        res = self.check(self.final, self.role(5))
        self.assertTrue(res["eligible"], res)

    def test_third_year_blocked(self):
        res = self.check(self.third, self.role(5))
        self.assertFalse(res["eligible"])
        self.assertIn("Placement is open to final-year students only.", res["blockers"])

    def test_two_year_course_final_year_is_year_2(self):
        mba2 = self.student("mba2", year=2, semester=3, course=self.mba)
        mba1 = self.student("mba1", year=1, semester=1, course=self.mba)
        self.assertTrue(self.check(mba2, self.role(5))["eligible"])
        self.assertFalse(self.check(mba1, self.role(5))["eligible"])

    def test_missing_course_explained(self):
        nocourse = User.objects.create_user(username="nc", password="x", role="student", department=self.dept)
        res = self.check(nocourse, self.role(5))
        self.assertFalse(res["eligible"])
        self.assertIn("contact the office", " ".join(res["blockers"]))

    def test_switch_off_lets_any_year_apply(self):
        p = PlacementPolicy.current()
        p.final_year_only = False
        p.save()
        self.assertTrue(self.check(self.third, self.role(5))["eligible"])


# ======================================================================
class HigherPackageRuleTests(EligibilityTestBase):

    def setUp(self):
        super().setUp()
        self.accepted_offer(self.final, 5)

    def test_lower_package_blocked(self):
        res = self.check(self.final, self.role("4.5"))
        self.assertFalse(res["eligible"])
        self.assertEqual(self.failed(res), ["Current offer"])
        self.assertIn("Only roles paying 5.00 LPA or more", " ".join(res["blockers"]))

    def test_same_package_allowed(self):
        self.assertTrue(self.check(self.final, self.role(5))["eligible"])

    def test_any_increase_allowed(self):
        self.assertTrue(self.check(self.final, self.role("5.1"))["eligible"])
        self.assertTrue(self.check(self.final, self.role(12))["eligible"])

    def test_role_without_package_blocked_for_placed_student(self):
        res = self.check(self.final, self.role(None))
        self.assertFalse(res["eligible"])
        self.assertIn("no package listed", " ".join(res["blockers"]))

    def test_best_accepted_offer_is_used(self):
        self.accepted_offer(self.final, 8)          # now holds 5 and 8
        self.assertFalse(self.check(self.final, self.role(6))["eligible"])
        self.assertTrue(self.check(self.final, self.role(8))["eligible"])

    def test_offer_not_accepted_is_not_placed(self):
        other = self.student("final2", year=4, semester=7)
        self.accepted_offer(other, 10, status="offered")     # not accepted yet
        self.assertTrue(self.check(other, self.role(4))["eligible"])
        declined = self.student("final3", year=4, semester=7)
        self.accepted_offer(declined, 10, status="declined")
        self.assertTrue(self.check(declined, self.role(4))["eligible"])

    def test_unplaced_student_any_package(self):
        other = self.student("final4", year=4, semester=7)
        self.assertTrue(self.check(other, self.role(3))["eligible"])

    def test_switch_off_allows_lower_package(self):
        p = PlacementPolicy.current()
        p.higher_package_only = False
        p.save()
        self.assertTrue(self.check(self.final, self.role(3))["eligible"])

    def test_apply_endpoint_refuses_lower_package(self):
        low = self.role(3)
        self.client.force_authenticate(user=self.final)
        r = self.client.post(f"/api/placement/roles/{low.id}/apply/", {"status": "applied"}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(Application.objects.filter(student=self.final, job_role=low).exists())
        ok = self.role(6)
        r = self.client.post(f"/api/placement/roles/{ok.id}/apply/", {"status": "applied"}, format="json")
        self.assertIn(r.status_code, (200, 201), r.data)


# ======================================================================
class CompanyRuleTests(EligibilityTestBase):
    """CGPA only / arrears only / nothing - without needing verified 10th/12th."""

    def test_no_rule_no_marks_entered_still_eligible(self):
        self.assertFalse(PriorAcademics.objects.filter(student=self.final).exists())
        self.assertTrue(self.check(self.final, self.role(5))["eligible"])

    def test_arrears_only_rule_needs_no_marksheet(self):
        res = self.check(self.final, self.role(5, max_arrears=0))
        self.assertTrue(res["eligible"], res)

    def test_unverified_marks_dont_block_open_role(self):
        PriorAcademics.objects.create(student=self.final, tenth_percent=D("80"), twelfth_percent=D("85"),
                                      verified=False)
        self.assertTrue(self.check(self.final, self.role(5))["eligible"])

    def test_cgpa_rule_without_results_is_explained(self):
        res = self.check(self.final, self.role(5, min_cgpa=D("7.0")))
        self.assertFalse(res["eligible"])
        self.assertEqual(self.failed(res), ["CGPA"])          # not blocked by 10th/12th

    def test_tenth_limit_requires_verified_marks(self):
        r = self.role(5, min_tenth_percent=D("60"))
        self.assertIn("not entered your 10th / 12th", " ".join(self.check(self.final, r)["blockers"]))
        PriorAcademics.objects.create(student=self.final, tenth_percent=D("80"), twelfth_percent=D("85"))
        self.assertIn("Verification", self.failed(self.check(self.final, r)))
        PriorAcademics.objects.filter(student=self.final).update(verified=True)
        self.assertTrue(self.check(self.final, r)["eligible"])

    def test_no_lateral_entry_rule_reads_entry_type(self):
        PriorAcademics.objects.create(student=self.final, tenth_percent=D("80"), is_lateral_entry=True,
                                      diploma_percent=D("75"), verified=True)
        res = self.check(self.final, self.role(5, allow_lateral_entry=False))
        self.assertFalse(res["eligible"])
        self.assertIn("lateral entry", " ".join(res["blockers"]))


# ======================================================================
class PolicyApiTests(EligibilityTestBase):

    def test_officer_switches_rules(self):
        officer = User.objects.create_user(username="officer", password="x", role="admin",
                                           sub_role="placement_officer")
        self.client.force_authenticate(user=officer)
        r = self.client.get("/api/placement/policy/")
        self.assertTrue(r.data["final_year_only"])
        self.assertTrue(r.data["higher_package_only"])
        r = self.client.put("/api/placement/policy/", {"tiers_enabled": False, "final_year_only": False},
                            format="json")
        self.assertEqual(r.status_code, 200, r.data)
        p = PlacementPolicy.current()
        self.assertFalse(p.final_year_only)
        self.assertTrue(p.higher_package_only)                # not sent -> unchanged

    def test_student_cannot_change_policy(self):
        self.client.force_authenticate(user=self.final)
        r = self.client.put("/api/placement/policy/", {"final_year_only": False}, format="json")
        self.assertEqual(r.status_code, 403)


class ResumeRemovedTests(EligibilityTestBase):

    def test_resume_endpoints_gone(self):
        self.client.force_authenticate(user=self.final)
        self.assertEqual(self.client.get("/api/placement/my-resume/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/placement/students/{self.final.id}/resume/").status_code, 404)
