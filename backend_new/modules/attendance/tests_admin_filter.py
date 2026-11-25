"""An admin's GET /api/attendance/ list must have a filter (class or dates).

Teachers, students and parents are not affected, and neither is the
single-record view GET /api/attendance/<id>/.
"""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, ParentProfile, User
from modules.attendance.models import Attendance

DAY = datetime.date(2026, 11, 3)


class AdminListNeedsFilterTests(TestCase):

    def setUp(self):
        dept = Department.objects.create(name="ECE", code="EC")
        course = Course.objects.create(name="B.E ECE")
        year = Year.objects.create(course=course, year_number=1)
        subject = Subject.objects.create(name="Circuits", code="EC101", year=year, semester=1)
        self.admin = User.objects.create_user(username="af_admin", password="x", role="admin")
        self.teacher = User.objects.create_user(username="af_t", password="x", role="teacher",
                                                department=dept)
        self.student = User.objects.create_user(username="af_s", password="x", role="student",
                                                department=dept, course=course, year=1, semester=1)
        self.parent = User.objects.create_user(username="af_p", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=course,
                                                    year=year, subject=subject)
        self.row = Attendance.objects.create(teaching_assignment=self.ta, student=self.student,
                                             date=DAY, hour=1, status="present")
        self.client = APIClient()

    def get(self, user, url):
        self.client.force_authenticate(user=user)
        return self.client.get(url)

    def test_admin_without_filter_gets_a_clear_400(self):
        r = self.get(self.admin, "/api/attendance/")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "Please choose a class or a date range.")

    def test_admin_with_any_one_filter_works(self):
        for q in (f"teaching_assignment={self.ta.id}", f"date={DAY}",
                  f"from_date={DAY}", f"to_date={DAY}"):
            r = self.get(self.admin, f"/api/attendance/?{q}")
            self.assertEqual(r.status_code, 200, q)
            self.assertEqual(len(r.json()), 1, q)

    def test_empty_filter_value_does_not_count(self):
        self.assertEqual(self.get(self.admin, "/api/attendance/?from_date=").status_code, 400)

    def test_teacher_student_parent_unchanged_without_filter(self):
        for user in (self.teacher, self.student, self.parent):
            r = self.get(user, "/api/attendance/")
            self.assertEqual(r.status_code, 200, user.role)
            self.assertEqual(len(r.json()), 1, user.role)

    def test_single_record_still_opens_for_admin(self):
        r = self.get(self.admin, f"/api/attendance/{self.row.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "present")