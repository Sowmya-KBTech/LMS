"""
Probe tests: does a class group get created automatically when a student is
assigned to a year and a class advisor is assigned?

Run: python manage.py test classgroups.tests_probe --settings=test_settings
"""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from classgroups.models import ClassGroup
from classgroups.views import my_groups
from courses.models import (Course, Enrollment, Subject, TeachingAssignment,
                            Year, YearTutor)
from users.models import User

factory = APIRequestFactory()


def get_groups(user):
    req = factory.get("/api/class-groups/")
    force_authenticate(req, user=user)
    return my_groups(req).data


class ClassGroupAutoCreation(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="B.E CSE")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.subject = Subject.objects.create(
            name="Data Structures", code="CS201", year=self.y2, semester=3
        )
        self.advisor = User.objects.create_user(
            username="advisor1", password="x", role="teacher",
            first_name="Advisor", last_name="One",
        )
        self.subject_teacher = User.objects.create_user(
            username="teacher1", password="x", role="teacher",
            first_name="Subject", last_name="Teacher",
        )

    # ---------- 1. assigning student + advisor creates nothing ----------
    def test_no_row_created_by_assignment(self):
        student = User.objects.create_user(
            username="s1", password="x", role="student",
            course=self.course, year=2, semester=3,
        )
        YearTutor.objects.create(
            teacher=self.advisor, course=self.course, year=self.y2
        )
        print("\n[1] After assigning a student AND a class advisor:")
        print("    ClassGroup rows in DB:", ClassGroup.objects.count())
        self.assertEqual(ClassGroup.objects.count(), 0)
        self.assertIsNotNone(student.id)

    # ---------- 2. the row appears when someone opens the page ----------
    def test_row_created_on_first_open(self):
        User.objects.create_user(
            username="s1", password="x", role="student",
            course=self.course, year=2, semester=3,
        )
        YearTutor.objects.create(
            teacher=self.advisor, course=self.course, year=self.y2
        )
        data = get_groups(self.advisor)
        print("[2] Advisor opens /api/class-groups/:")
        print("    ClassGroup rows now:", ClassGroup.objects.count())
        for g in data["class_groups"]:
            print("    card:", g["name"], "| students:", g["student_count"],
                  "| has_audience:", g["has_audience"], "| my_role:", g["my_role"])
        self.assertEqual(ClassGroup.objects.count(), 1)
        self.assertEqual(data["class_groups"][0]["student_count"], 1)

    # ---------- 3. student sees the class group with NO advisor ----------
    def test_student_sees_group_without_advisor(self):
        student = User.objects.create_user(
            username="s1", password="x", role="student",
            course=self.course, year=2, semester=3,
        )
        data = get_groups(student)
        print("[3] No YearTutor exists, student opens the page:")
        print("    class_groups returned:", len(data["class_groups"]), "(AFTER FIX: expect 0)")
        self.assertEqual(len(data["class_groups"]), 0)

    # ---------- 4. teacher sees NO class group without YearTutor ----------
    def test_teacher_sees_nothing_without_yeartutor(self):
        User.objects.create_user(
            username="s1", password="x", role="student",
            course=self.course, year=2, semester=3,
        )
        data = get_groups(self.advisor)
        print("[4] No YearTutor, advisor opens the page:")
        print("    class_groups returned:", len(data["class_groups"]))
        self.assertEqual(len(data["class_groups"]), 0)

    # ---------- 5. NEW student -> auto-enrolled -> subject group has audience ----------
    def test_new_student_autoenrolled_via_serializer(self):
        from users.serializers import UserSerializer
        TeachingAssignment.objects.create(
            teacher=self.subject_teacher, course=self.course,
            year=self.y2, subject=self.subject,
        )
        ser = UserSerializer(data={
            "username": "s_new", "password": "Passw0rd!", "role": "student", "email": "s_new@example.com",
            "course": self.course.id, "year": 2, "semester": 3,
            "first_name": "New", "last_name": "Student",
        })
        ser.is_valid(raise_exception=True)
        new_student = ser.save()
        data = get_groups(self.subject_teacher)
        card = data["subject_groups"][0]
        print("[5] Student CREATED through UserSerializer:")
        print("    Enrollment rows:", Enrollment.objects.filter(student=new_student).count())
        print("    subject card:", card["name"], "| students:", card["student_count"],
              "| has_audience:", card["has_audience"])
        self.assertEqual(Enrollment.objects.filter(student=new_student).count(), 1)

    # ---------- 6. MOVED student -> no enrolment -> no audience ----------
    def test_moved_student_not_enrolled(self):
        from users.serializers import UserSerializer
        y3 = Year.objects.create(course=self.course, year_number=3)
        sub3 = Subject.objects.create(
            name="Operating Systems", code="CS301", year=y3, semester=5
        )
        ta3 = TeachingAssignment.objects.create(
            teacher=self.subject_teacher, course=self.course,
            year=y3, subject=sub3,
        )
        YearTutor.objects.create(teacher=self.advisor, course=self.course, year=y3)

        existing = User.objects.create_user(
            username="s_old", password="x", role="student",
            course=self.course, year=2, semester=3,
        )
        # HOD/admin edits the student: moves them into III year, semester 5
        ser = UserSerializer(existing, data={"year": 3, "semester": 5}, partial=True)
        ser.is_valid(raise_exception=True)
        moved = ser.save()

        data = get_groups(self.advisor)
        class_card = data["class_groups"][0]
        teacher_data = get_groups(self.subject_teacher)
        subj_card = [c for c in teacher_data["subject_groups"]
                     if c["subject_name"] == "Operating Systems"][0]

        print("[6] EXISTING student MOVED to III year via UserSerializer.update:")
        print("    Enrollment rows for this student:",
              Enrollment.objects.filter(student=moved).count())
        print("    class group :", class_card["name"],
              "| students:", class_card["student_count"],
              "| has_audience:", class_card["has_audience"])
        print("    subject group:", subj_card["name"],
              "| students:", subj_card["student_count"],
              "| has_audience:", subj_card["has_audience"],
              "| can_post(owner):", subj_card["can_post"])
        self.assertEqual(class_card["student_count"], 1)      # class group: fine
        self.assertEqual(Enrollment.objects.filter(student=moved, teaching_assignment=ta3).count(), 1)
        self.assertTrue(subj_card["has_audience"])            # AFTER FIX: has audience