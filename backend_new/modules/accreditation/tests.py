"""
WAVE 2 TESTS - accreditation (NAAC / NBA) reports.

Run:  python manage.py test modules.accreditation -v 2
"""
import datetime
from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, FacultyParticipation, PrincipalTerm, User
from modules.accreditation.reports import current_year
from modules.attendance.models import Attendance
from modules.exams.models import ResultEntry, SemesterResult
from modules.mentoring.models import MentorAllocation
from modules.mentoring.utils import current_academic_year
from modules.placement.models import Application, Company, Drive, HigherStudies, JobRole, Offer
from modules.surveys.models import Answer, Participation, Question, Response, Survey

TODAY = timezone.localdate()
Y = current_year()


class AccreditationTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.iqac = mk("iqac1", password="x", role="admin", sub_role="iqac_admin")
        self.exam = mk("exam1", password="x", role="admin", sub_role="exam_admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.me = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.me
        self.hod.save()
        self.ce = Department.objects.create(name="Civil", code="CE")
        self.t1 = mk("ravi", password="x", role="teacher", department=self.me)
        self.t2 = mk("meena", password="x", role="teacher", department=self.ce)
        self.mech = Course.objects.create(name="B.E Mech")
        self.civil = Course.objects.create(name="B.E Civil")
        for n in range(1, 5):                                  # a 4-year course
            Year.objects.create(course=self.mech, year_number=n)
        self.y2 = Year.objects.get(course=self.mech, year_number=2)
        self.subj = Subject.objects.create(name="Thermo", code="ME301", year=self.y2, semester=3)
        self.ta = TeachingAssignment.objects.create(teacher=self.t1, course=self.mech, year=self.y2, subject=self.subj)

        def st(n, dept, course, year, sem, batch=None):
            return mk(n, password="x", role="student", department=dept, course=course, year=year, semester=sem,
                      batch_year=batch)
        self.s1 = st("asha", self.me, self.mech, 2, 3)
        self.s2 = st("bala", self.me, self.mech, 2, 3)
        self.s3 = st("chitra", self.me, self.mech, 4, 7, batch=Y + 1 - 4)       # graduates this year
        self.s4 = st("dinesh", self.me, self.mech, 4, 7, batch=Y + 1 - 4)
        self.s5 = st("esha", self.ce, self.civil, 1, 1)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def report(self, key, user=None, **params):
        q = "&".join(f"{k}={v}" for k, v in params.items())
        r = self.c(user or self.iqac).get(f"/api/accreditation/reports/{key}/?{q}")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["report"]

    # ---------------------------------------------------------------- access
    def test_who_can_see_reports(self):
        for u in (self.admin, self.iqac, self.hod):
            self.assertEqual(self.c(u).get("/api/accreditation/reports/").status_code, 200, u.username)
        for u in (self.exam, self.t1, self.s1):
            self.assertEqual(self.c(u).get("/api/accreditation/reports/").status_code, 403, u.username)
        PrincipalTerm.objects.create(teacher=self.t2, start_date=TODAY)
        self.assertTrue(self.c(self.t2).get("/api/accreditation/reports/").json()["college_wide"])

    def test_hod_is_locked_to_own_department(self):
        data = self.c(self.hod).get("/api/accreditation/reports/").json()
        self.assertEqual((data["department"], data["college_wide"]), (self.me.id, False))
        self.assertEqual([d["id"] for d in data["departments"]], [self.me.id])
        self.assertEqual(self.c(self.hod).get(f"/api/accreditation/reports/?department={self.ce.id}").status_code, 403)
        strength = self.report("student-strength", self.hod)
        self.assertEqual(strength["total"]["students"], 4)                      # ME only, not esha
        self.assertEqual(self.report("student-strength")["total"]["students"], 5)

    def test_bad_input(self):
        self.assertEqual(self.c(self.iqac).get("/api/accreditation/reports/nope/").status_code, 404)
        self.assertEqual(self.c(self.iqac).get("/api/accreditation/reports/?year=abc").status_code, 400)
        self.assertEqual(self.c(self.iqac).get(f"/api/accreditation/reports/?year={Y + 3}").status_code, 400)

    def test_list_has_all_eight(self):
        data = self.c(self.iqac).get("/api/accreditation/reports/").json()
        self.assertEqual(len(data["reports"]), 8)
        self.assertEqual(data["year"], Y)
        self.assertTrue(all(r["available"] for r in data["reports"]))

    # ---------------------------------------------------------------- the numbers
    def test_pass_percentage(self):
        for s, ok in ((self.s1, True), (self.s2, False)):
            sr = SemesterResult.objects.create(student=s, semester=3, is_published=True)
            ResultEntry.objects.create(result=sr, subject=self.subj, max_marks=100, marks_obtained=70 if ok else 20,
                                       grade="A" if ok else "U", is_pass=ok)
        SemesterResult.objects.create(student=self.s3, semester=7, is_published=False)    # not published
        old = SemesterResult.objects.create(student=self.s4, semester=5, is_published=True)
        SemesterResult.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=500))                    # last year
        r = self.report("pass-percentage")
        self.assertEqual([(x["semester"], x["appeared"], x["passed"], x["pass_percent"]) for x in r["rows"]],
                         [(3, 2, 1, 50.0)])
        last = self.report("pass-percentage", year=Y - 1)
        self.assertEqual(last["total"]["appeared"], 1)

    def test_survey_reports(self):
        s = Survey.objects.create(title="SSS", audience="students", template="student_satisfaction",
                                  status="open", start_date=TODAY, department=self.me)
        q = Question.objects.create(survey=s, order=1, kind="rating", text="Teachers came prepared")
        Question.objects.create(survey=s, order=2, kind="text", text="Comments", required=False)
        for u, rating in ((self.s1, 5), (self.s2, 3)):
            Participation.objects.create(survey=s, user=u)
            Answer.objects.create(response=Response.objects.create(survey=s), question=q, rating=rating)
        r = self.report("student-satisfaction")
        self.assertEqual(len(r["rows"]), 1)                                     # rating questions only
        row = r["rows"][0]
        self.assertEqual((row["answers"], row["average"], row["agree_percent"], row["response_rate"]),
                         (2, 4.0, 50.0, 50.0))                                 # 2 of 4 ME students answered
        self.assertEqual(self.report("student-satisfaction", department=self.ce.id)["rows"], [])
        self.assertEqual(self.report("curriculum-feedback")["rows"], [])        # other templates only

    def test_mentor_ratio(self):
        for s in (self.s1, self.s2, self.s3):
            MentorAllocation.objects.create(student=s, mentor=self.t1, department=self.me,
                                            academic_year=current_academic_year(), status="active", is_active=True)
        r = self.report("mentor-ratio")
        me = next(x for x in r["rows"] if x["department"] == "Mechanical")
        self.assertEqual((me["students"], me["mentored"], me["not_mentored"], me["mentors"], me["ratio"]),
                         (4, 3, 1, 1, "1 : 3.0"))

    def test_faculty_development(self):
        V = {"status": "verified"}                                           # HRIS PART B: verified only
        FacultyParticipation.objects.create(faculty=self.t1, category="fdp", title="AI FDP", date=TODAY, **V)
        FacultyParticipation.objects.create(faculty=self.t1, category="journal", title="Paper", date=TODAY, **V)
        FacultyParticipation.objects.create(faculty=self.t2, category="committee", title="NSS", date=TODAY, **V)
        FacultyParticipation.objects.create(faculty=self.t2, category="fdp", title="Old",
                                            date=datetime.date(Y - 2, 7, 1), **V)   # another year
        FacultyParticipation.objects.create(faculty=self.t2, category="journal", title="Not yet verified",
                                            date=TODAY)                       # waiting: not counted
        r = self.report("faculty-development")
        me = next(x for x in r["rows"] if x["department"] == "Mechanical")
        self.assertEqual((me["teachers"], me["active"], me["fdp"], me["journals"], me["total"]), (2, 1, 1, 1, 2))
        self.assertEqual((r["total"]["other"], r["total"]["total"]), (1, 3))

    def test_placement_uses_graduating_batch(self):
        drive = Drive.objects.create(company=Company.objects.create(name="Acme", category="core"), status="completed")
        role = JobRole.objects.create(drive=drive, title="Engineer", package_lpa=Decimal("6.5"))
        app = Application.objects.create(student=self.s3, job_role=role, status="applied")
        Offer.objects.create(application=app, package_lpa=Decimal("6.5"), status="accepted")
        HigherStudies.objects.create(student=self.s4, institution="IIT Madras")
        r = self.report("placement")
        self.assertEqual((r["total"]["students"], r["total"]["placed"], r["total"]["placed_percent"],
                          r["total"]["higher_studies"], r["total"]["progression_percent"], r["total"]["median_lpa"]),
                         (2, 1, 50.0, 1, 100.0, 6.5))                        # s1/s2 are not final year

    def test_attendance(self):
        for h, (a, b) in enumerate([("present", "absent"), ("duty_leave", "absent"), ("present", "present")], 1):
            Attendance.objects.create(teaching_assignment=self.ta, student=self.s1, date=TODAY, hour=h, status=a)
            Attendance.objects.create(teaching_assignment=self.ta, student=self.s2, date=TODAY, hour=h, status=b)
        r = self.report("attendance")
        self.assertEqual([(x["students"], x["hours"], x["attendance_percent"], x["below_75"]) for x in r["rows"]],
                         [(2, 6, 66.7, 1)])                                   # bala 1/3 is below 75%

    # ---------------------------------------------------------------- excel
    def test_excel_download(self):
        from openpyxl import load_workbook
        r = self.c(self.hod).get("/api/accreditation/reports/student-strength/excel/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("student-strength_", r["Content-Disposition"])
        ws = load_workbook(BytesIO(r.content)).active
        values = [c for row in ws.iter_rows(values_only=True) for c in row if c is not None]
        self.assertIn("Student strength", values)
        self.assertIn("Students", values)                                     # header row
        self.assertIn(4, values)                                              # HOD's total: ME only
        self.assertEqual(self.c(self.t1).get("/api/accreditation/reports/student-strength/excel/").status_code, 403)
