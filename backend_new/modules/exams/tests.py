"""
Exams module checks: revaluation rules (meeting point 4) and the single,
shared Import & Export path for results and IA marks (meeting point 2).

Run:  python manage.py test modules.exams -v 2
"""
import io

from django.test import TestCase
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.exams.models import ResultEntry, RevaluationWindow, SemesterResult


class ExamsTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mechanical")
        self.y2 = Year.objects.create(course=self.course, year_number=2)

        self.sub3 = Subject.objects.create(name="Thermodynamics", code="ME301", year=self.y2, semester=3)
        self.sub4 = Subject.objects.create(name="Fluid Mechanics", code="ME401", year=self.y2, semester=4)

        self.admin = User.objects.create_user(username="admin1", password="x", role="admin", sub_role="super_admin")
        self.teacher = User.objects.create_user(username="t1", password="x", role="teacher", department=self.dept)
        self.student = User.objects.create_user(
            username="s1", password="x", role="student", department=self.dept,
            course=self.course, year=2, semester=4, first_name="Aarthi",
        )
        self.ta3 = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y2, subject=self.sub3)
        self.ta4 = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y2, subject=self.sub4)
        for ta in (self.ta3, self.ta4):
            Enrollment.objects.create(student=self.student, teaching_assignment=ta)

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def publish(self, semester, subject, marks=40):
        res = SemesterResult.objects.create(student=self.student, semester=semester, is_published=True)
        return ResultEntry.objects.create(result=res, subject=subject, max_marks=100, marks_obtained=marks)


