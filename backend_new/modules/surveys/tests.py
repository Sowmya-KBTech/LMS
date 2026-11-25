"""
WAVE 2 TESTS - surveys.

Run:  python manage.py test modules.surveys -v 2
"""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course
from core.notifications.models import Notification
from core.users.models import Department, PrincipalTerm, User
from modules.surveys.models import Participation, Response, Survey
from modules.surveys.templates import TEMPLATES


class SurveyTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.iqac = mk("iqac1", password="x", role="admin", sub_role="iqac_admin")
        self.fees = mk("fees1", password="x", role="admin", sub_role="accounts_admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.me = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.me
        self.hod.save()
        self.ce = Department.objects.create(name="Civil", code="CE")
        self.t_me = mk("ravi", password="x", role="teacher", department=self.me)
        self.t_ce = mk("meena", password="x", role="teacher", department=self.ce)
        self.mech = Course.objects.create(name="B.E Mech")
        self.civil = Course.objects.create(name="B.E Civil")

        def st(n, dept, course, year, sem):
            return mk(n, password="x", role="student", department=dept, course=course, year=year, semester=sem,
                      first_name=n.title())
        self.s1 = st("asha", self.me, self.mech, 2, 3)
        self.s2 = st("bala", self.me, self.mech, 2, 3)
        self.s3 = st("chitra", self.me, self.mech, 3, 5)
        self.s4 = st("dinesh", self.ce, self.civil, 2, 3)
        self.parent = mk("par1", password="x", role="parent")

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def body(self, **over):
        data = {"title": "Course feedback", "audience": "students", "department": self.me.id,
                "anonymous": True, "questions": [
                    {"kind": "rating", "text": "Clear teaching?", "required": True},
                    {"kind": "choice", "text": "Pace?", "options": ["Slow", "Right", "Fast"], "required": True},
                    {"kind": "multi", "text": "Helpful?", "options": ["Notes", "Labs", "Videos"], "required": False},
                    {"kind": "text", "text": "Comments", "required": False},
                ]}
        data.update(over)
        return data

    def create(self, user=None, **over):
        r = self.c(user or self.hod).post("/api/surveys/manage/", self.body(**over), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def publish(self, sid, user=None):
        return self.c(user or self.hod).post(f"/api/surveys/manage/{sid}/publish/")

    def answer(self, user, sid, answers):
        return self.c(user).post(f"/api/surveys/my/{sid}/submit/", {"answers": answers}, format="json")

    def qids(self, survey):
        return [q["id"] for q in survey["questions"]]

    # ---------------------------------------------------------------- building
    def test_who_can_build(self):
        for u in (self.t_me, self.s1, self.parent, self.fees):
            self.assertEqual(self.c(u).post("/api/surveys/manage/", self.body(), format="json").status_code,
                             403, u.username)
            self.assertEqual(self.c(u).get("/api/surveys/templates/").status_code, 403, u.username)
        for u in (self.admin, self.iqac, self.hod):
            self.create(u)
        PrincipalTerm.objects.create(teacher=self.t_ce, start_date=timezone.localdate())
        self.create(self.t_ce)                                                  # the Principal

    def test_hod_only_own_department(self):
        r = self.c(self.hod).post("/api/surveys/manage/", self.body(department=self.ce.id), format="json")
        self.assertEqual(r.status_code, 400)
        s = self.create(self.hod, department=None)                             # filled in for them
        self.assertEqual(s["department"], self.me.id)
        college = self.create(self.admin, department=None, title="College-wide")
        self.assertIsNone(college["department"])
        mine = [x["id"] for x in self.c(self.hod).get("/api/surveys/manage/").json()]
        self.assertEqual(mine, [s["id"]])                                      # not the college-wide one
        self.assertEqual(self.c(self.hod).get(f"/api/surveys/manage/{college['id']}/results/").status_code, 404)
        self.assertEqual(len(self.c(self.iqac).get("/api/surveys/manage/").json()), 2)

    def test_form_checks(self):
        bad = [
            {"title": ""},
            {"questions": []},
            {"questions": [{"kind": "choice", "text": "Pick", "options": ["Only one"]}]},
            {"questions": [{"kind": "rating", "text": ""}]},
            {"questions": [{"kind": "weird", "text": "x"}]},
            {"year": 7},
            {"start_date": "2026-12-10", "end_date": "2026-12-01"},
            {"audience": "parents"},
        ]
        for over in bad:
            r = self.c(self.admin).post("/api/surveys/manage/", self.body(**over), format="json")
            self.assertEqual(r.status_code, 400, over)

    def test_staff_survey_ignores_class_filters(self):
        s = self.create(self.admin, audience="staff", department=None, course=self.mech.id, year=2)
        self.assertEqual((s["course"], s["year"]), (None, None))

    def test_draft_edit_and_delete_only_while_draft(self):
        s = self.create()
        r = self.c(self.hod).put(f"/api/surveys/manage/{s['id']}/", self.body(title="Renamed"), format="json")
        self.assertEqual(r.json()["title"], "Renamed")
        self.assertEqual(self.publish(s["id"]).status_code, 200)
        self.assertEqual(self.c(self.hod).put(f"/api/surveys/manage/{s['id']}/", self.body(), format="json")
                         .status_code, 400)
        self.assertEqual(self.c(self.hod).delete(f"/api/surveys/manage/{s['id']}/").status_code, 400)
        d = self.create(title="Throw away")
        self.assertEqual(self.c(self.hod).delete(f"/api/surveys/manage/{d['id']}/").status_code, 204)

    # ---------------------------------------------------------------- publishing and audience
    def test_publish_tells_only_the_audience(self):
        s = self.create(year=2)
        r = self.publish(s["id"])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["notified"], 2)                              # asha, bala - not chitra (yr 3)
        told = set(Notification.objects.filter(title="Survey: Course feedback")
                   .values_list("recipient__username", flat=True))
        self.assertEqual(told, {"asha", "bala"})
        self.assertEqual(self.publish(s["id"]).status_code, 400)               # already
        nobody = self.create(year=4)
        self.assertEqual(self.publish(nobody["id"]).status_code, 400)          # no one matches

    def test_my_list_matches_the_audience(self):
        s = self.create(year=2)
        staff = self.create(self.admin, audience="staff", department=self.ce.id, title="Staff only")
        self.publish(s["id"])
        self.publish(staff["id"], self.admin)
        self.assertEqual([x["id"] for x in self.c(self.s1).get("/api/surveys/my/").json()], [s["id"]])
        self.assertEqual(self.c(self.s3).get("/api/surveys/my/").json(), [])   # year 3
        self.assertEqual(self.c(self.s4).get("/api/surveys/my/").json(), [])   # civil
        self.assertEqual([x["id"] for x in self.c(self.t_ce).get("/api/surveys/my/").json()], [staff["id"]])
        self.assertEqual(self.c(self.t_me).get("/api/surveys/my/").json(), [])
        self.assertEqual(self.c(self.s3).get(f"/api/surveys/my/{s['id']}/").status_code, 404)
        draft = self.create(title="Draft")
        self.assertEqual(self.c(self.s1).get(f"/api/surveys/my/{draft['id']}/").status_code, 404)

    def test_dates(self):
        today = timezone.localdate()
        later = self.create(start_date=(today + datetime.timedelta(days=3)).isoformat())
        self.publish(later["id"])
        self.assertEqual(self.c(self.s1).get("/api/surveys/my/").json(), [])   # not started
        q = self.qids(later)
        self.assertEqual(self.answer(self.s1, later["id"], {q[0]: 4, q[1]: "Right"}).status_code, 400)
        past = self.create(start_date=(today - datetime.timedelta(days=9)).isoformat(),
                           end_date=(today - datetime.timedelta(days=1)).isoformat())
        self.assertEqual(self.publish(past["id"]).status_code, 400)            # already over

    # ---------------------------------------------------------------- answering
    def test_answer_rules(self):
        s = self.create()
        self.publish(s["id"])
        r_, c_, m_, t_ = self.qids(s)
        self.assertEqual(self.answer(self.s1, s["id"], {r_: 4}).status_code, 400)               # required choice
        self.assertEqual(self.answer(self.s1, s["id"], {r_: 9, c_: "Right"}).status_code, 400)   # 1..5
        self.assertEqual(self.answer(self.s1, s["id"], {r_: 4, c_: "Maybe"}).status_code, 400)   # not an option
        self.assertEqual(self.answer(self.s1, s["id"], {r_: 4, c_: "Right", m_: "Notes"}).status_code, 400)
        ok = self.answer(self.s1, s["id"], {r_: 4, c_: "Right", m_: ["Notes", "Labs"], t_: "Good"})
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(self.answer(self.s1, s["id"], {r_: 5, c_: "Fast"}).status_code, 400)    # twice
        self.assertTrue(self.c(self.s1).get(f"/api/surveys/my/{s['id']}/").json()["answered"])
        self.assertEqual(self.answer(self.s4, s["id"], {r_: 5, c_: "Fast"}).status_code, 404)    # not for them
        self.c(self.hod).post(f"/api/surveys/manage/{s['id']}/close/")
        self.assertEqual(self.answer(self.s2, s["id"], {r_: 5, c_: "Fast"}).status_code, 400)    # closed
        mine = self.c(self.s1).get("/api/surveys/my/").json()
        self.assertEqual([(x["id"], x["answered"]) for x in mine], [(s["id"], True)])           # still listed

    def test_anonymous_answers_have_no_name(self):
        s = self.create()
        self.publish(s["id"])
        r_, c_, m_, t_ = self.qids(s)
        self.answer(self.s1, s["id"], {r_: 5, c_: "Right", t_: "Loved the labs"})
        resp = Response.objects.get(survey_id=s["id"])
        self.assertIsNone(resp.respondent_id)
        self.assertTrue(Participation.objects.filter(survey_id=s["id"], user=self.s1).exists())
        res = self.c(self.hod).get(f"/api/surveys/manage/{s['id']}/results/").json()
        text_q = next(q for q in res["questions"] if q["kind"] == "text")
        self.assertEqual(text_q["answers"], [{"text": "Loved the labs", "by": ""}])

        named = self.create(anonymous=False, title="Named")
        self.publish(named["id"])
        q = self.qids(named)
        self.answer(self.s2, named["id"], {q[0]: 3, q[1]: "Fast", q[3]: "More examples"})
        res = self.c(self.hod).get(f"/api/surveys/manage/{named['id']}/results/").json()
        text_q = next(x for x in res["questions"] if x["kind"] == "text")
        self.assertEqual(text_q["answers"], [{"text": "More examples", "by": "Bala"}])

    def test_results(self):
        s = self.create()                                   # ME students: asha, bala (y2), chitra (y3)
        self.publish(s["id"])
        r_, c_, m_, t_ = self.qids(s)
        self.answer(self.s1, s["id"], {r_: 5, c_: "Right", m_: ["Notes", "Labs"]})
        self.answer(self.s2, s["id"], {r_: 2, c_: "Fast", m_: ["Labs"], t_: "Slow down"})
        res = self.c(self.hod).get(f"/api/surveys/manage/{s['id']}/results/").json()
        self.assertEqual((res["eligible"], res["answered"], res["rate"]), (3, 2, 66.7))
        self.assertEqual({g["group"]: (g["eligible"], g["answered"]) for g in res["by_group"]},
                         {"B.E Mech · Year 2": (2, 2), "B.E Mech · Year 3": (1, 0)})
        rating, choice, multi, text = res["questions"]
        self.assertEqual((rating["average"], rating["distribution"]["5"], rating["distribution"]["2"]), (3.5, 1, 1))
        self.assertEqual({x["option"]: x["count"] for x in choice["counts"]}, {"Slow": 0, "Right": 1, "Fast": 1})
        self.assertEqual({x["option"]: x["count"] for x in multi["counts"]}, {"Notes": 1, "Labs": 2, "Videos": 0})
        self.assertEqual(text["count"], 1)
        listed = next(x for x in self.c(self.hod).get("/api/surveys/manage/").json() if x["id"] == s["id"])
        self.assertEqual((listed["answered"], listed["eligible"]), (2, 3))

    def test_templates_are_valid(self):
        for t in TEMPLATES:
            r = self.c(self.admin).post("/api/surveys/manage/", {**t, "template": t["key"], "department": None},
                                        format="json")
            self.assertEqual(r.status_code, 201, (t["key"], r.content))
            self.assertEqual(len(r.json()["questions"]), len(t["questions"]))
