"""N+1 fix: GET /api/attendance/ must not run extra queries for every row.

Before: each row loaded its subject, course and year separately
(3 queries per row: 90 rows = 271 queries).
After:  a fixed number of queries, however many rows there are.
"""
import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.attendance.models import Attendance


class AttendanceListQueryTests(TestCase):

    def setUp(self):
        dept = Department.objects.create(name="Mechanical", code="ME")
        course = Course.objects.create(name="B.E Mechanical")
        year = Year.objects.create(course=course, year_number=1)
        self.admin = User.objects.create_user(username="nq_admin", password="x", role="admin")
        self.teacher = User.objects.create_user(username="nq_t", password="x", role="teacher",
                                                department=dept)
        self.tas = []
        for i in range(3):
            subject = Subject.objects.create(name=f"Subject {i}", code=f"NQ{i}", year=year, semester=1)
            self.tas.append(TeachingAssignment.objects.create(
                teacher=self.teacher, course=course, year=year, subject=subject))
        self.students = [
            User.objects.create_user(username=f"nq_s{i}", password="x", role="student",
                                     department=dept, course=course, year=1, semester=1,
                                     roll_number=f"R{i:03d}")
            for i in range(10)
        ]
        self.day = datetime.date(2026, 11, 2)
        self.client = APIClient()

    def add_rows(self, days, start=0):
        rows = []
        for d in range(start, start + days):
            for ta in self.tas:
                for s in self.students:
                    rows.append(Attendance(teaching_assignment=ta, student=s, status="present",
                                           date=self.day + datetime.timedelta(days=d), hour=1))
        Attendance.objects.bulk_create(rows)

    def count_queries(self, user):
        self.client.force_authenticate(user=user)
        # an admin's list needs a filter (class or dates) - see views.py
        url = "/api/attendance/?from_date=2026-11-01&to_date=2026-11-30"
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        return len(ctx.captured_queries), r.json()

    def test_query_count_does_not_grow_with_rows(self):
        self.add_rows(days=1)                          # 30 rows
        small, data_small = self.count_queries(self.admin)
        self.add_rows(days=2, start=1)                 # +60 rows = 90
        big, data_big = self.count_queries(self.admin)
        self.assertEqual((len(data_small), len(data_big)), (30, 90))
        self.assertEqual(small, big, f"30 rows: {small} queries, 90 rows: {big} queries")
        self.assertLessEqual(big, 5)

    def test_teacher_view_is_also_constant(self):
        self.add_rows(days=3)
        n, data = self.count_queries(self.teacher)
        self.assertEqual(len(data), 90)
        self.assertLessEqual(n, 5)

    def test_row_still_has_all_the_same_fields(self):
        self.add_rows(days=1)
        _, data = self.count_queries(self.admin)
        row = next(r for r in data if r["student_roll_no"] == "R000" and r["subject_name"] == "Subject 0")
        self.assertEqual(
            (row["student_name"], row["course_name"], row["year_number"], row["semester"],
             row["status"], row["date"], row["hour"]),
            ("nq_s0", "B.E Mechanical", 1, 1, "present", "2026-11-02", 1))