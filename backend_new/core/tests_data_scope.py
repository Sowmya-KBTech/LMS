"""
PHASE 5, PART 3 TESTS - data scope: lists show only what each person should see.

Two subject-classes in one college:
  ta_mine   taught by `teacher`, `student` enrolled      (parent = student's parent)
  ta_other  taught by `other_teacher`, `classmate` enrolled
The HOD heads the department both subjects belong to.

Run:  python manage.py test core.tests_data_scope -v 2
"""
from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, ParentProfile, User
from modules.learning.models import DiscussionMessage, Question, Quiz
from modules.teachingplan.models import TeachingPlan
from modules.teachingplan.views import year_label


class ScopeTestBase(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.admin = mk("admin1", password="x", role="admin")
        self.teacher = mk("teach1", password="x", role="teacher", department=self.dept)
        self.other_teacher = mk("teach2", password="x", role="teacher", department=self.dept)
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=1)
        mine = Subject.objects.create(name="Thermo", code="ME101", year=self.year, semester=1, department=self.dept)
        other = Subject.objects.create(name="Fluids", code="ME102", year=self.year, semester=1, department=self.dept)
        self.ta_mine = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                         year=self.year, subject=mine)
        self.ta_other = TeachingAssignment.objects.create(teacher=self.other_teacher, course=self.course,
                                                          year=self.year, subject=other)
        self.student = mk("stu1", password="x", role="student", course=self.course, year=1, semester=1)
        self.classmate = mk("stu2", password="x", role="student", course=self.course, year=1, semester=1)
        Enrollment.objects.create(student=self.student, teaching_assignment=self.ta_mine)
        Enrollment.objects.create(student=self.classmate, teaching_assignment=self.ta_other)
        self.parent = mk("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

    def get(self, user, url):
        c = APIClient()
        c.force_authenticate(user=user)
        r = c.get(url)
        self.assertEqual(r.status_code, 200, r.content)
        data = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        return data

    def ids(self, user, url):
        return sorted(row["id"] for row in self.get(user, url))


# =====================================================================
#  DISCUSSIONS
# =====================================================================
class DiscussionScopeTests(ScopeTestBase):

    def setUp(self):
        super().setUp()
        self.mine = DiscussionMessage.objects.create(teaching_assignment=self.ta_mine, user=self.student, message="mine")
        self.theirs = DiscussionMessage.objects.create(teaching_assignment=self.ta_other, user=self.classmate,
                                                       message="other class")

    def test_each_person_sees_only_their_own_subjects(self):
        self.assertEqual(self.ids(self.student, "/api/discussions/"), [self.mine.id])
        self.assertEqual(self.ids(self.teacher, "/api/discussions/"), [self.mine.id])
        self.assertEqual(self.ids(self.other_teacher, "/api/discussions/"), [self.theirs.id])
        self.assertEqual(self.ids(self.parent, "/api/discussions/"), [])

    def test_filter_for_another_subject_returns_nothing(self):
        self.assertEqual(self.ids(self.student, f"/api/discussions/?teaching_assignment={self.ta_other.id}"), [])

    def test_hod_and_admin_see_the_department(self):
        both = sorted([self.mine.id, self.theirs.id])
        self.assertEqual(self.ids(self.hod, "/api/discussions/"), both)
        self.assertEqual(self.ids(self.admin, "/api/discussions/"), both)

    def test_cannot_open_another_class_message_by_id(self):
        c = APIClient()
        c.force_authenticate(user=self.student)
        self.assertEqual(c.get(f"/api/discussions/{self.theirs.id}/").status_code, 404)

    def test_cannot_post_into_another_class(self):
        c = APIClient()
        c.force_authenticate(user=self.student)
        r = c.post("/api/discussions/", {"teaching_assignment": self.ta_other.id, "message": "spam"}, format="json")
        self.assertEqual(r.status_code, 403)
        c.force_authenticate(user=self.other_teacher)
        r = c.post("/api/discussions/", {"teaching_assignment": self.ta_mine.id, "message": "spam"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(DiscussionMessage.objects.count(), 2)

    def test_members_can_still_post(self):
        c = APIClient()
        c.force_authenticate(user=self.student)
        r = c.post("/api/discussions/", {"teaching_assignment": self.ta_mine.id, "message": "hello"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)


# =====================================================================
#  QUIZ QUESTIONS
# =====================================================================
class QuestionScopeTests(ScopeTestBase):

    def setUp(self):
        super().setUp()
        q_mine = Quiz.objects.create(title="Q1", teaching_assignment=self.ta_mine, created_by=self.teacher)
        q_other = Quiz.objects.create(title="Q2", teaching_assignment=self.ta_other, created_by=self.other_teacher)
        kw = dict(text="?", option1="a", option2="b", option3="c", option4="d", correct_answer=1)
        self.qm = Question.objects.create(quiz=q_mine, **kw)
        self.qo = Question.objects.create(quiz=q_other, **kw)

    def test_each_person_sees_only_their_own_quizzes(self):
        self.assertEqual(self.ids(self.teacher, "/api/questions/"), [self.qm.id])
        self.assertEqual(self.ids(self.other_teacher, "/api/questions/"), [self.qo.id])
        self.assertEqual(self.ids(self.student, "/api/questions/"), [self.qm.id])
        self.assertEqual(self.ids(self.parent, "/api/questions/"), [])
        self.assertEqual(self.ids(self.admin, "/api/questions/"), sorted([self.qm.id, self.qo.id]))

    def test_filter_for_another_quiz_returns_nothing(self):
        self.assertEqual(self.ids(self.student, f"/api/questions/?quiz={self.qo.quiz_id}"), [])
        self.assertEqual(self.ids(self.teacher, f"/api/questions/?quiz={self.qo.quiz_id}"), [])

    def test_teacher_quiz_editor_still_loads(self):
        rows = self.get(self.teacher, f"/api/questions/?quiz={self.qm.quiz_id}")
        self.assertEqual([r["id"] for r in rows], [self.qm.id])
        self.assertIn("correct_answer", rows[0])        # the teacher still sees the answer


# =====================================================================
#  TEACHING PLANS
# =====================================================================
class TeachingPlanScopeTests(ScopeTestBase):

    def setUp(self):
        super().setUp()
        label = year_label(self.year)
        common = dict(department=self.dept, class_section=label, semester="Odd 2026", status="approved")
        self.p_mine = TeachingPlan.objects.create(teacher=self.teacher, subject=self.ta_mine.subject, **common)
        self.p_other = TeachingPlan.objects.create(teacher=self.other_teacher, subject=self.ta_other.subject, **common)
        self.p_elsewhere = TeachingPlan.objects.create(
            teacher=self.other_teacher, subject=self.ta_other.subject, department=self.dept,
            class_section="B.E Civil - Year 3", semester="Odd 2026", status="approved")

    def test_plain_list_is_staff_scoped(self):
        self.assertEqual(self.ids(self.teacher, "/api/teaching-plans/"), [self.p_mine.id])
        self.assertEqual(self.ids(self.student, "/api/teaching-plans/"), [])
        self.assertEqual(self.ids(self.parent, "/api/teaching-plans/"), [])
        everything = sorted([self.p_mine.id, self.p_other.id, self.p_elsewhere.id])
        self.assertEqual(self.ids(self.hod, "/api/teaching-plans/"), everything)
        self.assertEqual(self.ids(self.admin, "/api/teaching-plans/"), everything)

    def test_cannot_open_another_teachers_plan_by_id(self):
        c = APIClient()
        c.force_authenticate(user=self.teacher)
        self.assertEqual(c.get(f"/api/teaching-plans/{self.p_other.id}/").status_code, 404)
        c.force_authenticate(user=self.student)
        self.assertEqual(c.get(f"/api/teaching-plans/{self.p_mine.id}/").status_code, 404)

    def test_student_screen_shows_only_their_class(self):
        got = self.ids(self.student, "/api/teaching-plans/student/")
        self.assertIn(self.p_mine.id, got)
        self.assertNotIn(self.p_elsewhere.id, got)

    def test_no_class_means_no_plans_not_every_plan(self):
        loner = User.objects.create_user("stu9", password="x", role="student")
        self.assertEqual(self.ids(loner, "/api/teaching-plans/student/"), [])
        self.assertEqual(self.ids(self.parent, "/api/teaching-plans/student/"), [])

    def test_teacher_and_hod_screens_still_work(self):
        self.assertEqual(self.ids(self.teacher, "/api/teaching-plans/my/"), [self.p_mine.id])
        self.assertEqual(len(self.get(self.hod, "/api/teaching-plans/department/")), 3)
