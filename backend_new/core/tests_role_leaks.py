"""
PHASE 5, PART 1 TESTS - role leaks inside ONE college.

Each test is a real attack a student, parent or teacher could make by calling
the API directly (the menu hiding a button is not protection), followed by a
check that the people who SHOULD be able to do it still can.

Run:  python manage.py test core.tests_role_leaks -v 2
"""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.notifications.models import Notification
from core.users.models import Department, ParentProfile, User
from modules.exams.models import IAMark, InternalAssessment, ResultEntry, SemesterResult
from modules.fees.models import Fee
from modules.learning.models import DiscussionMessage, Feedback, Question, Quiz, StudyMaterial
from modules.teachingplan.models import TeachingPlan

TODAY = datetime.date(2026, 12, 1)
FORBIDDEN = (403, 404)          # refused, or "doesn't exist for you"


class RoleTestBase(TestCase):

    def setUp(self):
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=1)
        self.subject = Subject.objects.create(name="Thermo", code="ME101", year=self.year,
                                              semester=1, department=self.dept)

        self.admin = User.objects.create_user("admin1", password="x", role="admin")
        self.placement = User.objects.create_user("place1", password="x", role="admin",
                                                  sub_role="placement_officer")
        self.teacher = User.objects.create_user("teach1", password="x", role="teacher", department=self.dept)
        self.other_teacher = User.objects.create_user("teach2", password="x", role="teacher", department=self.dept)
        self.student = User.objects.create_user("stu1", email="stu1@example.com", password="x",
                                                role="student", department=self.dept,
                                                course=self.course, year=1, semester=1)
        self.victim = User.objects.create_user("stu2", email="victim@example.com", password="x",
                                               role="student", department=self.dept,
                                               course=self.course, year=1, semester=1)
        self.parent = User.objects.create_user("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                    year=self.year, subject=self.subject)
        for s in (self.student, self.victim):
            Enrollment.objects.create(student=s, teaching_assignment=self.ta)

    def as_(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c


# =====================================================================
#  USERS - the worst one: a student could make themselves an admin
# =====================================================================
class UserLeakTests(RoleTestBase):

    def test_student_cannot_make_themselves_admin(self):
        r = self.as_(self.student).patch(f"/api/users/{self.student.id}/",
                                         {"role": "admin", "sub_role": "super_admin"}, format="json")
        self.assertIn(r.status_code, FORBIDDEN)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "student")

    def test_student_cannot_edit_or_delete_another_user(self):
        c = self.as_(self.student)
        self.assertIn(c.patch(f"/api/users/{self.victim.id}/", {"email": "x@x.com"},
                              format="json").status_code, FORBIDDEN)
        self.assertIn(c.delete(f"/api/users/{self.victim.id}/").status_code, FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=self.victim.pk, email="victim@example.com").exists())

    def test_student_cannot_create_a_user(self):
        r = self.as_(self.student).post("/api/users/", {
            "username": "hacker", "email": "h@x.com", "password": "Strong@12345",
            "role": "admin"}, format="json")
        self.assertIn(r.status_code, FORBIDDEN)
        self.assertFalse(User.objects.filter(username="hacker").exists())

    def test_non_admins_see_only_themselves(self):
        for user in (self.student, self.parent, self.teacher):
            r = self.as_(user).get("/api/users/")
            self.assertEqual(r.status_code, 200)
            ids = [u["id"] for u in (r.data.get("results", r.data) if isinstance(r.data, dict) else r.data)]
            self.assertEqual(ids, [user.id], user.username)          # Profile page still finds itself
            self.assertNotIn("victim@example.com", r.content.decode())
        self.assertIn(self.as_(self.student).get(f"/api/users/{self.victim.id}/").status_code, FORBIDDEN)

    def test_admin_still_manages_users(self):
        c = self.as_(self.admin)
        self.assertEqual(len(c.get("/api/users/").data), User.objects.count())
        r = c.post("/api/users/", {"username": "newteacher", "email": "nt@x.com",
                                   "password": "Strong@12345", "role": "teacher"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = c.patch(f"/api/users/{self.victim.id}/", {"first_name": "Renamed"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_only_main_admin_can_hand_out_admin_rights(self):
        c = self.as_(self.placement)
        r = c.patch(f"/api/users/{self.teacher.id}/", {"role": "admin", "sub_role": "super_admin"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = c.patch(f"/api/users/{self.admin.id}/", {"first_name": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        # ...but may still edit an ordinary teacher
        r = c.patch(f"/api/users/{self.teacher.id}/", {"sub_role": "professor"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        # and the main admin may promote
        r = self.as_(self.admin).patch(f"/api/users/{self.teacher.id}/",
                                       {"role": "admin", "sub_role": "academic_admin"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)


# =====================================================================
#  ACADEMIC SETUP - courses, years, subjects, departments, enrollments
# =====================================================================
class AcademicSetupTests(RoleTestBase):

    def test_non_admins_cannot_change_academic_setup(self):
        for user in (self.student, self.parent, self.teacher):
            c = self.as_(user)
            self.assertEqual(c.patch(f"/api/courses/{self.course.id}/", {"name": "X"}, format="json").status_code, 403)
            self.assertEqual(c.delete(f"/api/years/{self.year.id}/").status_code, 403)
            self.assertEqual(c.delete(f"/api/subjects/{self.subject.id}/").status_code, 403)
            self.assertEqual(c.patch(f"/api/users/departments/{self.dept.id}/", {"name": "X"}, format="json").status_code, 403)
            self.assertEqual(c.post("/api/courses/", {"name": "Fake"}, format="json").status_code, 403)
            self.assertEqual(c.post("/api/enrollments/", {"student": user.id,
                             "teaching_assignment": self.ta.id}, format="json").status_code, 403)
        self.assertEqual(Course.objects.get().name, "B.E Mech")
        self.assertTrue(Subject.objects.filter(pk=self.subject.pk).exists())

    def test_everyone_can_still_read_and_admin_can_write(self):
        self.assertEqual(self.as_(self.student).get("/api/courses/").status_code, 200)
        self.assertEqual(self.as_(self.student).get("/api/users/departments/").status_code, 200)
        r = self.as_(self.admin).post("/api/courses/", {"name": "B.E Civil"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)


# =====================================================================
#  NOTIFICATIONS - no fake messages
# =====================================================================
class NotificationTests(RoleTestBase):

    def test_nobody_can_send_a_notification_by_hand(self):
        for user in (self.student, self.teacher, self.admin):
            r = self.as_(user).post("/api/notifications/", {
                "recipient": self.victim.id, "title": "Pay here", "message": "fake link"}, format="json")
            self.assertEqual(r.status_code, 405)
        self.assertFalse(Notification.objects.filter(recipient=self.victim).exists())

    def test_people_still_read_and_mark_their_own(self):
        n = Notification.objects.create(recipient=self.student, title="Hi", message="m")
        c = self.as_(self.student)
        self.assertEqual(len(c.get("/api/notifications/").data), 1)
        self.assertEqual(c.post(f"/api/notifications/{n.id}/mark_read/").status_code, 200)
        self.assertEqual(c.post("/api/notifications/mark_all_read/").status_code, 200)
        self.assertEqual(self.as_(self.victim).post(f"/api/notifications/{n.id}/mark_read/").status_code, 404)


# =====================================================================
#  RESULTS AND INTERNAL ASSESSMENT MARKS
# =====================================================================
class ResultsAndMarksTests(RoleTestBase):

    def setUp(self):
        super().setUp()
        self.result = SemesterResult.objects.create(student=self.victim, semester=1, is_published=True)
        ResultEntry.objects.create(result=self.result, subject=self.subject, max_marks=100, marks_obtained=33)
        self.ia = InternalAssessment.objects.create(teaching_assignment=self.ta, number=1)
        IAMark.objects.create(assessment=self.ia, student=self.victim, marks_obtained=12)

    def test_teacher_cannot_read_or_change_semester_results(self):
        c = self.as_(self.teacher)
        self.assertEqual(c.get("/api/semester-results/").data, [])
        self.assertIn(c.patch(f"/api/semester-results/{self.result.id}/", {"semester": 2},
                              format="json").status_code, FORBIDDEN)
        self.assertIn(c.delete(f"/api/semester-results/{self.result.id}/").status_code, FORBIDDEN)
        self.assertTrue(SemesterResult.objects.filter(pk=self.result.pk, semester=1).exists())

    def test_student_cannot_create_a_result(self):
        r = self.as_(self.student).post("/api/semester-results/", {
            "student": self.student.id, "semester": 2, "is_published": True}, format="json")
        self.assertIn(r.status_code, FORBIDDEN)
        self.assertFalse(SemesterResult.objects.filter(student=self.student).exists())

    def test_students_and_parents_cannot_read_everyones_ia_marks(self):
        for user in (self.student, self.parent):
            c = self.as_(user)
            self.assertEqual(c.get("/api/internal-assessments/").data, [])
            self.assertIn(c.patch(f"/api/internal-assessments/{self.ia.id}/", {"max_marks": 1},
                                  format="json").status_code, FORBIDDEN)
            self.assertIn(c.delete(f"/api/internal-assessments/{self.ia.id}/").status_code, FORBIDDEN)
        self.assertTrue(InternalAssessment.objects.filter(pk=self.ia.pk).exists())

    def test_student_posting_ia_mark_is_refused_not_a_crash(self):
        r = self.as_(self.student).post("/api/ia-marks/", {"student": self.student.id}, format="json")
        self.assertIn(r.status_code, (400, 403))

    def test_admin_and_teacher_keep_their_access(self):
        self.assertEqual(len(self.as_(self.admin).get("/api/semester-results/").data), 1)
        self.assertEqual(len(self.as_(self.teacher).get("/api/internal-assessments/").data), 1)
        self.assertEqual(len(self.as_(self.victim).get("/api/semester-results/").data), 1)   # own result


# =====================================================================
#  FEES
# =====================================================================
class FeeTests(RoleTestBase):

    def test_student_and_parent_cannot_raise_change_or_delete_fees(self):
        fee = Fee.objects.create(student=self.student, term="Tuition", amount=50000, due_date=TODAY)
        for user in (self.student, self.parent):
            c = self.as_(user)
            r = c.post("/api/fees/", {"student": self.student.id, "term": "Fake", "amount": 1,
                                      "due_date": "2026-12-31"}, format="json")
            self.assertIn(r.status_code, FORBIDDEN)
            self.assertIn(c.patch(f"/api/fees/{fee.id}/", {"amount": 1}, format="json").status_code, FORBIDDEN)
            self.assertIn(c.delete(f"/api/fees/{fee.id}/").status_code, FORBIDDEN)
        fee.refresh_from_db()
        self.assertEqual(fee.amount, 50000)
        self.assertEqual(Fee.objects.count(), 1)

    def test_admin_can_still_edit_a_fee(self):
        fee = Fee.objects.create(student=self.student, term="Tuition", amount=50000, due_date=TODAY)
        r = self.as_(self.admin).patch(f"/api/fees/{fee.id}/", {"due_date": "2027-01-15"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)


# =====================================================================
#  LEARNING - materials, quiz questions, discussions, feedback, plans
# =====================================================================
class LearningTests(RoleTestBase):

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(title="Q1", teaching_assignment=self.ta, created_by=self.teacher)
        self.question = Question.objects.create(quiz=self.quiz, text="2+2?", option1="3", option2="4",
                                                option3="5", option4="6", correct_answer=2)
        self.material = StudyMaterial.objects.create(title="Notes", file="study_materials/n.pdf",
                                                     teaching_assignment=self.ta, uploaded_by=self.teacher)
        self.msg = DiscussionMessage.objects.create(teaching_assignment=self.ta, user=self.victim,
                                                    message="victim message")
        self.feedback = Feedback.objects.create(teaching_assignment=self.ta, student=self.victim,
                                                teacher=self.teacher, direction="s2t", message="private")
        self.plan = TeachingPlan.objects.create(teacher=self.teacher, subject=self.subject,
                                                department=self.dept, class_section="ME 1",
                                                semester="Odd 2026")

    def test_other_teacher_cannot_change_my_quiz_questions(self):
        c = self.as_(self.other_teacher)
        # 403 (refused) or 404 (Part 3: not even visible to them) - both block the change
        self.assertIn(c.patch(f"/api/questions/{self.question.id}/", {"text": "hacked"},
                              format="json").status_code, (403, 404))
        self.assertIn(c.delete(f"/api/questions/{self.question.id}/").status_code, (403, 404))
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "2+2?")
        r = self.as_(self.teacher).patch(f"/api/questions/{self.question.id}/", {"text": "3+3?"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_students_never_get_the_answer(self):
        r = self.as_(self.student).get(f"/api/questions/?quiz={self.quiz.id}")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("correct_answer", r.content.decode())

    def test_only_the_subject_teacher_manages_its_materials(self):
        for user in (self.student, self.parent, self.other_teacher):
            c = self.as_(user)
            self.assertIn(c.patch(f"/api/study-materials/{self.material.id}/", {"title": "x"},
                                  format="multipart").status_code, FORBIDDEN)
            self.assertIn(c.delete(f"/api/study-materials/{self.material.id}/").status_code, FORBIDDEN)
        self.material.refresh_from_db()
        self.assertEqual(self.material.title, "Notes")
        r = self.as_(self.teacher).patch(f"/api/study-materials/{self.material.id}/", {"title": "New"},
                                         format="multipart")
        self.assertEqual(r.status_code, 200, r.content)

    def test_only_the_author_edits_a_discussion_message(self):
        r = self.as_(self.student).patch(f"/api/discussions/{self.msg.id}/", {"message": "edited"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.as_(self.student).delete(f"/api/discussions/{self.msg.id}/").status_code, 403)
        self.assertEqual(self.as_(self.victim).patch(f"/api/discussions/{self.msg.id}/",
                                                     {"message": "mine"}, format="json").status_code, 200)
        self.assertEqual(self.as_(self.teacher).delete(f"/api/discussions/{self.msg.id}/").status_code, 204)

    def test_parent_cannot_read_or_change_feedback(self):
        c = self.as_(self.parent)
        self.assertEqual(c.get("/api/feedback/").data, [])
        self.assertIn(c.patch(f"/api/feedback/{self.feedback.id}/", {"message": "x"},
                              format="json").status_code, FORBIDDEN)
        self.assertIn(c.delete(f"/api/feedback/{self.feedback.id}/").status_code, FORBIDDEN)
        self.assertEqual(len(self.as_(self.teacher).get("/api/feedback/").data), 1)   # the teacher still sees it

    def test_only_the_owner_changes_a_teaching_plan(self):
        for user in (self.student, self.parent, self.other_teacher):
            c = self.as_(user)
            self.assertEqual(c.patch(f"/api/teaching-plans/{self.plan.id}/", {"allotted_hours": 99},
                                     format="json").status_code, 403, user.username)
            self.assertEqual(c.delete(f"/api/teaching-plans/{self.plan.id}/").status_code, 403, user.username)
        self.assertTrue(TeachingPlan.objects.filter(pk=self.plan.pk, allotted_hours=0).exists())
