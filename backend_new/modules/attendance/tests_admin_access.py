"""Lead's decision (20-11-2026): only the main admin (no sub-role), super admin
and academic admin may read attendance through GET /api/attendance/.
Other admin types (exam, accounts, IQAC, placement officer) get 403 on the
list and 404 on a single record. Teachers, students, parents unchanged.
"""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.attendance.models import Attendance

DAY = datetime.date(2026, 11, 4)
URL = f"/api/attendance/?date={DAY}"


class AdminAttendanceAccessTests(TestCase):

    def setUp(self):
        dept = Department.objects.create(name="IT", code="IT")
        course = Course.objects.create(name="B.Tech IT")
        year = Year.objects.create(course=course, year_number=1)
        subject = Subject.objects.create(name="Networks", code="IT101", year=year, semester=1)
        self.teacher = User.objects.create_user(username="aa_t", password="x", role="teacher",
                                                department=dept)
        student = User.objects.create_user(username="aa_s", password="x", role="student",
                                           department=dept, course=course, year=1, semester=1)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=course, year=year,
                                               subject=subject)
        self.row = Attendance.objects.create(teaching_assignment=ta, student=student,
                                             date=DAY, hour=1, status="present")
        self.client = APIClient()

    def admin(self, sub_role):
        return User.objects.create_user(username=f"aa_{sub_role or 'main'}", password="x",
                                        role="admin", sub_role=sub_role)

    def get(self, user, url):
        self.client.force_authenticate(user=user)
        return self.client.get(url)

    def test_main_super_and_academic_admin_can_view(self):
        for sub in ("", "super_admin", "academic_admin"):
            u = self.admin(sub)
            r = self.get(u, URL)
            self.assertEqual(r.status_code, 200, sub)
            self.assertEqual(len(r.json()), 1, sub)
            self.assertEqual(self.get(u, f"/api/attendance/{self.row.id}/").status_code, 200, sub)

    def test_other_admin_types_are_refused(self):
        for sub in ("exam_admin", "accounts_admin", "iqac_admin", "placement_officer"):
            u = self.admin(sub)
            r = self.get(u, URL)
            self.assertEqual(r.status_code, 403, sub)
            self.assertEqual(r.json()["error"],
                             "Only the academic admin or super admin can view attendance.")
            self.assertEqual(self.get(u, f"/api/attendance/{self.row.id}/").status_code, 404, sub)

    def test_teacher_unchanged(self):
        self.assertEqual(len(self.get(self.teacher, "/api/attendance/").json()), 1)