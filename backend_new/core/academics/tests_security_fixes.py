"""
The three small security fixes (before the next demo):

  1. Teaching assignments: anyone logged in could create / edit / delete
     who teaches what. Now only the academic admin can; reading stays open.
  2. On duty: the attendance register trusted the screen. Now the SERVER
     decides - an approved OD is always On duty, and nobody else can be.
  3. #49 exams: every admin sub-role passed is_exam_admin(). Now only the
     superuser, main admin, super admin and Examination admin do.

Run:  python manage.py test core.academics.tests_security_fixes -v 2
"""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User


class Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mechanical")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.subject = Subject.objects.create(name="Thermodynamics", code="ME301", year=self.y2, semester=3)
        self.main_admin = User.objects.create_user(username="admin", password="x", role="admin")
        self.academic = User.objects.create_user(username="acad", password="x", role="admin",
                                                 sub_role="academic_admin")
        self.exam_admin = User.objects.create_user(username="exam", password="x", role="admin",
                                                   sub_role="exam_admin")
        self.placement = User.objects.create_user(username="po", password="x", role="admin",
                                                  sub_role="placement_officer")
        self.teacher = User.objects.create_user(username="priya", password="x", role="teacher",
                                                department=self.dept)
        self.student = User.objects.create_user(username="s1", password="x", role="student",
                                                department=self.dept, course=self.course, year=2, semester=3)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                    year=self.y2, subject=self.subject)
        Enrollment.objects.create(student=self.student, teaching_assignment=self.ta)

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client


# ======================================================================
class TeachingAssignmentPermissionTests(Base):
    def payload(self):
        self._n = getattr(self, "_n", 0) + 1
        sub = Subject.objects.create(name=f"Elective {self._n}", code=f"ME39{self._n}", year=self.y2, semester=3)
        return {"teacher": self.teacher.id, "course": self.course.id, "year": self.y2.id, "subject": sub.id}

    def test_teacher_and_student_cannot_change(self):
        for user in (self.teacher, self.student, self.placement):
            c = self.as_(user)
            self.assertEqual(c.post("/api/teaching-assignments/", self.payload(), format="json").status_code, 403,
                             user.username)
            self.assertEqual(c.delete(f"/api/teaching-assignments/{self.ta.id}/").status_code, 403, user.username)
            self.assertEqual(c.patch(f"/api/teaching-assignments/{self.ta.id}/", {"teacher": self.teacher.id},
                                     format="json").status_code, 403, user.username)
        self.assertTrue(TeachingAssignment.objects.filter(pk=self.ta.pk).exists())

    def test_reading_still_works_for_everyone(self):
        for user in (self.teacher, self.student):
            r = self.as_(user).get(f"/api/teaching-assignments/{self.ta.id}/")
            self.assertEqual(r.status_code, 200, user.username)

    def test_main_and_academic_admin_can_change(self):
        for user in (self.main_admin, self.academic):
            r = self.as_(user).post("/api/teaching-assignments/", self.payload(), format="json")
            self.assertEqual(r.status_code, 201, (user.username, r.data))


# ======================================================================
class OnDutyRuleTests(Base):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.other = User.objects.create_user(username="s2", password="x", role="student", department=self.dept,
                                              course=self.course, year=2, semester=3)
        Enrollment.objects.create(student=self.other, teaching_assignment=self.ta)

    def mark(self, records):
        return self.as_(self.teacher).post("/api/attendance/bulk_mark/", {
            "teaching_assignment": self.ta.id, "date": str(self.today), "hour": 1, "records": records,
        }, format="json")

    def status_of(self, student):
        from modules.attendance.models import Attendance
        return Attendance.objects.get(student=student, date=self.today, hour=1).status

    def approve_od(self, student):
        from modules.attendance.models import ODRequest
        od = ODRequest.objects.create(student=student, from_date=self.today, to_date=self.today,
                                      reason="Symposium at PSG")
        ODRequest.objects.filter(pk=od.pk).update(status=ODRequest.Status.APPROVED)

    def test_approved_od_is_on_duty_even_if_screen_says_absent(self):
        self.approve_od(self.student)
        r = self.mark([{"student": self.student.id, "status": "absent"},
                       {"student": self.other.id, "status": "present"}])
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status_of(self.student), "duty_leave")
        self.assertEqual(self.status_of(self.other), "present")

    def test_on_duty_without_approval_refused(self):
        r = self.mark([{"student": self.other.id, "status": "duty_leave"}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("no approved on-duty request", r.data["error"])

    def test_unknown_status_refused(self):
        r = self.mark([{"student": self.other.id, "status": "holiday"}])
        self.assertEqual(r.status_code, 400)


# ======================================================================
class ExamAdminTests(Base):
    """#49: only the main / super / Examination admin manage exams."""

    def test_rule(self):
        from modules.exams.views import is_exam_admin
        self.assertTrue(is_exam_admin(self.main_admin))
        self.assertTrue(is_exam_admin(self.exam_admin))
        self.assertTrue(is_exam_admin(User.objects.create_user(username="sa", password="x", role="admin",
                                                               sub_role="super_admin")))
        for u in (self.placement, self.academic, self.teacher, self.student):
            self.assertFalse(is_exam_admin(u), u.username)

    def test_placement_officer_cannot_publish_results_or_schedule_exams(self):
        from modules.exams.models import SemesterResult
        res = SemesterResult.objects.create(student=self.student, semester=3)
        c = self.as_(self.placement)
        self.assertEqual(c.post(f"/api/semester-results/{res.id}/publish/").status_code, 403)
        res.refresh_from_db()
        self.assertFalse(res.is_published)
        r = c.post("/api/exam-schedules/", {"subject": self.subject.id, "semester": 3,
                                            "exam_date": str(timezone.localdate() + datetime.timedelta(days=30)),
                                            "session": "FN"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_exam_admin_can_publish(self):
        from modules.exams.models import SemesterResult
        res = SemesterResult.objects.create(student=self.student, semester=3)
        r = self.as_(self.exam_admin).post(f"/api/semester-results/{res.id}/publish/")
        self.assertEqual(r.status_code, 200, getattr(r, "data", r))
        res.refresh_from_db()
        self.assertTrue(res.is_published)

    def test_imports_follow_the_same_rule(self):
        c = self.as_(self.placement)
        for key in ("results", "exam_schedule"):
            self.assertEqual(c.get(f"/api/dataio/{key}/template/").status_code, 403, key)