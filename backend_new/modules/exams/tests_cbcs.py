"""
WAVE 3 PART 1B TESTS - results under the student's regulation (CBCS).

Run:  python manage.py test modules.exams.tests_cbcs -v 2
"""
import io

from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from core.academics import regulations as R
from core.academics.models import (Course, CourseCategory, CreditRequirement, Subject, TeachingAssignment,
                                   Year)
from core.users.models import Department, User
from modules.exams.models import ResultAttempt, ResultEntry, SemesterResult
from modules.exams.services import get_arrear_count, get_cgpa


class CBCSResultsBase(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mech")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.admin = mk("admin1", password="x", role="admin")
        self.exam = mk("exam1", password="x", role="admin", sub_role="exam_admin")
        self.teacher = mk("ravi", password="x", role="teacher", department=self.dept)
        self.student = mk("asha", password="x", role="student", department=self.dept, course=self.course,
                          year=2, semester=3, batch_year=2023, roll_number="23ME001")
        self.other = mk("bala", password="x", role="student", department=self.dept, course=self.course,
                        year=2, semester=3, batch_year=2023, roll_number="23ME002")
        self.reg = R.create_regulation("R2021", "template", self.admin)
        R.add_template_categories()
        self.pcc = CourseCategory.objects.get(code="PCC")
        self.mc = CourseCategory.objects.get(code="MC")
        self.thermo = Subject.objects.create(name="Thermodynamics", code="ME301", year=self.y2, semester=3,
                                             credits=4, category=self.pcc)
        self.lab = Subject.objects.create(name="Fluids lab", code="ME311", year=self.y2, semester=3,
                                          credits=2, category=self.pcc, kind="practical")
        self.maths = Subject.objects.create(name="Transforms", code="MA301", year=self.y2, semester=3,
                                            credits=3, category=self.pcc)
        self.env = Subject.objects.create(name="Environmental Science", code="MC301", year=self.y2, semester=3,
                                          credits=0, category=self.mc)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y2,
                                                    subject=self.thermo)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def save(self, subject, records, session="", user=None):
        return self.c(user or self.exam).post("/api/semester-results/save_results/", {
            "subject": subject.id, "semester": 3, "exam_session": session, "records": records}, format="json")

    def entry(self, subject, student=None):
        return ResultEntry.objects.get(result__student=student or self.student, subject=subject)

    def publish(self, student=None):
        SemesterResult.objects.filter(student=student or self.student).update(is_published=True)


