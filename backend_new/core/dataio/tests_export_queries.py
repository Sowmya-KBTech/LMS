"""N+1 fix: the student and staff Excel exports must not run a query per row.

Before: every row loaded its profile (gender, address, ...) separately,
so 100 students = 100 extra queries.
After:  a fixed number of queries, however many people are exported.
"""
import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.academics.models import Course
from core.dataio import registry
from core.users.models import (Department, FacultyProfile, ParentProfile, StudentProfile,
                               User)


def export_all(key):
    """Run an export exactly like the export view does; return (queries, rows)."""
    imp = registry.get(key)
    with CaptureQueriesContext(connection) as ctx:
        rows = [imp.export_row(obj) for obj in imp.export_queryset(None, {}, {})]
    return len(ctx.captured_queries), rows


class ExportQueryTests(TestCase):

    def setUp(self):
        self.dept = Department.objects.create(name="Civil", code="CE")
        self.course = Course.objects.create(name="B.E Civil")
        self.n = 0

    def add_students(self, count):
        for _ in range(count):
            self.n += 1
            s = User.objects.create_user(username=f"ex_s{self.n}", password="x", role="student",
                                         department=self.dept, course=self.course, year=1,
                                         semester=1, roll_number=f"CE{self.n:03d}")
            StudentProfile.objects.create(user=s, gender="F", city="Vellore",
                                          date_of_birth=datetime.date(2006, 1, 2))
            parent = User.objects.create_user(username=f"ex_p{self.n}", password="x", role="parent",
                                              first_name=f"Parent {self.n}")
            ParentProfile.objects.create(user=parent, phone="9000000000",
                                         relation="Mother").children.add(s)

    def add_staff(self, count):
        for _ in range(count):
            self.n += 1
            t = User.objects.create_user(username=f"ex_t{self.n}", password="x", role="teacher",
                                         department=self.dept, employee_id=f"E{self.n:03d}")
            FacultyProfile.objects.create(user=t, gender="M", qualification="M.E.")

    def test_student_export_query_count_does_not_grow(self):
        self.add_students(5)
        small, rows_small = export_all("students")
        self.add_students(20)
        big, rows_big = export_all("students")
        self.assertEqual((len(rows_small), len(rows_big)), (5, 25))
        self.assertEqual(small, big, f"5 students: {small} queries, 25 students: {big} queries")

    def test_student_export_values_unchanged(self):
        self.add_students(1)
        _, rows = export_all("students")
        r = rows[0]
        self.assertEqual(
            (r["roll_number"], r["department"], r["course"], r["gender"], r["city"],
             r["parent_name"], r["parent_phone"], r["parent_relation"]),
            ("CE001", "Civil", "B.E Civil", "F", "Vellore", "Parent 1", "9000000000", "Mother"))
        self.assertTrue(r["date_of_birth"])

    def test_student_without_profile_still_exports(self):
        User.objects.create_user(username="ex_bare", password="x", role="student")
        _, rows = export_all("students")
        self.assertEqual((rows[0]["username"], rows[0]["gender"], rows[0]["parent_name"]),
                         ("ex_bare", "", ""))

    def test_staff_export_query_count_does_not_grow(self):
        self.add_staff(5)
        small, rows_small = export_all("staff")
        self.add_staff(20)
        big, rows_big = export_all("staff")
        self.assertEqual((len(rows_small), len(rows_big)), (5, 25))
        self.assertEqual(small, big, f"5 staff: {small} queries, 25 staff: {big} queries")