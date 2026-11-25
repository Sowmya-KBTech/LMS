"""
Staff records -> Teaching tab: the classes a teacher has now.

Run:  python manage.py test core.users.tests_staff_teaching -v 2
"""
from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User


class StaffTeachingTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.cse = Department.objects.create(name="CSE", code="CSE")
        self.maths = Department.objects.create(name="Maths", code="MATH")
        self.hod = mk("anitha", password="x", role="teacher", department=self.cse)
        self.cse.hod = self.hod
        self.cse.save()
        self.arun = mk("arun", password="x", role="teacher", department=self.cse)
        self.idle = mk("karthik", password="x", role="teacher", department=self.cse)
        self.other = mk("lakshmi", password="x", role="teacher", department=self.maths)
        self.clerk = mk("ravi", password="x", role="non_teaching", department=self.cse)

        self.course = Course.objects.create(name="B.E Computer Science")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.y3 = Year.objects.create(course=self.course, year_number=3)
        self.cloud = Subject.objects.create(name="Cloud Computing", code="CCS335", year=self.y3,
                                            semester=5, is_elective=True, department=self.cse)
        self.dbms = Subject.objects.create(name="Database Management", code="CS3492", year=self.y2,
                                           semester=3, department=self.cse)
        self.ta_cloud = TeachingAssignment.objects.create(teacher=self.arun, course=self.course,
                                                          year=self.y3, subject=self.cloud)
        self.ta_dbms = TeachingAssignment.objects.create(teacher=self.arun, course=self.course,
                                                         year=self.y2, subject=self.dbms)
        for i in range(3):
            s = mk(f"s3_{i}", password="x", role="student", course=self.course, year=3, semester=5)
            if i < 2:
                Enrollment.objects.create(student=s, teaching_assignment=self.ta_cloud)
        for i in range(4):
            s = mk(f"s2_{i}", password="x", role="student", course=self.course, year=2, semester=3)
            Enrollment.objects.create(student=s, teaching_assignment=self.ta_dbms)

    def get(self, user, staff):
        c = APIClient()
        c.force_authenticate(user=user)
        return c.get(f"/api/users/hris/staff/{staff.id}/")

    def test_teacher_record_lists_classes_with_students(self):
        r = self.get(self.admin, self.arun)
        self.assertEqual(r.status_code, 200, r.content)
        t = r.json()["teaching"]
        self.assertEqual((t["classes"], t["subjects"], t["students"]), (2, 2, 6))
        rows = {x["subject_code"]: x for x in t["rows"]}
        self.assertEqual(rows["CCS335"]["type"], "elective")
        self.assertEqual(rows["CCS335"]["students"], 2)          # only those who chose it
        self.assertEqual((rows["CCS335"]["year"], rows["CCS335"]["semester"]), (3, 5))
        self.assertEqual(rows["CS3492"]["type"], "core")
        self.assertEqual(rows["CS3492"]["students"], 4)
        self.assertEqual(rows["CS3492"]["course"], "B.E Computer Science")
        self.assertEqual([x["year"] for x in t["rows"]], [2, 3])  # sorted by year

    def test_teacher_without_classes_gets_empty_list(self):
        t = self.get(self.admin, self.idle).json()["teaching"]
        self.assertEqual((t["classes"], t["students"], t["rows"]), (0, 0, []))
        self.assertIsNone(t["hours"])

    def test_non_teaching_staff_has_no_teaching_block(self):
        self.assertIsNone(self.get(self.admin, self.clerk).json()["teaching"])

    def test_hod_sees_own_department_teacher(self):
        r = self.get(self.hod, self.arun)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["teaching"]["classes"], 2)

    def test_hod_cannot_see_other_department(self):
        self.assertEqual(self.get(self.hod, self.other).status_code, 403)

    def test_teacher_sees_own_teaching(self):
        r = self.get(self.arun, self.arun)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["teaching"]["classes"], 2)
