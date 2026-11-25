"""
WAVE 2 TESTS - the Principal.

Run:  python manage.py test core.users.tests_principal -v 2
"""
import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.notifications.models import Notification
from core.users.models import Department, PrincipalTerm, User
from modules.attendance.models import Attendance, ODRequest, StaffLeaveRequest, StudentLeaveRequest
from modules.exams.models import ResultEntry, SemesterResult


class PrincipalTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.fees = mk("fees1", password="x", role="admin", sub_role="accounts_admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.dept
        self.hod.save()
        self.civil = Department.objects.create(name="Civil", code="CE")
        self.t1 = mk("ravi", password="x", role="teacher", department=self.dept, first_name="Ravi")
        self.t2 = mk("meena", password="x", role="teacher", department=self.civil)
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.subj = Subject.objects.create(name="Thermo", code="ME301", year=self.year, semester=3)
        self.ta = TeachingAssignment.objects.create(teacher=self.t1, course=self.course, year=self.year,
                                                    subject=self.subj)

        def student(n):
            return mk(n, password="x", role="student", department=self.dept, course=self.course,
                      year=2, semester=3)
        self.s1, self.s2 = student("asha"), student("bala")

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_principal(self, teacher):
        return self.c(self.admin).post("/api/users/principal/assign/", {"teacher": teacher.id})

    # ---------------------------------------------------------------- assigning
    def test_only_main_admin_assigns(self):
        for u in (self.fees, self.t1, self.hod):
            self.assertEqual(self.c(u).post("/api/users/principal/assign/", {"teacher": self.t1.id}).status_code,
                             403, u.username)
        r = self.make_principal(self.t1)
        self.assertEqual(r.status_code, 201, r.content)
        info = self.c(self.t1).get("/api/users/principal/").json()
        self.assertEqual((info["current"]["name"], info["is_me"], info["can_manage"]), ("Ravi", True, False))
        self.assertNotIn("history", info)
        self.assertTrue(Notification.objects.filter(recipient=self.t1, title="You are now the Principal").exists())

    def test_must_be_an_active_teacher(self):
        self.assertEqual(self.make_principal(self.s1).status_code, 400)
        self.t2.is_active = False
        self.t2.save()
        self.assertEqual(self.make_principal(self.t2).status_code, 400)
        self.assertEqual(self.c(self.admin).post("/api/users/principal/assign/", {"teacher": "x"}).status_code, 400)

    def test_new_principal_ends_the_old_term(self):
        self.make_principal(self.t1)
        self.assertEqual(self.make_principal(self.t1).status_code, 400)              # already
        self.assertEqual(self.make_principal(self.t2).status_code, 201)
        self.assertEqual(PrincipalTerm.objects.filter(is_current=True).count(), 1)
        old = PrincipalTerm.objects.get(teacher=self.t1)
        self.assertEqual((old.is_current, old.end_date, old.ended_by), (False, timezone.localdate(), self.admin))
        info = self.c(self.admin).get("/api/users/principal/").json()
        self.assertEqual([h["teacher_id"] for h in info["history"]], [self.t1.id])
        self.assertEqual(self.c(self.t1).get("/api/users/principal/dashboard/").status_code, 403)

    def test_end_term(self):
        self.assertEqual(self.c(self.admin).post("/api/users/principal/end/").status_code, 400)
        self.make_principal(self.t1)
        self.assertEqual(self.c(self.t1).post("/api/users/principal/end/").status_code, 403)
        self.assertEqual(self.c(self.admin).post("/api/users/principal/end/").status_code, 200)
        self.assertIsNone(self.c(self.admin).get("/api/users/principal/").json()["current"])

    def test_database_allows_one_current_principal(self):
        PrincipalTerm.objects.create(teacher=self.t1, start_date=timezone.localdate())
        with self.assertRaises(IntegrityError), transaction.atomic():
            PrincipalTerm.objects.create(teacher=self.t2, start_date=timezone.localdate())

    # ---------------------------------------------------------------- dashboard
    def test_dashboard_access(self):
        self.assertEqual(self.c(self.t1).get("/api/users/principal/dashboard/").status_code, 403)
        self.assertEqual(self.c(self.fees).get("/api/users/principal/dashboard/").status_code, 403)
        self.assertEqual(self.c(self.hod).get("/api/users/principal/dashboard/").status_code, 403)
        self.make_principal(self.t1)
        self.assertEqual(self.c(self.t1).get("/api/users/principal/dashboard/").status_code, 200)
        self.assertEqual(self.c(self.admin).get("/api/users/principal/dashboard/").status_code, 200)

    def test_dashboard_numbers(self):
        today = timezone.localdate()
        for h, (st1, st2) in enumerate([("present", "absent"), ("duty_leave", "absent"), ("present", "absent")], 1):
            Attendance.objects.create(teaching_assignment=self.ta, student=self.s1, date=today, hour=h, status=st1)
            Attendance.objects.create(teaching_assignment=self.ta, student=self.s2, date=today, hour=h, status=st2)
        ODRequest.objects.create(student=self.s1, from_date=today, to_date=today, reason="symposium",
                                 status="pending", stage="awaiting_hod")
        StudentLeaveRequest.objects.create(student=self.s2, leave_type="sick", from_date=today, to_date=today,
                                           reason="fever", status="pending", stage="awaiting_hod")
        StaffLeaveRequest.objects.create(teacher=self.t1, department=self.dept, leave_type="casual",
                                         from_date=today, to_date=today, reason="family", status="approved")
        StaffLeaveRequest.objects.create(teacher=self.hod, department=self.dept, leave_type="casual",
                                         from_date=today + datetime.timedelta(days=5),
                                         to_date=today + datetime.timedelta(days=6), reason="trip",
                                         status="recorded", backup=self.t1)
        for s, ok in ((self.s1, True), (self.s2, False)):
            sr = SemesterResult.objects.create(student=s, semester=2, is_published=True)
            ResultEntry.objects.create(result=sr, subject=self.subj, max_marks=100, marks_obtained=60 if ok else 20,
                                       grade="B" if ok else "U", is_pass=ok)
        self.make_principal(self.t2)

        data = self.c(self.t2).get("/api/users/principal/dashboard/").json()
        me = next(d for d in data["departments"] if d["code"] == "ME")
        self.assertEqual((me["students"], me["teachers"], me["hod"]), (2, 2, "hodme"))
        self.assertEqual(me["attendance_today"], {"marked": 6, "attended": 3, "percentage": 50.0})
        self.assertEqual(me["low_attendance"], 1)                                # bala 0%, asha 100%
        self.assertEqual(me["pending"], {"od": 1, "student_leave": 1, "staff_leave": 0, "total": 2})
        self.assertEqual(me["results"], {"appeared": 2, "all_clear": 1, "pass_percentage": 50.0})
        self.assertEqual(me["staff_on_leave"], 1)
        self.assertEqual([r["teacher"] for r in data["on_leave_today"]], ["Ravi"])
        self.assertEqual([(r["teacher"], r["is_hod"], r["backup"]) for r in data["hod_leave_upcoming"]],
                         [("hodme", True, "Ravi")])
        ce = next(d for d in data["departments"] if d["code"] == "CE")
        self.assertIsNone(ce["attendance_today"]["percentage"])
        self.assertEqual(data["totals"]["students"], 2)
        self.assertEqual(data["totals"]["pending"], 2)

    # ---------------------------------------------------------------- powers elsewhere
    def test_principal_sees_rank_lists_and_reports(self):
        url = f"/api/reports/rank-list/?course={self.course.id}&year=2&semester=3"
        report = f"/api/reports/progress/{self.s1.id}/"
        self.assertEqual(self.c(self.t2).get(url).status_code, 403)
        self.assertEqual(self.c(self.t2).get(report).status_code, 404)
        self.make_principal(self.t2)
        self.assertEqual(self.c(self.t2).get(url).status_code, 200)
        self.assertEqual(self.c(self.t2).get(report).status_code, 200)
        self.assertEqual(len(self.c(self.t2).get("/api/reports/classes/").json()), 1)

    def test_hod_leave_tells_the_principal(self):
        self.make_principal(self.t2)
        day = timezone.localdate() + datetime.timedelta(days=14)
        while day.weekday() >= 5:
            day += datetime.timedelta(days=1)
        r = self.c(self.hod).post("/api/users/staff-leave/create/", {
            "leave_type": "casual", "from_date": day.isoformat(), "to_date": day.isoformat(),
            "session": "full", "reason": "Family function", "backup": self.t1.id})
        self.assertEqual(r.status_code, 201, r.content)
        # WAVE 2 Part 1b: the Principal now APPROVES an HOD's leave (was: told only)
        self.assertEqual(r.json()["status"], "pending")
        self.assertTrue(Notification.objects.filter(recipient=self.t2, title="HOD leave request from hodme").exists())


# ====================================================================== HRIS PART B
from core.users.models import Appraisal, FacultyParticipation   # noqa: E402


class HrisPartBTests(TestCase):
    """Achievements verified by the HOD (the Principal for an HOD), and the appraisal steps."""

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.dept
        self.hod.save()
        self.civil = Department.objects.create(name="Civil", code="CE")
        self.t1 = mk("ravi", password="x", role="teacher", department=self.dept)
        self.other = mk("anand", password="x", role="teacher", department=self.civil)
        self.principal = mk("sundar", password="x", role="teacher", department=self.civil)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_principal(self):
        r = self.c(self.admin).post("/api/users/principal/assign/", {"teacher": self.principal.id})
        self.assertEqual(r.status_code, 201, r.content)

    def add(self, user, title="Nanofluid paper"):
        r = self.c(user).post("/api/users/participation/add/", {
            "category": "journal", "title": title, "date": timezone.localdate().isoformat(),
            "activity_role": "published", "details": "Applied Thermal Engg, Vol 214", "indexing": "scopus"})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def review(self, user, pk, action, note=""):
        return self.c(user).post(f"/api/users/achievements/{pk}/review/", {"action": action, "note": note})

    # ---------------------------------------------------------------- achievements
    def test_the_hod_verifies_or_returns_and_verified_entries_are_locked(self):
        pk = self.add(self.t1)
        self.assertEqual(FacultyParticipation.objects.get(pk=pk).status, "pending")
        self.assertTrue(Notification.objects.filter(recipient=self.hod, title__startswith="Verify:").exists())
        self.assertEqual(self.review(self.other, pk, "verify").status_code, 403)     # another department
        self.assertEqual(self.review(self.t1, pk, "verify").status_code, 403)        # own entry
        self.assertEqual(self.review(self.hod, pk, "return").status_code, 400)       # needs a note
        self.assertEqual(self.review(self.hod, pk, "return", "Attach the DOI page").status_code, 200)
        r = self.c(self.t1).patch(f"/api/users/achievements/{pk}/", {"details": "DOI 10.1016/x"}, format="json")
        self.assertEqual((r.status_code, r.json()["status"]), (200, "pending"))
        listed = self.c(self.hod).get("/api/users/achievements/review/").json()
        self.assertEqual([x["id"] for x in listed["rows"]], [pk])
        self.assertEqual(self.review(self.hod, pk, "verify").status_code, 200)
        self.assertEqual(self.c(self.t1).delete(f"/api/users/participation/{pk}/delete/").status_code, 400)
        r = self.c(self.t1).patch(f"/api/users/achievements/{pk}/", {"title": "x"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_an_hods_own_entry_goes_to_the_principal(self):
        self.make_principal()
        pk = self.add(self.hod, "HOD's paper")
        self.assertTrue(Notification.objects.filter(recipient=self.principal, title__startswith="Verify:").exists())
        self.assertEqual(self.review(self.hod, pk, "verify").status_code, 403)
        rows = self.c(self.hod).get("/api/users/achievements/review/").json()["rows"]
        self.assertNotIn(pk, [x["id"] for x in rows])
        self.assertEqual(self.review(self.principal, pk, "verify").status_code, 200)

    # ---------------------------------------------------------------- appraisal
    def open_cycle(self):
        today = timezone.localdate()
        body = {"name": "2026-27", "start": (today - datetime.timedelta(days=120)).isoformat(),
                "end": (today + datetime.timedelta(days=240)).isoformat()}
        self.assertEqual(self.c(self.t1).post("/api/users/appraisal/cycles/", body, format="json").status_code, 403)
        r = self.c(self.admin).post("/api/users/appraisal/cycles/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def full(self, n=20):
        return {"teaching": 25, "results": 16, "research": n, "department": 12, "development": 7}

    def test_self_hod_principal_then_the_teacher_replies(self):
        self.make_principal()
        cycle = self.open_cycle()
        pk = self.add(self.t1)
        self.review(self.hod, pk, "verify")
        ap = self.c(self.t1).get("/api/users/appraisal/mine/").json()["appraisal"]
        self.assertIn("1 journal publication (verified)", ap["facts"]["research"][0])
        url = f"/api/users/appraisal/{ap['id']}/"
        summary = "Completed the funded dryer prototype and two FDPs."
        r = self.c(self.t1).post(url + "self/", {"scores": {"teaching": 25}, "summary": summary, "submit": True},
                                 format="json")
        self.assertEqual(r.status_code, 400)                                       # every area needed
        r = self.c(self.t1).post(url + "self/", {"scores": dict(self.full(), research=26), "summary": summary,
                                                  "submit": True}, format="json")
        self.assertEqual(r.status_code, 400)                                       # research max is 25
        r = self.c(self.t1).post(url + "self/", {"scores": self.full(), "summary": summary, "submit": True},
                                 format="json")
        self.assertEqual(r.json()["status"], "with_hod")
        self.assertEqual(self.c(self.other).get(url).status_code, 403)
        # the HOD reviews; remarks are needed to send it on
        r = self.c(self.hod).post(url + "hod/", {"scores": self.full(18), "action": "forward"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c(self.principal).post(url + "principal/", {"action": "finalise", "grade": "A"},
                                                     format="json").status_code, 403)   # not its turn
        r = self.c(self.hod).post(url + "hod/", {"scores": self.full(18), "remarks": "Strong research year.",
                                                 "action": "forward"}, format="json")
        self.assertEqual((r.json()["status"], r.json()["hod_total"]), ("with_principal", 78))
        mine = self.c(self.t1).get(url).json()
        self.assertEqual((mine["hod_remarks"], mine["hod_total"]), ("", None))      # hidden until final
        r = self.c(self.principal).post(url + "principal/", {"action": "finalise", "remarks": "Well done this year."},
                                        format="json")
        self.assertEqual(r.status_code, 400)                                       # grade needed
        r = self.c(self.principal).post(url + "principal/", {"action": "finalise", "grade": "A",
                                                             "remarks": "Well done this year."}, format="json")
        self.assertEqual(r.json()["status"], "done")
        mine = self.c(self.t1).get(url).json()
        self.assertEqual((mine["grade"], mine["hod_total"], mine["can_reply"]), ("A", 78, True))
        self.assertEqual(self.c(self.t1).post(url + "reply/", {"reply": "Thank you, agreed."}, format="json")
                         .status_code, 200)
        self.assertEqual(self.c(self.t1).post(url + "reply/", {"reply": "Again"}, format="json").status_code, 400)
        # areas are fixed once appraisals are sent in
        r = self.c(self.admin).patch(f"/api/users/appraisal/cycles/{cycle}/",
                                     {"areas": [{"label": "A", "max": 50}, {"label": "B", "max": 50}]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_an_hods_appraisal_skips_the_hod_and_the_admin_finalises_without_a_principal(self):
        self.open_cycle()
        ap = self.c(self.hod).get("/api/users/appraisal/mine/").json()["appraisal"]
        url = f"/api/users/appraisal/{ap['id']}/"
        r = self.c(self.hod).post(url + "self/", {"scores": self.full(), "submit": True,
                                                  "summary": "Ran the department and the NBA visit."}, format="json")
        self.assertEqual(r.json()["status"], "with_principal")
        self.assertEqual(self.c(self.hod).post(url + "principal/", {"action": "finalise", "grade": "A",
                                                                    "remarks": "Good year overall."},
                                               format="json").status_code, 403)
        r = self.c(self.admin).post(url + "principal/", {"action": "finalise", "grade": "A+",
                                                         "remarks": "Good year overall."}, format="json")
        self.assertEqual(r.json()["status"], "done")
        self.assertEqual(Appraisal.objects.get(pk=ap["id"]).principal_by, self.admin)