class GradingTests(CBCSResultsBase):

    def test_internal_and_end_sem_graded_by_the_regulation(self):
        r = self.save(self.thermo, [{"student": self.student.id, "internal_marks": 34, "end_marks": 48}], "Nov/Dec 2025")
        self.assertEqual(r.status_code, 200, r.content)
        e = self.entry(self.thermo)
        self.assertEqual((e.marks_obtained, e.max_marks, e.grade, e.is_pass, float(e.grade_points), e.outcome),
                         (82, 100, "A+", True, 9.0, "pass"))
        self.assertEqual((e.attempt, e.exam_session), (1, "Nov/Dec 2025"))

    def test_end_sem_pass_mark_gives_ra_even_with_a_pass_total(self):
        self.save(self.thermo, [{"student": self.student.id, "internal_marks": 40, "end_marks": 26}])  # 66 total, 43% end
        e = self.entry(self.thermo)
        self.assertEqual((e.grade, e.is_pass, e.outcome), ("RA", False, "fail"))
        self.save(self.lab, [{"student": self.student.id, "internal_marks": 52, "end_marks": 34}])     # practical 60/40
        self.assertEqual(self.entry(self.lab).grade, "A+")

    def test_total_only_absent_and_by_hand(self):
        self.save(self.thermo, [{"student": self.student.id, "marks_obtained": 55},
                                {"student": self.other.id, "marks_obtained": None}])
        self.assertEqual(self.entry(self.thermo).grade, "C")
        self.assertEqual((self.entry(self.thermo, self.other).grade, self.entry(self.thermo, self.other).is_pass),
                         ("RA", False))
        self.save(self.maths, [{"student": self.student.id, "grade": "SA"}])
        e = self.entry(self.maths)
        self.assertEqual((e.grade, e.is_pass, e.outcome), ("SA", False, "arrear"))

    def test_bad_rows_save_nothing(self):
        r = self.save(self.thermo, [{"student": self.student.id, "internal_marks": 30, "end_marks": 40},
                                    {"student": self.other.id, "internal_marks": 41, "end_marks": 40}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Internal 41 is out of range", str(r.json()["errors"]))
        self.assertFalse(ResultEntry.objects.exists())
        for rec, text in (({"grade": "O"}, "can't be given by hand"), ({"end_marks": 40}, "both the internal"),
                          ({"internal_marks": "x", "end_marks": 1}, "must be a number")):
            r = self.save(self.thermo, [{"student": self.student.id, **rec}])
            self.assertEqual(r.status_code, 400, rec)
            self.assertIn(text, str(r.json()["errors"]))
        self.assertEqual(self.save(self.thermo, [{"student": self.student.id, "marks_obtained": 50}],
                                   user=self.teacher).status_code, 403)

    def test_no_regulation_keeps_the_old_grading(self):
        from core.academics.models import Regulation
        Regulation.objects.all().delete()
        self.save(self.thermo, [{"student": self.student.id, "marks_obtained": 45}])
        e = self.entry(self.thermo)
        self.assertEqual((e.grade, e.is_pass, e.grade_points), ("C", True, None))     # old 40% pass mark
        r = self.save(self.thermo, [{"student": self.student.id, "internal_marks": 20, "end_marks": 30}])
        self.assertIn("need a regulation", str(r.json()["errors"]))


class AttemptTests(CBCSResultsBase):

    def test_re_exam_records_a_new_attempt_and_keeps_internal(self):
        self.save(self.maths, [{"student": self.student.id, "internal_marks": 22, "end_marks": 18}], "Nov/Dec 2025")
        self.publish()
        # same session after publishing: refused
        r = self.save(self.maths, [{"student": self.student.id, "internal_marks": 22, "end_marks": 40}], "Nov/Dec 2025")
        self.assertIn("already published", str(r.json()["errors"]))
        # attempt 2: only the end-sem mark; the regulation keeps the first internal
        r = self.save(self.maths, [{"student": self.student.id, "end_marks": 24}], "Apr/May 2026")
        self.assertEqual(r.json()["new_attempt"], 1, r.content)
        e = self.entry(self.maths)
        self.assertEqual((e.attempt, e.internal_marks, e.end_marks, e.grade), (2, 22, 24, "RA"))
        self.assertEqual(list(ResultAttempt.objects.values_list("attempt", "exam_session", "grade")),
                         [(1, "Nov/Dec 2025", "RA")])
        # the same re-exam session twice: refused
        r = self.save(self.maths, [{"student": self.student.id, "end_marks": 30}], "Nov/Dec 2025")
        self.assertIn("already recorded", str(r.json()["errors"]))
        # attempt 3 passes
        self.save(self.maths, [{"student": self.student.id, "end_marks": 40}], "Nov/Dec 2026")
        e = self.entry(self.maths)
        self.assertEqual((e.attempt, e.is_pass, e.grade), (3, True, "B+"))           # 62
        self.assertEqual(get_arrear_count(self.student), 0)
        # a passed subject can't be written again
        r = self.save(self.maths, [{"student": self.student.id, "end_marks": 55}], "Apr/May 2027")
        self.assertIn("already passed", str(r.json()["errors"]))

    def test_arrear_roster(self):
        self.save(self.maths, [{"student": self.student.id, "internal_marks": 22, "end_marks": 18},
                               {"student": self.other.id, "internal_marks": 30, "end_marks": 40}], "Nov/Dec 2025")
        self.publish()
        self.publish(self.other)
        d = self.c(self.exam).get(f"/api/results/arrear-roster/?subject={self.maths.id}").json()
        self.assertEqual([s["student_roll_no"] for s in d["students"]], ["23ME001"])
        self.assertEqual(d["students"][0]["internal_marks"], 22)
        self.assertEqual(self.c(self.teacher).get(f"/api/results/arrear-roster/?subject={self.maths.id}").status_code, 403)

    def test_entry_rules_for_the_grid(self):
        d = self.c(self.exam).get(f"/api/results/entry-rules/?subject={self.lab.id}&course={self.course.id}"
                                  f"&year=2&semester=3").json()
        rule = d["rules"][str(self.reg.id)]
        self.assertEqual((rule["internal_max"], rule["end_max"], rule["min_end_pct"]), (60, 40, 50.0))
        self.assertEqual(rule["hand_grades"], ["SA", "W"])
        self.assertEqual(d["students"][str(self.student.id)], self.reg.id)


class GpaTests(CBCSResultsBase):

    def setUp(self):
        super().setUp()
        cat_req = [(self.pcc, 12), (CourseCategory.objects.get(code="BSC"), 4)]
        for cat, cr in cat_req:
            CreditRequirement.objects.create(regulation=self.reg, course=self.course, category=cat, credits=cr)
        self.save(self.thermo, [{"student": self.student.id, "internal_marks": 34, "end_marks": 48}], "Nov/Dec 2025")  # A+ 9 x4
        self.save(self.lab, [{"student": self.student.id, "internal_marks": 40, "end_marks": 20}], "Nov/Dec 2025")    # 60 B 6 x2
        self.save(self.maths, [{"student": self.student.id, "internal_marks": 22, "end_marks": 18}], "Nov/Dec 2025")  # RA x3
        self.save(self.env, [{"student": self.student.id, "internal_marks": 30, "end_marks": 30}], "Nov/Dec 2025")    # MC
        self.publish()

    def test_arrears_left_out_until_passed(self):
        self.assertEqual(get_cgpa(self.student), (8.0, None))                     # (36 + 12) / 6
        self.reg.arrears_in_gpa = "zero"
        self.reg.save()
        self.assertEqual(get_cgpa(self.student), (5.33, None))                    # 48 / 9

    def test_withdrawn_is_not_counted_and_not_an_arrear(self):
        SemesterResult.objects.update(is_published=False)
        self.save(self.maths, [{"student": self.student.id, "grade": "W"}], "Nov/Dec 2025")
        self.publish()
        self.assertEqual(get_arrear_count(self.student), 0)
        self.reg.arrears_in_gpa = "zero"
        self.reg.save()
        self.assertEqual(get_cgpa(self.student), (8.0, None))

    def test_credits_page(self):
        d = self.c(self.student).get("/api/results/credits/me/").json()
        self.assertEqual((d["cgpa"], d["credits_earned"], d["credits_required"]), (8.0, 6.0, 16.0))
        sem = d["semesters"][0]
        self.assertEqual((sem["sgpa"], sem["grade_points"], sem["gpa_credits"], sem["has_arrear"]), (8.0, 48.0, 6.0, True))
        self.assertEqual([c["code"] for c in d["categories"]], ["BSC", "PCC"])
        self.assertEqual(next(c for c in d["categories"] if c["code"] == "PCC")["earned"], 6.0)
        self.assertEqual([a["code"] for a in d["arrears"]], ["MA301"])
        env = next(x for x in sem["entries"] if x["code"] == "MC301")
        self.assertEqual((env["counts_for_credit"], env["in_gpa"]), (False, False))
        self.assertEqual(d["degree_class"], "First class")                        # an arrear rules out distinction
        # who may see it
        self.assertEqual(self.c(self.other).get(f"/api/results/credits/{self.student.id}/").status_code, 403)
        self.assertEqual(self.c(self.admin).get(f"/api/results/credits/{self.student.id}/").status_code, 200)
        self.assertEqual(self.c(self.teacher).get(f"/api/results/credits/{self.student.id}/").status_code, 403)
        self.assertEqual(self.c(self.teacher).get("/api/results/credits/me/").status_code, 403)

    def test_unpublished_results_are_hidden_from_the_student(self):
        SemesterResult.objects.update(is_published=False)
        d = self.c(self.student).get("/api/results/credits/me/").json()
        self.assertEqual((d["semesters"], d["cgpa"]), ([], None))
        d = self.c(self.exam).get(f"/api/results/credits/{self.student.id}/").json()
        self.assertEqual(len(d["semesters"]), 1)


class ImportTests(CBCSResultsBase):

    def upload(self, rows, commit=True):
        wb = Workbook()
        ws = wb.active
        ws.append(["Roll number", "Name", "Marks", "Grade", "Result", "Internal", "End-sem", "Grade by hand"])
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "r.xlsx"
        from core.dataio.tests import post_upload    # the waiting /import/ URL was removed
        return post_upload(self.c(self.exam), "results", {
            "file": buf, "mode": "upsert", "teaching_assignment": self.ta.id, "max_marks": 100}, commit)

    def test_import_split_marks_and_hand_grades(self):
        r = self.upload([["23ME001", "", "", "", "", 34, 48, ""], ["23ME002", "", "", "", "", "", "", "SA"]])
        self.assertTrue(r.json()["saved"], r.content)
        self.assertEqual(self.entry(self.thermo).grade, "A+")
        self.assertEqual(self.entry(self.thermo, self.other).grade, "SA")

    def test_import_problems(self):
        r = self.upload([["23ME001", "", 70, "", "", 30, 40, ""], ["23ME002", "", "", "", "", 45, 40, ""]])
        msgs = " | ".join(m for row in r.json()["rows"] for m in row["messages"])
        self.assertIn("either Marks, or Internal and End-sem", msgs)
        self.assertIn("Internal 45 is out of range", msgs)
        self.assertFalse(ResultEntry.objects.exists())