# ======================================================================
#  REVALUATION (meeting point 4)
# ======================================================================
class RevaluationTests(ExamsTestBase):

    def test_latest_endpoint_exists_and_returns_latest_semester(self):
        """The student screen calls /api/revaluations/latest/ - it was 404."""
        self.publish(3, self.sub3)
        self.publish(4, self.sub4)
        r = self.as_user(self.student).get("/api/revaluations/latest/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["semester"], 4)
        self.assertFalse(r.data["window"]["is_open"])

    def test_latest_with_nothing_published(self):
        r = self.as_user(self.student).get("/api/revaluations/latest/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["semester"])

    def test_student_cannot_apply_for_old_semester(self):
        """Sem 3 window open by mistake still can't be used once Sem 4 is out."""
        old = self.publish(3, self.sub3)
        self.publish(4, self.sub4)
        RevaluationWindow.objects.create(semester=3, is_open=True, fee_amount=500)
        r = self.as_user(self.student).post("/api/revaluations/apply/", {"result_entry": old.id}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("latest examination (Semester 4)", r.data["detail"])

    def test_student_can_apply_for_latest_semester(self):
        self.publish(3, self.sub3)
        latest = self.publish(4, self.sub4)
        RevaluationWindow.objects.create(semester=4, is_open=True, fee_amount=500)
        r = self.as_user(self.student).post("/api/revaluations/apply/", {"result_entry": latest.id}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)

    def test_admin_cannot_open_semester_with_no_published_results(self):
        r = self.as_user(self.admin).post("/api/revaluation-window/",
                                          {"semester": 5, "is_open": True, "fee_amount": 500}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("No Semester 5 results have been published", r.data["detail"])
        self.assertFalse(RevaluationWindow.objects.filter(semester=5, is_open=True).exists())

    def test_admin_cannot_open_older_semester(self):
        self.publish(3, self.sub3)
        self.publish(4, self.sub4)
        r = self.as_user(self.admin).post("/api/revaluation-window/",
                                          {"semester": 3, "is_open": True, "fee_amount": 500}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not the latest examination", r.data["detail"])

    def test_admin_can_open_latest_and_close_any(self):
        self.publish(4, self.sub4)
        c = self.as_user(self.admin)
        r = c.post("/api/revaluation-window/", {"semester": 4, "is_open": True, "fee_amount": 500}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["is_open"])
        # closing never needs validation
        r = c.post("/api/revaluation-window/", {"semester": 3, "is_open": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_admin_rejects_bad_input(self):
        self.publish(4, self.sub4)
        c = self.as_user(self.admin)
        self.assertEqual(c.post("/api/revaluation-window/", {"semester": 9, "is_open": True}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/revaluation-window/", {"semester": 4, "is_open": True, "fee_amount": -1}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/revaluation-window/", {"semester": 4, "is_open": True, "fee_amount": "abc"}, format="json").status_code, 400)

    def test_status_tells_admin_whether_semester_can_open(self):
        self.publish(3, self.sub3)
        self.publish(4, self.sub4)
        c = self.as_user(self.admin)
        self.assertFalse(c.get("/api/revaluation-window/status/?semester=3").data["can_open"])
        r = c.get("/api/revaluation-window/status/?semester=4").data
        self.assertTrue(r["can_open"])
        self.assertEqual(r["eligible_students"], 1)
        # students don't get the admin-only fields
        self.assertNotIn("can_open", self.as_user(self.student).get("/api/revaluation-window/status/?semester=4").data)

    def test_inactive_students_do_not_count(self):
        self.publish(4, self.sub4)
        self.student.is_active = False
        self.student.save()
        r = self.as_user(self.admin).get("/api/revaluation-window/status/?semester=4").data
        self.assertEqual(r["eligible_students"], 0)


# ======================================================================
#  IMPORT / EXPORT (meeting point 2): one path only - the shared engine
# ======================================================================
class ImportExportTests(ExamsTestBase):

    def test_old_duplicate_csv_endpoints_are_gone(self):
        c = self.as_user(self.admin)
        for url in ("/api/results-template/", "/api/results-import/", "/api/ia-template/", "/api/ia-import/"):
            self.assertEqual(c.get(url).status_code, 404, url)

    def test_results_and_ia_registered_in_shared_engine(self):
        data = self.as_user(self.admin).get("/api/dataio/").data
        items = data.get("importers", data) if isinstance(data, dict) else data
        keys = {i["key"] for i in items}
        self.assertTrue({"results", "ia_marks"} <= keys, keys)

    def _xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "results.xlsx"
        return buf

    def test_results_template_import_export_roundtrip(self):
        c = self.as_user(self.admin)
        params = {"teaching_assignment": self.ta4.id, "max_marks": 100}

        t = c.get("/api/dataio/results/template/", params)
        self.assertEqual(t.status_code, 200, getattr(t, "data", t.content[:300]))
        header = [cell.value for cell in next(load_workbook(io.BytesIO(t.content)).active.iter_rows(max_row=1))]
        roll_col = header[0]

        self.student.refresh_from_db()
        upload = self._xlsx([header, [self.student.roll_number, "Aarthi", 78, "", ""]])
        from core.dataio.tests import post_upload    # the waiting /import/ URL was removed
        imp = post_upload(c, "results", {**params, "file": upload, "mode": "upsert"}, commit=True)
        self.assertEqual(imp.status_code, 200, getattr(imp, "data", imp.content[:500]))

        entry = ResultEntry.objects.get(result__student=self.student, subject=self.sub4)
        self.assertEqual(entry.marks_obtained, 78)

        e = c.get("/api/dataio/results/export/", params)
        self.assertEqual(e.status_code, 200)
        rows = list(load_workbook(io.BytesIO(e.content)).active.iter_rows(values_only=True))
        self.assertTrue(any(78 in r or "78" in r or 78.0 in r for r in rows), rows)
        self.assertEqual(rows[0][0].rstrip(" *"), roll_col.rstrip(" *"))

    def test_student_cannot_use_results_import(self):
        r = self.as_user(self.student).get("/api/dataio/results/template/",
                                           {"teaching_assignment": self.ta4.id})
        self.assertIn(r.status_code, (403, 404))


# ======================================================================
#  CO-PO PART B - IA question paper, marks by question, CO attainment
# ======================================================================
class CoMarksBase(ExamsTestBase):
    def setUp(self):
        super().setUp()
        from modules.teachingplan.models import CourseOutcome
        self.s2 = User.objects.create_user(username="s2", password="x", role="student", course=self.course, year=2,
                                           semester=3)
        self.s3 = User.objects.create_user(username="s3", password="x", role="student", course=self.course, year=2,
                                           semester=3)
        for s in (self.s2, self.s3):
            Enrollment.objects.create(student=s, teaching_assignment=self.ta3)
        self.co1 = CourseOutcome.objects.create(subject=self.sub3, code="CO1", text="First law", order=1)
        self.co2 = CourseOutcome.objects.create(subject=self.sub3, code="CO2", text="Entropy", order=2)
        self.q = f"?teaching_assignment={self.ta3.id}&number=1"

    def paper(self, questions, user=None):
        return self.as_user(user or self.teacher).put(f"/api/ia-papers/{self.q}", {"questions": questions},
                                                      format="json")

    def standard_paper(self):
        r = self.paper([{"label": "Q1", "max_marks": 2, "outcome": self.co1.id, "bloom": "remember"},
                        {"label": "Q2", "max_marks": 2, "outcome": self.co2.id},
                        {"label": "Q3", "max_marks": 16, "outcome": self.co1.id, "bloom": "apply"}])
        self.assertEqual(r.status_code, 200, r.content)
        return {q["label"]: q["id"] for q in r.json()["questions"]}

    def marks(self, records):
        return self.as_user(self.teacher).post("/api/ia-question-marks/", {
            "teaching_assignment": self.ta3.id, "number": 1, "records": records}, format="json")


class CoMarksTests(CoMarksBase):
    def test_paper_rules(self):
        q = self.standard_paper()
        from modules.exams.models import InternalAssessment
        self.assertEqual(InternalAssessment.objects.get(teaching_assignment=self.ta3, number=1).max_marks, 20)
        other = User.objects.create_user(username="t2", password="x", role="teacher")
        self.assertEqual(self.paper([], user=other).status_code, 403)
        from modules.teachingplan.models import CourseOutcome
        alien = CourseOutcome.objects.create(subject=self.sub4, code="CO1", text="x")
        self.assertEqual(self.paper([{"label": "Q1", "max_marks": 2, "outcome": alien.id}]).status_code, 400)
        self.assertEqual(self.paper([{"label": "Q1", "max_marks": 60}, {"label": "Q2", "max_marks": 50}]).status_code, 400)
        self.assertEqual(self.paper([{"label": "Q1", "max_marks": 2}, {"label": "q1", "max_marks": 2}]).status_code, 400)
        self.assertEqual(self.paper([{"label": "Q1", "max_marks": 1.25}]).status_code, 400)
        # rename and reorder keep the same questions
        r = self.paper([{"id": q["Q3"], "label": "Q1", "max_marks": 16, "outcome": self.co1.id},
                        {"id": q["Q1"], "label": "Q3", "max_marks": 2, "outcome": self.co1.id},
                        {"id": q["Q2"], "label": "Q2", "max_marks": 2, "outcome": self.co2.id}])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([x["label"] for x in r.json()["questions"]], ["Q1", "Q3", "Q2"])
        self.assertEqual(sorted(x["id"] for x in r.json()["questions"]), sorted(q.values()))

    def test_marks_by_question_make_the_total(self):
        q = self.standard_paper()
        bad = self.marks([{"student": self.student.id, "marks": {str(q["Q1"]): 3}},
                          {"student": self.s2.id, "marks": {str(q["Q1"]): 1}}])
        self.assertEqual(bad.status_code, 400)
        from modules.exams.models import IAMark
        self.assertFalse(IAMark.objects.exists())                            # nothing saved
        r = self.marks([{"student": self.student.id, "marks": {str(q["Q1"]): 2, str(q["Q3"]): 14}},
                        {"student": self.s2.id, "marks": {str(q["Q1"]): 1, str(q["Q2"]): 2, str(q["Q3"]): 8.5}},
                        {"student": self.s3.id, "absent": True, "marks": {str(q["Q1"]): 2}}])
        self.assertEqual(r.status_code, 200, r.content)
        totals = {m.student_id: (m.marks_obtained, m.is_absent) for m in IAMark.objects.all()}
        self.assertEqual(totals, {self.student.id: (16, False), self.s2.id: (11.5, False), self.s3.id: (None, True)})
        # totals can't be typed any more, and the Excel import of totals is refused
        r = self.as_user(self.teacher).post("/api/ia-marks/save_marks/", {
            "teaching_assignment": self.ta3.id, "number": 1, "max_marks": 20,
            "records": [{"student": self.s2.id, "marks_obtained": 5}]}, format="json")
        self.assertEqual(r.status_code, 400)
        # a question with marks can't be removed or go below the highest mark
        self.assertEqual(self.paper([{"id": q["Q1"], "label": "Q1", "max_marks": 2}]).status_code, 400)
        self.assertEqual(self.paper([{"id": q["Q1"], "label": "Q1", "max_marks": 2},
                                     {"id": q["Q2"], "label": "Q2", "max_marks": 2},
                                     {"id": q["Q3"], "label": "Q3", "max_marks": 12}]).status_code, 400)
        # locked = read-only
        from modules.exams.models import InternalAssessment
        InternalAssessment.objects.filter(teaching_assignment=self.ta3).update(is_locked=True)
        self.assertEqual(self.marks([{"student": self.s2.id, "marks": {}}]).status_code, 400)

    def test_co_attainment(self):
        q = self.standard_paper()
        self.marks([{"student": self.student.id, "marks": {str(q["Q1"]): 2, str(q["Q2"]): 2, str(q["Q3"]): 14}},
                    {"student": self.s2.id, "marks": {str(q["Q1"]): 1, str(q["Q2"]): 2, str(q["Q3"]): 8}},
                    {"student": self.s3.id, "absent": True}])
        url = f"/api/co-attainment/{self.ta3.id}/"
        d = self.as_user(self.teacher).get(url).json()
        co1, co2 = d["cos"]
        # CO1 out of 18: 16 reached 60%, 9 and absent did not -> 33.3% -> level 0
        self.assertEqual((co1["internal"]["pct"], co1["internal"]["level"]), (33.3, 0))
        # CO2 out of 2: two of three -> 66.7% -> level 2
        self.assertEqual((co2["internal"]["pct"], co2["internal"]["level"]), (66.7, 2))
        self.assertIsNone(co1["end"])
        self.assertEqual((co1["direct"], co2["direct"]), (0.0, 2.0))
        # end-semester: 70 and 65 reach 60, 40 doesn't -> 66.7% -> level 2 for every CO
        for s, m in ((self.student, 70), (self.s2, 65), (self.s3, 40)):
            res = SemesterResult.objects.create(student=s, semester=3, is_published=True)
            ResultEntry.objects.create(result=res, subject=self.sub3, max_marks=100, marks_obtained=m)
        d = self.as_user(self.teacher).get(url).json()
        co1, co2 = d["cos"]
        self.assertEqual(co1["end"]["level"], 2)
        self.assertEqual((co1["direct"], co1["attained"]), (1.4, False))      # 0 x 30% + 2 x 70%
        self.assertEqual((co2["direct"], co2["attained"]), (2.0, True))
        self.assertEqual([s["name"] for s in d["sources"]], ["IA 1"])
        # the action plan
        r = self.as_user(self.teacher).put(f"{url}plan/", {"outcome": self.co1.id, "text": "Extra tutorials"},
                                           format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.as_user(self.teacher).get(url).json()["cos"][0]["plan"], "Extra tutorials")
        # the HOD can look; a student can't
        hod = User.objects.create_user(username="hod1", password="x", role="teacher", department=self.dept)
        self.dept.hod = hod
        self.dept.save()
        self.assertEqual(self.as_user(hod).get(url).status_code, 200)
        self.assertEqual(self.as_user(hod).put(f"{url}plan/", {"outcome": self.co1.id, "text": "x"},
                                               format="json").status_code, 403)
        self.assertEqual(self.as_user(self.s2).get(url).status_code, 403)


# ======================================================================
#  CO-PO PART C - course exit survey, PO / PSO attainment, NBA Excel
# ======================================================================
class PoAttainmentTests(CoMarksBase):
    def setUp(self):
        super().setUp()
        q = self.standard_paper()
        self.marks([{"student": self.student.id, "marks": {str(q["Q1"]): 2, str(q["Q2"]): 2, str(q["Q3"]): 14}},
                    {"student": self.s2.id, "marks": {str(q["Q1"]): 1, str(q["Q2"]): 2, str(q["Q3"]): 8}},
                    {"student": self.s3.id, "absent": True}])
        for s, m in ((self.student, 70), (self.s2, 65), (self.s3, 40)):
            res = SemesterResult.objects.create(student=s, semester=3, is_published=True)
            ResultEntry.objects.create(result=res, subject=self.sub3, max_marks=100, marks_obtained=m)
        self.url = f"/api/co-attainment/{self.ta3.id}/"

    def answer(self, student, survey_id, co1, co2):
        from modules.surveys.models import Question
        qs = {q.outcome_id: q.id for q in Question.objects.filter(survey_id=survey_id, outcome__isnull=False)}
        return self.as_user(student).post(f"/api/surveys/my/{survey_id}/submit/", {
            "answers": {str(qs[self.co1.id]): co1, str(qs[self.co2.id]): co2}}, format="json")

    def test_exit_survey_joins_the_final(self):
        self.assertEqual(self.as_user(self.s2).post(f"{self.url}survey/").status_code, 403)
        r = self.as_user(self.teacher).post(f"{self.url}survey/")
        self.assertEqual(r.status_code, 201, r.content)
        sid = r.json()["id"]
        self.assertEqual(self.as_user(self.teacher).post(f"{self.url}survey/").status_code, 400)   # once
        # only the class's students see it
        outsider = User.objects.create_user(username="s9", password="x", role="student", course=self.course,
                                            year=2, semester=3)
        self.assertEqual([x["id"] for x in self.as_user(self.s2).get("/api/surveys/my/").json()], [sid])
        self.assertEqual(self.as_user(outsider).get("/api/surveys/my/").json(), [])
        # one answer of three = 33% < 50%: not counted yet
        self.assertEqual(self.answer(self.student, sid, 5, 5).status_code, 201)
        d = self.as_user(self.teacher).get(self.url).json()
        self.assertFalse(d["survey"]["counted"])
        self.assertEqual(d["cos"][0]["final"], d["cos"][0]["direct"])
        # two of three = 67%: counted. Rating 5 of 5 = level 3; final = 80% direct + 20% survey
        self.answer(self.s2, sid, 5, 5)
        d = self.as_user(self.teacher).get(self.url).json()
        self.assertTrue(d["survey"]["counted"])
        co1, co2 = d["cos"]
        self.assertEqual((co1["survey"], co1["final"]), (3.0, 1.72))           # 1.4 x 0.8 + 3 x 0.2
        self.assertEqual((co2["final"], co2["attained"]), (2.2, True))

    def test_po_attainment_and_export(self):
        from modules.teachingplan.models import COPOMap, ProgramOutcome
        po1 = ProgramOutcome.objects.create(code="PO1", text="Engineering knowledge", order=1)
        po2 = ProgramOutcome.objects.create(code="PO2", text="Problem analysis", order=2)
        COPOMap.objects.create(outcome=self.co1, program_outcome=po1, strength=3)
        COPOMap.objects.create(outcome=self.co2, program_outcome=po1, strength=1)
        COPOMap.objects.create(outcome=self.co2, program_outcome=po2, strength=2)
        d = self.as_user(self.teacher).get(f"/api/po-attainment/?course={self.course.id}").json()
        overall = {o["code"]: (o["value"], o["attained"]) for o in d["overall"]}
        # finals CO1 1.4, CO2 2.0 -> PO1 = (1.4 x 3 + 2.0 x 1) / 4 = 1.55, PO2 = 2.0
        self.assertEqual(overall, {"PO1": (1.55, False), "PO2": (2.0, True)})
        self.assertEqual([x["subject"] for x in d["subjects"]], ["ME301 Thermodynamics"])
        self.assertEqual(d["left_out"], [{"subject": "ME401 Fluid Mechanics", "why": "No CO–PO mapping"}])
        self.assertEqual((d["cos_below"], d["cos_total"]), (1, 2))
        self.assertEqual(self.as_user(self.s2).get(f"/api/po-attainment/?course={self.course.id}").status_code, 403)
        # a batch with nobody in it: nothing
        d = self.as_user(self.teacher).get(f"/api/po-attainment/?course={self.course.id}&batch=1999").json()
        self.assertEqual(d["subjects"], [])
        # the Excel file
        r = self.as_user(self.teacher).get(f"/api/po-attainment/export/?course={self.course.id}")
        self.assertEqual(r.status_code, 200)
        wb = load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["CO attainment", "CO-PO mapping", "PO attainment"])
        last = list(wb["PO attainment"].iter_rows(values_only=True))
        self.assertEqual((last[-2][0], last[-2][2], last[-2][3]), ("Programme", 1.55, 2))
