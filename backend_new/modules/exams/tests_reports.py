"""
WAVE 1 TESTS - rank lists and progress reports.

Run:  python manage.py test modules.exams.tests_reports -v 2
"""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year, YearTutor
from core.users.models import Department, ParentProfile, User
from modules.attendance.models import Attendance
from modules.exams.models import IAMark, InternalAssessment, ResultEntry, SemesterResult
from modules.mentoring.models import MentorAllocation
from modules.mentoring.utils import current_academic_year


class ReportTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.other_hod = mk("hod2", password="x", role="teacher")
        Department.objects.create(name="Civil", code="CE", hod=self.other_hod)
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.tutor = mk("tutor1", password="x", role="teacher", department=self.dept)
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.year)
        self.stranger = mk("teach9", password="x", role="teacher", department=self.dept)
        self.admin = mk("admin1", password="x", role="admin")
        self.thermo = Subject.objects.create(name="Thermo", code="ME301", year=self.year, semester=3)
        self.fluids = Subject.objects.create(name="Fluids", code="ME302", year=self.year, semester=3)

        def student(name, roll):
            return mk(name, password="x", role="student", department=self.dept, course=self.course,
                      year=2, semester=3, roll_number=roll)
        self.s1, self.s2, self.s3, self.s4 = (student("asha", "R01"), student("bala", "R02"),
                                              student("chitra", "R03"), student("dinesh", "R04"))
        # semester 3: asha 90%, bala 80%, chitra 80% (tie), dinesh 95% but failed Fluids
        self.result(self.s1, [(90, True), (90, True)])
        self.result(self.s2, [(85, True), (75, True)])
        self.result(self.s3, [(75, True), (85, True)])
        self.result(self.s4, [(100, True), (90, False)])
        self.result(self.s1, [(10, True), (10, True)], semester=4, published=False)   # not published

        self.parent = mk("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.s1)

    def result(self, student, marks, semester=3, published=True):
        sr = SemesterResult.objects.create(student=student, semester=semester, is_published=published)
        for subject, (m, ok) in zip((self.thermo, self.fluids), marks):
            ResultEntry.objects.create(result=sr, subject=subject, max_marks=100, marks_obtained=m,
                                       grade="A" if ok else "U", is_pass=ok)

    def get(self, user, url):
        c = APIClient()
        c.force_authenticate(user=user)
        return c.get(url)

    def rank_url(self, semester=3):
        return f"/api/reports/rank-list/?course={self.course.id}&year=2&semester={semester}"

    # ---------------- rank list ----------------
    def test_ranks_ties_and_arrears(self):
        r = self.get(self.tutor, self.rank_url())
        self.assertEqual(r.status_code, 200, r.content)
        rows = r.json()["rows"]
        self.assertEqual([(x["username"], x["rank"]) for x in rows],
                         [("asha", 1), ("bala", 2), ("chitra", 2), ("dinesh", None)])
        self.assertEqual(rows[0]["percentage"], 90.0)
        self.assertEqual(rows[3]["arrears"], 1)
        s = r.json()["summary"]
        self.assertEqual((s["appeared"], s["all_clear"], s["pass_percentage"]), (4, 3, 75.0))

    def test_subject_toppers(self):
        toppers = {t["subject"]: t["top"] for t in self.get(self.tutor, self.rank_url()).json()["toppers"]}
        self.assertEqual(toppers["Thermo"][0]["name"], "dinesh")        # 100: toppers count marks, not arrears
        self.assertEqual([t["marks"] for t in toppers["Fluids"]], [90, 90, 85])

    def test_unpublished_results_are_left_out(self):
        self.assertEqual(self.get(self.tutor, self.rank_url(semester=4)).json()["rows"], [])

    def test_who_may_see_a_rank_list(self):
        for user in (self.tutor, self.hod, self.admin):
            self.assertEqual(self.get(user, self.rank_url()).status_code, 200, user.username)
        for user in (self.stranger, self.other_hod, self.s1, self.parent):
            self.assertEqual(self.get(user, self.rank_url()).status_code, 403, user.username)
        self.assertEqual(self.get(self.tutor, "/api/reports/rank-list/?course=x").status_code, 400)

    def test_sub_admins(self):
        exam = User.objects.create_user("exam1", password="x", role="admin", sub_role="exam_admin")
        fees = User.objects.create_user("fees1", password="x", role="admin", sub_role="accounts_admin")
        self.assertEqual(self.get(exam, self.rank_url()).status_code, 200)
        self.assertEqual(self.get(exam, f"/api/reports/progress/{self.s1.id}/").status_code, 200)
        self.assertEqual(self.get(fees, self.rank_url()).status_code, 403)
        self.assertEqual(self.get(fees, f"/api/reports/progress/{self.s1.id}/").status_code, 404)
        self.assertEqual(self.get(fees, "/api/reports/classes/").json(), [])

    def test_class_picker(self):
        rows = self.get(self.tutor, "/api/reports/classes/").json()
        self.assertEqual([(r["course_name"], r["year"], r["semesters"]) for r in rows], [("B.E Mech", 2, [3])])
        self.assertEqual(len(self.get(self.hod, "/api/reports/classes/").json()), 1)
        self.assertEqual(self.get(self.stranger, "/api/reports/classes/").json(), [])

    # ---------------- progress report ----------------
    def test_student_report_has_results_rank_ia_and_attendance(self):
        ta = TeachingAssignment.objects.create(teacher=self.stranger, course=self.course, year=self.year,
                                               subject=self.thermo)
        for h, st in ((1, "present"), (2, "present"), (3, "duty_leave"), (4, "absent")):
            Attendance.objects.create(teaching_assignment=ta, student=self.s1,
                                      date=datetime.date(2026, 11, 2), hour=h, status=st)
        declared = InternalAssessment.objects.create(teaching_assignment=ta, number=1, max_marks=50, is_locked=True)
        draft = InternalAssessment.objects.create(teaching_assignment=ta, number=2, max_marks=50, is_locked=False)
        IAMark.objects.create(assessment=declared, student=self.s1, marks_obtained=42)
        IAMark.objects.create(assessment=draft, student=self.s1, marks_obtained=10)

        r = self.get(self.s1, "/api/reports/progress/me/")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        sem3 = data["semester_results"][0]
        self.assertEqual((sem3["semester"], sem3["percentage"], sem3["rank"], sem3["class_size"]), (3, 90.0, 1, 4))
        self.assertEqual(len(data["semester_results"]), 1)                       # unpublished sem 4 hidden
        att = data["attendance"]["subjects"][0]
        self.assertEqual((att["attended"], att["total"], att["percentage"]), (3, 4, 75.0))
        ia = data["internal_assessments"][0]
        self.assertEqual([t["number"] for t in ia["tests"]], [1])                 # draft IA 2 hidden
        self.assertEqual(ia["tests"][0]["obtained"], 42)

    def test_who_may_open_a_progress_report(self):
        url = f"/api/reports/progress/{self.s1.id}/"
        for user in (self.s1, self.parent, self.tutor, self.hod, self.admin):
            self.assertEqual(self.get(user, url).status_code, 200, user.username)
        for user in (self.s2, self.stranger, self.other_hod):
            self.assertEqual(self.get(user, url).status_code, 404, user.username)
        MentorAllocation.objects.create(student=self.s1, mentor=self.stranger, department=self.dept,
                                        academic_year=current_academic_year(), status="active", is_active=True)
        self.assertEqual(self.get(self.stranger, url).status_code, 200)            # now their mentor

    def test_arrears_student_report_shows_no_rank(self):
        sem3 = self.get(self.tutor, f"/api/reports/progress/{self.s4.id}/").json()["semester_results"][0]
        self.assertIsNone(sem3["rank"])
        self.assertEqual(sem3["arrears"], 1)

    def test_only_students_have_me(self):
        self.assertEqual(self.get(self.parent, "/api/reports/progress/me/").status_code, 403)
