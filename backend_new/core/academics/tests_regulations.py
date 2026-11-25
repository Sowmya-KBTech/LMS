"""
WAVE 3 PART 1A TESTS - CBCS: regulations, categories, credit requirements.

Run:  python manage.py test core.academics.tests_regulations -v 2
"""
import copy
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.academics import regulations as R
from core.academics.models import (Course, CourseCategory, CreditRequirement, Regulation, RegulationBatch, Subject,
                                   Year)
from core.users.models import User


class CBCSBase(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.exam = mk("exam1", password="x", role="admin", sub_role="exam_admin")
        self.acad = mk("acad1", password="x", role="admin", sub_role="academic_admin")
        self.fees = mk("fees1", password="x", role="admin", sub_role="accounts_admin")
        self.teacher = mk("ravi", password="x", role="teacher")
        self.student = mk("asha", password="x", role="student", batch_year=2023)
        self.course = Course.objects.create(name="B.E Mech")
        self.y2 = Year.objects.create(course=self.course, year_number=2)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def create(self, name="R2021", start_from="template", user=None, **extra):
        return self.c(user or self.admin).post("/api/regulations/", {"name": name, "start_from": start_from, **extra},
                                               format="json")

    def rules_of(self, reg_id):
        d = self.c(self.admin).get(f"/api/regulations/{reg_id}/").json()
        return {k: d[k] for k in ("pass_rules", "grades", "classes", "arrears_in_gpa", "reattempt_internal")}


class RegulationTests(CBCSBase):

    def test_template_and_default(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertTrue(d["is_default"])                                          # the first one
        self.assertEqual([g["code"] for g in d["grades"]], ["O", "A+", "A", "B+", "B", "C", "RA", "SA", "W"])
        o, a_plus = d["grades"][0], d["grades"][1]
        self.assertEqual((o["min_mark"], o["max_mark"], a_plus["max_mark"]), (91.0, 100.0, 90.0))
        self.assertEqual(d["grades"][6]["outcome"], "fail")
        self.assertEqual([p["kind"] for p in d["pass_rules"]], ["theory", "practical", "project"])
        second = self.create("R2025", "blank").json()
        self.assertFalse(second["is_default"])
        self.assertEqual(second["grades"], [])
        # make the second the default: only one default at a time
        self.c(self.admin).post(f"/api/regulations/{second['id']}/default/")
        self.assertEqual(list(Regulation.objects.filter(is_default=True).values_list("name", flat=True)), ["R2025"])

    def test_copy_takes_rules_and_credit_requirements(self):
        base = Regulation.objects.get(id=self.create().json()["id"])
        cat = CourseCategory.objects.create(code="PCC", name="Professional core")
        CreditRequirement.objects.create(regulation=base, course=self.course, category=cat, credits=59)
        r = self.create("R2025", "copy", copy_from=base.id)
        self.assertEqual(r.status_code, 201, r.content)
        new = Regulation.objects.get(id=r.json()["id"])
        self.assertEqual(new.grades.count(), 9)
        self.assertEqual(new.requirements.get().credits, Decimal("59"))
        self.assertEqual(self.create("r2021").status_code, 400)                   # name taken (any case)

    def test_who_may_change(self):
        self.assertEqual(self.create(user=self.exam).status_code, 201)            # exam admin may
        rid = Regulation.objects.get().id
        for u in (self.fees, self.teacher, self.student):
            self.assertEqual(self.create("R9", user=u).status_code, 403, u.username)
            self.assertEqual(self.c(u).put(f"/api/regulations/{rid}/", {}, format="json").status_code, 403)
        self.assertEqual(self.c(self.teacher).get(f"/api/regulations/{rid}/").status_code, 200)   # staff read
        self.assertEqual(self.c(self.student).get("/api/regulations/").status_code, 403)

    def test_save_rules_and_checks(self):
        rid = self.create().json()["id"]
        good = self.rules_of(rid)
        good["pass_rules"][0]["min_end_pct"] = 40
        good["arrears_in_gpa"] = "zero"
        r = self.c(self.admin).put(f"/api/regulations/{rid}/", good, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["pass_rules"][0]["min_end_pct"], r.json()["arrears_in_gpa"]), (40.0, "zero"))

        def refused(change, text):
            data = copy.deepcopy(good)
            change(data)
            res = self.c(self.admin).put(f"/api/regulations/{rid}/", data, format="json")
            self.assertEqual(res.status_code, 400, text)
            self.assertIn(text, res.json()["detail"])

        refused(lambda d: d["grades"].append(dict(d["grades"][0])), "listed twice")
        refused(lambda d: d["grades"][6].update(outcome="pass", min_mark=40, points=4), "exactly one grade")
        refused(lambda d: d["grades"][1].update(min_mark=91), "same mark")
        refused(lambda d: d["grades"][5].update(min_mark=55), "Make it start at 50 or lower")   # pass at 50 has no grade
        refused(lambda d: d["grades"][0].update(points=8.5), "fewer grade points")
        refused(lambda d: d["pass_rules"].pop(), "theory, practical and project")
        refused(lambda d: d["pass_rules"][1].update(internal_max=0, end_max=0), "cannot both be 0")
        refused(lambda d: d["pass_rules"][0].update(min_total_pct=120), "between 0 and 100")
        refused(lambda d: d["classes"][0].update(min_cgpa=11), "between 0 and 10")
        refused(lambda d: d.update(arrears_in_gpa="maybe"), "one of the options")
        # nothing half-saved by a refused change
        self.assertEqual(Regulation.objects.get().pass_rules.get(kind="theory").min_end_pct, Decimal("40"))

    def test_batches_and_who_follows_what(self):
        r21 = Regulation.objects.get(id=self.create().json()["id"])
        r25 = Regulation.objects.get(id=self.create("R2025").json()["id"])
        self.assertEqual(R.regulation_for_student(self.student), r21)               # no batch row -> default
        self.c(self.admin).post(f"/api/regulations/{r25.id}/batches/", {"batch_year": 2023}, format="json")
        self.assertEqual(R.regulation_for_student(self.student), r25)
        self.c(self.admin).post(f"/api/regulations/{r21.id}/batches/", {"batch_year": 2023}, format="json")
        self.assertEqual(RegulationBatch.objects.get(batch_year=2023).regulation, r21)   # moved, not doubled
        listing = self.c(self.admin).get("/api/regulations/").json()
        row = next(x for x in listing["regulations"] if x["name"] == "R2021")
        self.assertEqual((row["batches"], row["students"]), ([2023], 1))
        bad = self.c(self.admin).post(f"/api/regulations/{r21.id}/batches/", {"batch_year": "abc"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_delete_rules(self):
        r21 = self.create().json()["id"]
        r25 = self.create("R2025").json()["id"]
        self.assertEqual(self.c(self.admin).delete(f"/api/regulations/{r21}/").status_code, 400)   # default
        Subject.objects.create(name="Thermo", year=self.y2, semester=3, regulation_id=r25)
        self.assertIn("Subjects belong", self.c(self.admin).delete(f"/api/regulations/{r25}/").json()["detail"])
        Subject.objects.all().delete()
        self.assertEqual(self.c(self.admin).delete(f"/api/regulations/{r25}/").status_code, 204)


class CurriculumTests(CBCSBase):

    def setUp(self):
        super().setUp()
        self.reg = Regulation.objects.get(id=self.create().json()["id"])
        self.c(self.admin).post("/api/course-categories/template/")
        self.pcc = CourseCategory.objects.get(code="PCC")
        self.mc = CourseCategory.objects.get(code="MC")

    def subject(self, name, credits, cat, sem=3, **kw):
        return Subject.objects.create(name=name, year=self.y2, semester=sem, credits=credits, category=cat, **kw)

    def test_template_categories_once(self):
        self.assertEqual(CourseCategory.objects.count(), 8)
        again = self.c(self.admin).post("/api/course-categories/template/").json()
        self.assertEqual(again["added"], 0)
        self.assertFalse(self.mc.carries_credit)

    def test_credits_required_against_subject_list(self):
        self.subject("Thermo", Decimal("4"), self.pcc)
        self.subject("Fluids lab", Decimal("1.5"), self.pcc)
        self.subject("Environmental Science", 0, self.mc)
        self.subject("Untagged", 3, None, sem=4)
        r = self.c(self.admin).put("/api/curriculum/requirements/", {
            "course": self.course.id, "regulation": self.reg.id,
            "items": [{"category": self.pcc.id, "credits": 7}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        pcc = next(x for x in d["categories"] if x["code"] == "PCC")
        self.assertEqual((pcc["required"], pcc["have"], pcc["check"], pcc["difference"]), (7.0, 5.5, "short", -1.5))
        self.assertEqual(next(x for x in d["categories"] if x["code"] == "MC")["check"], "no_credit")
        self.assertEqual((d["total_required"], d["total_have"], d["no_category"]), (7.0, 8.5, 1))
        self.assertEqual([s["semester"] for s in d["semesters"]], [3, 4])
        self.assertEqual(d["semesters"][0]["credits"], 5.5)

    def test_subject_of_another_regulation_is_not_counted(self):
        other = Regulation.objects.get(id=self.create("R2017", "copy", copy_from=self.reg.id).json()["id"])
        self.subject("Old thermo", 4, self.pcc, regulation=other)
        self.subject("Thermo", 4, self.pcc)                          # no regulation -> the default (R2021)
        d = self.c(self.teacher).get(f"/api/curriculum/?course={self.course.id}&regulation={self.reg.id}").json()
        self.assertEqual([s["name"] for s in d["semesters"][0]["subjects"]], ["Thermo"])
        self.assertFalse(d["can_edit"])                              # staff may read only
        d = self.c(self.admin).get(f"/api/curriculum/?course={self.course.id}&regulation={other.id}").json()
        self.assertEqual([s["name"] for s in d["semesters"][0]["subjects"]], ["Old thermo"])

    def test_requirement_checks_and_permissions(self):
        url = "/api/curriculum/requirements/"
        body = {"course": self.course.id, "regulation": self.reg.id, "items": [{"category": self.pcc.id, "credits": 2.3}]}
        self.assertEqual(self.c(self.admin).put(url, body, format="json").status_code, 400)       # not whole / half
        body["items"][0]["credits"] = 3
        self.assertEqual(self.c(self.exam).put(url, body, format="json").status_code, 403)        # exam admin: no
        self.assertEqual(self.c(self.acad).put(url, body, format="json").status_code, 200)        # academic admin
        self.assertEqual(self.c(self.student).get(f"/api/curriculum/?course={self.course.id}").status_code, 403)

    def test_subject_takes_cbcs_fields(self):
        s = self.subject("Thermo", 3, None)
        r = self.c(self.admin).patch(f"/api/subjects/{s.id}/", {
            "credits": 1.5, "category": self.pcc.id, "kind": "practical", "lecture_hours": 0,
            "tutorial_hours": 0, "practical_hours": 3, "regulation": self.reg.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["credits"], r.json()["category_code"], r.json()["regulation_name"]),
                         (1.5, "PCC", "R2021"))
        self.assertEqual(self.c(self.admin).patch(f"/api/subjects/{s.id}/", {"credits": 1.2},
                                                  format="json").status_code, 400)
        self.assertEqual(self.c(self.admin).patch(f"/api/subjects/{s.id}/", {"kind": "lecture"},
                                                  format="json").status_code, 400)

    def test_category_rules(self):
        self.assertEqual(self.c(self.admin).post("/api/course-categories/", {"code": "pcc", "name": "Again"},
                                                 format="json").status_code, 400)
        r = self.c(self.admin).post("/api/course-categories/", {"code": "ihc", "name": "Industry honours"},
                                    format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (201, "IHC"))
        self.subject("Thermo", 3, self.pcc)
        self.assertEqual(self.c(self.admin).delete(f"/api/course-categories/{self.pcc.id}/").status_code, 400)
        self.assertEqual(self.c(self.admin).delete(f"/api/course-categories/{r.json()['id']}/").status_code, 204)
        self.assertEqual(self.c(self.teacher).post("/api/course-categories/", {"code": "X", "name": "Y"},
                                                   format="json").status_code, 403)

    def test_cgpa_works_with_half_credits(self):
        from modules.exams.models import ResultEntry, SemesterResult
        from modules.exams.services import get_cgpa
        a = self.subject("Thermo", 4, self.pcc)
        b = self.subject("Lab", Decimal("1.5"), self.pcc)
        res = SemesterResult.objects.create(student=self.student, semester=3, is_published=True)
        ResultEntry.objects.create(result=res, subject=a, marks_obtained=95, max_marks=100, grade="O", is_pass=True)
        ResultEntry.objects.create(result=res, subject=b, marks_obtained=85, max_marks=100, grade="A+", is_pass=True)
        cgpa, reason = get_cgpa(self.student)
        self.assertIsNone(reason)
        self.assertEqual(cgpa, round((10 * 4 + 9 * 1.5) / 5.5, 2))
