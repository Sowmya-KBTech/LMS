"""
WAVE 3 PART 2 TESTS - exam sessions, registration with arrears, the session
timetable's clash check, and hall tickets that list arrear papers.

Run:  python manage.py test modules.exams.tests_sessions -v 2
"""
import datetime
import importlib

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.exams.models import (EligibilityOverride, ExamRegistration, ExamSchedule, ExamSession,
                                  ResultEntry, SemesterResult)
from modules.fees.models import Fee


def next_weekday(d):
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


class SessionBase(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.today = timezone.localdate()
        self.dept = Department.objects.create(name="Computer Science", code="CS")
        self.course = Course.objects.create(name="B.E CSE")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.y3 = Year.objects.create(course=self.course, year_number=3)
        self.exam = mk("exam1", password="x", role="admin", sub_role="exam_admin")
        self.teacher = mk("ravi", password="x", role="teacher", department=self.dept)
        self.kavya = mk("kavya", password="x", role="student", department=self.dept, course=self.course,
                        year=3, semester=5, batch_year=2022, roll_number="22CS041")
        self.arun = mk("arun", password="x", role="student", department=self.dept, course=self.course,
                       year=2, semester=3, batch_year=2023, roll_number="23CS001")
        S = Subject.objects.create
        self.ds = S(name="Data Structures", code="CS301", year=self.y2, semester=3, credits=4)
        self.ma3 = S(name="Transforms", code="MA301", year=self.y2, semester=3, credits=4)
        self.cd = S(name="Compiler Design", code="CS501", year=self.y3, semester=5, credits=4)
        self.cn = S(name="Computer Networks", code="CS502", year=self.y3, semester=5, credits=4)
        # Kavya's Semester 3 result: CS301 is an arrear (RA), MA301 passed
        res = SemesterResult.objects.create(student=self.kavya, semester=3, is_published=True)
        ResultEntry.objects.create(result=res, subject=self.ds, marks_obtained=38, max_marks=100, grade="RA",
                                   is_pass=False, outcome="fail", internal_marks=30, end_marks=8,
                                   exam_session="Apr/May 2026")
        ResultEntry.objects.create(result=res, subject=self.ma3, marks_obtained=70, max_marks=100, grade="A",
                                   is_pass=True, outcome="pass")
        self.start = next_weekday(self.today + datetime.timedelta(days=20))
        self.session = ExamSession.objects.create(
            name="Nov/Dec 2026", semesters=[3, 5], reg_opens=self.today - datetime.timedelta(days=1),
            reg_closes=self.today + datetime.timedelta(days=5), late_until=self.today + datetime.timedelta(days=8),
            exam_start=self.start, exam_end=self.start + datetime.timedelta(days=14),
            regular_fee=500, arrear_fee=300, late_fee=200, is_current=True)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def register(self, user=None, arrears=(), submit=True):
        return self.c(user or self.kavya).post("/api/exam-registration/me/",
                                               {"arrear_subjects": list(arrears), "submit": submit}, format="json")

    def slot(self, subject, day, sess="FN", session=None):
        return ExamSchedule.objects.create(subject=subject, semester=subject.semester, exam_date=day, session=sess,
                                           exam_session=session or self.session)

    def day(self, n):
        """The n-th working day of the session (0 = the first)."""
        from modules.exams.views import _working_dates
        return _working_dates(self.session.exam_start, self.session.exam_end)[n]


class SessionAdminTests(SessionBase):

    def test_only_the_exam_admin_manages_sessions(self):
        for u in (self.kavya, self.teacher):
            self.assertEqual(self.c(u).get("/api/exam-sessions/").status_code, 403)
        self.assertEqual(self.c(self.exam).get("/api/exam-sessions/").status_code, 200)

    def test_create_checks_the_fields(self):
        r = self.c(self.exam).post("/api/exam-sessions/", {"name": "", "reg_opens": "30-11-2026",
                                                          "reg_closes": "20-11-2026"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.data["errors"])
        self.assertIn("reg_closes", r.data["errors"])
        r = self.c(self.exam).post("/api/exam-sessions/", {"name": "nov/dec 2026", "reg_opens": "01-04-2027"},
                                   format="json")
        self.assertEqual(r.data["errors"]["name"], "Another exam session already has this name.")

    def test_new_session_is_not_current_until_made_current(self):
        r = self.c(self.exam).post("/api/exam-sessions/", {"name": "Apr/May 2027", "reg_opens": "01-04-2027",
                                                          "semesters": [2, 4, 6]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.data["is_current"])
        self.c(self.exam).post(f"/api/exam-sessions/{r.data['id']}/make-current/")
        self.assertEqual(list(ExamSession.objects.filter(is_current=True).values_list("name", flat=True)),
                         ["Apr/May 2027"])

    def test_session_with_registrations_cannot_be_deleted(self):
        self.register(arrears=[self.ds.id])
        r = self.c(self.exam).delete(f"/api/exam-sessions/{self.session.id}/")
        self.assertEqual(r.status_code, 400)

    def test_progress_counts_by_class(self):
        self.register(arrears=[self.ds.id])
        r = self.c(self.exam).get(f"/api/exam-sessions/{self.session.id}/progress/")
        rows = {x["semester"]: x for x in r.data["classes"]}
        self.assertEqual((rows[5]["students"], rows[5]["registered"], rows[5]["arrear_papers"], rows[5]["fee_pending"]),
                         (1, 1, 1, 1))
        self.assertEqual((rows[3]["students"], rows[3]["not_yet"]), (1, 1))
        self.assertEqual(r.data["totals"]["students"], 2)


class RegistrationTests(SessionBase):

    def test_student_sees_current_subjects_and_arrears(self):
        r = self.c(self.kavya).get("/api/exam-registration/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["window"], "open")
        self.assertEqual([x["code"] for x in r.data["regular"]], ["CS501", "CS502"])
        self.assertEqual([(x["code"], x["grade"], x["next_attempt"]) for x in r.data["arrears"]], [("CS301", "RA", 2)])
        self.assertEqual(r.data["arrears"][0]["attempts"][0]["exam_session"], "Apr/May 2026")

    def test_submit_saves_papers_and_raises_the_fee(self):
        r = self.register(arrears=[self.ds.id])
        self.assertEqual(r.status_code, 200, r.content)
        reg = ExamRegistration.objects.get(student=self.kavya)
        self.assertEqual(sorted((p.subject.code, p.kind) for p in reg.papers.all()),
                         [("CS301", "arrear"), ("CS501", "regular"), ("CS502", "regular")])
        self.assertEqual((reg.status, reg.is_late), ("submitted", False))
        self.assertEqual((reg.fee.term, float(reg.fee.amount)), ("Exam fee - Nov/Dec 2026", 1300.0))
        self.assertFalse(r.data["complete"])
        # dropping the arrear lowers the same fee, it does not raise a second one
        self.register(arrears=[])
        self.assertEqual(Fee.objects.filter(student=self.kavya).count(), 1)
        self.assertEqual(float(Fee.objects.get(student=self.kavya).amount), 1000.0)

    def test_only_own_arrears_can_be_picked(self):
        for bad in ([self.ma3.id], [self.cd.id], ["x"]):
            r = self.register(arrears=bad)
            self.assertEqual(r.status_code, 400, bad)
        self.assertFalse(ExamRegistration.objects.filter(student=self.kavya, papers__isnull=False).exists())

    def test_late_registration_adds_the_late_fee(self):
        self.session.reg_closes = self.today - datetime.timedelta(days=1)
        self.session.reg_opens = self.today - datetime.timedelta(days=5)
        self.session.save()
        r = self.register(arrears=[self.ds.id])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_late"])
        self.assertEqual(r.data["fee"]["amount"], 1500.0)

    def test_closed_window_refuses(self):
        self.session.registration_closed = True
        self.session.save()
        r = self.register(arrears=[self.ds.id])
        self.assertEqual((r.status_code, r.data["detail"]), (400, "Registration is closed. Please contact the exam cell."))

    def test_paid_registration_is_final(self):
        self.register(arrears=[self.ds.id])
        Fee.objects.filter(student=self.kavya).update(status="paid", paid_amount=1300)
        r = self.register(arrears=[])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ExamRegistration.objects.get(student=self.kavya).papers.count(), 3)
        self.assertTrue(self.c(self.kavya).get("/api/exam-registration/me/").data["complete"])

    def test_exam_cell_can_add_every_arrear(self):
        self.session.students_pick_arrears = False
        self.session.save()
        self.register(arrears=[])
        self.assertTrue(ExamRegistration.objects.get(student=self.kavya).papers.filter(subject=self.ds,
                                                                                      kind="arrear").exists())

    def test_supplementary_session_is_arrears_only(self):
        self.session.kind = "supplementary"
        self.session.save()
        r = self.register(arrears=[self.ds.id])
        self.assertEqual([p.subject.code for p in ExamRegistration.objects.get(student=self.kavya).papers.all()],
                         ["CS301"])
        self.assertEqual(r.data["fee"]["amount"], 300.0)
        self.assertEqual(self.register(user=self.arun).status_code, 400)    # no arrears, nothing to write


class TimetableClashTests(SessionBase):

    def test_arrear_clash_is_found_with_free_slots(self):
        self.register(arrears=[self.ds.id])
        self.slot(self.ds, self.day(0), "FN")      # Sem 3 paper
        self.slot(self.ma3, self.day(1), "FN")
        self.slot(self.cd, self.day(0), "FN")      # Kavya also writes CS301 then
        self.slot(self.cn, self.day(2), "FN")
        r = self.c(self.exam).get(f"/api/exam-sessions/{self.session.id}/timetable-check/")
        self.assertEqual(len(r.data["clashes"]), 1)
        c = r.data["clashes"][0]
        self.assertEqual(sorted(s["code"] for s in c["subjects"]), ["CS301", "CS501"])
        self.assertEqual((c["count"], c["students"][0]["roll_number"]), (1, "22CS041"))
        # CS501 has 1 student, CS301 has 2 (Arun + Kavya) -> move CS501
        self.assertEqual(c["move_subject"], self.cd.id)
        sugg = {(s["exam_date"], s["session"]) for s in c["suggestions"]}
        self.assertTrue(sugg)
        self.assertNotIn((self.day(2).isoformat(), "FN"), sugg)      # Kavya writes CS502 then
        self.assertNotIn((self.day(0).isoformat(), "FN"), sugg)
        self.assertEqual(r.data["checks"]["clashes"], 1)

    def test_publish_is_refused_with_a_clash_then_locks_the_timetable(self):
        self.register(arrears=[self.ds.id])
        self.slot(self.ds, self.day(0))
        self.slot(self.ma3, self.day(1))
        cd = self.slot(self.cd, self.day(0))
        self.slot(self.cn, self.day(2))
        url = f"/api/exam-sessions/{self.session.id}/publish-timetable/"
        r = self.c(self.exam).post(url)
        self.assertEqual((r.status_code, r.data["detail"]), (400, "Fix 1 clash before publishing."))
        r = self.c(self.exam).patch(f"/api/exam-schedules/{cd.id}/", {"exam_date": self.day(3).isoformat()},
                                    format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.c(self.exam).post(url).status_code, 200)
        r = self.c(self.exam).patch(f"/api/exam-schedules/{cd.id}/", {"session": "AN"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("published", r.data["detail"])
        r = self.c(self.exam).post("/api/exam-schedules/", {"subject": self.cn.id, "semester": 5,
                                                           "exam_date": self.day(4).isoformat(), "session": "FN"})
        self.assertEqual(r.status_code, 400)

    def test_arrear_paper_without_a_date_blocks_publishing(self):
        sem2 = Year.objects.create(course=Course.objects.create(name="B.E ECE"), year_number=2)
        old = Subject.objects.create(name="Signals", code="EC401", year=sem2, semester=4, credits=3)
        res = SemesterResult.objects.create(student=self.kavya, semester=4, is_published=True)
        ResultEntry.objects.create(result=res, subject=old, marks_obtained=None, grade="", is_pass=False)
        self.register(arrears=[old.id])
        for i, s in enumerate((self.ds, self.ma3, self.cd, self.cn)):
            self.slot(s, self.day(i))
        r = self.c(self.exam).get(f"/api/exam-sessions/{self.session.id}/timetable-check/")
        self.assertEqual([x["code"] for x in r.data["unscheduled"]], ["EC401"])
        self.assertTrue(r.data["unscheduled"][0]["suggestions"])
        r = self.c(self.exam).post(f"/api/exam-sessions/{self.session.id}/publish-timetable/")
        self.assertEqual(r.data["detail"], "Fix 1 paper without a date before publishing.")

    def test_draft_keeps_class_papers_off_an_arrear_slot(self):
        self.register(arrears=[self.ds.id])
        self.slot(self.ds, self.day(0), "FN")
        r = self.c(self.exam).post("/api/exam-schedules/draft/", {
            "course": self.course.id, "year": 3, "semester": 5, "gap": 1, "session": "FN"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        slots = {(x["exam_date"], x["session"]) for x in r.data["draft"]}
        self.assertNotIn((self.day(0).isoformat(), "FN"), slots)
        self.assertTrue(r.data["clash_note"])
        self.assertTrue(all(self.session.exam_start.isoformat() <= x["exam_date"] <= self.session.exam_end.isoformat()
                            for x in r.data["draft"]))

    def test_schedule_list_shows_the_current_session_only(self):
        other = ExamSession.objects.create(name="Apr/May 2026", registration_required=False)
        self.slot(self.ds, self.day(0))
        self.slot(self.ds, self.day(1), session=other)       # same subject, another session is fine
        r = self.c(self.exam).get("/api/exam-schedules/?semester=3")
        self.assertEqual([x["exam_session"] for x in r.data], [self.session.id])
        r = self.c(self.exam).get(f"/api/exam-schedules/?exam_session={other.id}")
        self.assertEqual(len(r.data), 1)
        r = self.c(self.exam).post("/api/exam-schedules/", {"subject": self.ds.id, "semester": 3,
                                                           "exam_date": self.day(2).isoformat(), "session": "AN"})
        self.assertEqual((r.status_code, r.data["detail"]), (400, "Data Structures already has an exam date in this session."))


class HallTicketTests(SessionBase):

    def ready(self):
        for i, s in enumerate((self.ds, self.ma3, self.cd, self.cn)):
            self.slot(s, self.day(i))
        self.session.timetable_published = True
        self.session.hall_tickets_released = True
        self.session.save()

    def ticket(self, user=None):
        return self.c(user or self.kavya).get("/api/hall-ticket/").data

    def test_not_registered_means_no_ticket(self):
        self.ready()
        t = self.ticket()
        self.assertEqual((t["eligible"], t["reason"], t["subjects"]), (False, "not_registered", []))

    def test_not_released_yet(self):
        self.register(arrears=[self.ds.id])
        Fee.objects.filter(student=self.kavya).update(status="paid")
        t = self.ticket()
        self.assertEqual((t["eligible"], t["reason"]), (False, "not_released"))

    def test_ticket_lists_arrears_and_withholds_by_rule(self):
        self.ready()
        self.register(arrears=[self.ds.id])
        t = self.ticket()
        self.assertEqual(t["reason"], "registration_fee_unpaid")
        self.assertTrue(all(p["withheld"] == "registration_fee_unpaid" for p in t["subjects"]))
        self.assertEqual(t["registration_fee"]["amount"], 1300.0)
        Fee.objects.filter(student=self.kavya).update(status="paid")
        t = self.ticket()
        # no attendance -> regular papers withheld, the arrear paper is not
        papers = {p["code"]: p for p in t["subjects"]}
        self.assertEqual((papers["CS301"]["kind"], papers["CS301"]["withheld"]), ("arrear", None))
        self.assertEqual(papers["CS301"]["exam_date"], self.day(0).isoformat())
        self.assertTrue(papers["CS501"]["withheld"])
        self.assertTrue(t["eligible"])
        EligibilityOverride.objects.create(student=self.kavya, semester=5, reason="Medical", created_by=self.exam)
        t = self.ticket()
        self.assertTrue(all(p["withheld"] is None for p in t["subjects"]))
        self.assertEqual([p["code"] for p in t["subjects"]], ["CS301", "CS501", "CS502"])   # by exam date

    def test_without_a_session_the_old_hall_ticket_still_works(self):
        first = self.day(0)
        ExamSession.objects.all().delete()
        ExamSchedule.objects.create(subject=self.cd, semester=5, exam_date=first, session="AN")
        for subj in (self.cd, self.cn):
            ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=subj)
            Enrollment.objects.create(student=self.kavya, teaching_assignment=ta)
        t = self.ticket()
        self.assertIsNone(t["session"])
        self.assertTrue(t["released"])
        self.assertEqual({(p["code"], p["exam_date"], p["kind"]) for p in t["subjects"]},
                         {("CS501", first.isoformat(), "regular"), ("CS502", None, "regular")})


class MigrationTests(TestCase):

    def test_existing_exam_dates_move_into_one_current_session(self):
        course = Course.objects.create(name="B.E Civil")
        y = Year.objects.create(course=course, year_number=1)
        s1 = Subject.objects.create(name="Maths", code="MA101", year=y, semester=1)
        s2 = Subject.objects.create(name="Physics", code="PH101", year=y, semester=1)
        ExamSchedule.objects.create(subject=s1, semester=1, exam_date=datetime.date(2026, 4, 6))
        ExamSchedule.objects.create(subject=s2, semester=1, exam_date=datetime.date(2026, 4, 9), session="AN")
        mig = importlib.import_module("modules.exams.migrations.0009_exam_sessions")
        mig.attach_existing_schedule(django_apps, None)
        sess = ExamSession.objects.get()
        self.assertEqual((sess.name, sess.is_current, sess.registration_required, sess.hall_tickets_released,
                          sess.semesters, sess.exam_start, sess.exam_end),
                         ("Earlier exams", True, False, True, [1], datetime.date(2026, 4, 6), datetime.date(2026, 4, 9)))
        self.assertFalse(ExamSchedule.objects.filter(exam_session__isnull=True).exists())


# ============================================================ WAVE 3 PART 2b
class SeatingBase(SessionBase):

    def setUp(self):
        super().setUp()
        from modules.exams.models import ExamHall
        mk = User.objects.create_user
        self.session.fee_required = False
        self.session.save()
        self.s5b = mk("s5b", password="x", role="student", course=self.course, year=3, semester=5, roll_number="22CS050")
        self.s5c = mk("s5c", password="x", role="student", course=self.course, year=3, semester=5, roll_number="22CS051")
        self.s3b = mk("s3b", password="x", role="student", course=self.course, year=2, semester=3, roll_number="23CS002")
        for u in (self.kavya, self.s5b, self.s5c, self.arun, self.s3b):
            self.assertEqual(self.register(user=u).status_code, 200)
        self.slot(self.ds, self.day(0), "FN")        # CS301: arun, s3b
        self.slot(self.cd, self.day(0), "FN")        # CS501: kavya, s5b, s5c
        self.slot(self.ma3, self.day(1), "FN")
        self.slot(self.cn, self.day(1), "AN")
        self.session.timetable_published = True
        self.session.save()
        self.h1 = ExamHall.objects.create(name="B-201", seats=4, per_bench=2, order=1)
        self.h2 = ExamHall.objects.create(name="B-202", seats=4, per_bench=2, order=2)
        self.base = f"/api/exam-sessions/{self.session.id}"

    def allot(self, n=0, sit="FN"):
        return self.c(self.exam).post(f"{self.base}/seating/allot/", {"date": self.day(n).isoformat(), "sitting": sit},
                                      format="json")

    def plan(self, n=0, sit="FN"):
        return self.c(self.exam).get(f"{self.base}/seating/", {"date": self.day(n).isoformat(), "sitting": sit}).data


class HallTests(SeatingBase):

    def test_halls_are_checked_and_used_halls_cannot_be_deleted(self):
        c = self.c(self.exam)
        self.assertEqual(c.post("/api/exam-halls/", {"name": "b-201"}).status_code, 400)
        self.assertEqual(c.post("/api/exam-halls/", {"name": "C-101", "seats": 0}).status_code, 400)
        r = c.post("/api/exam-halls/", {"name": "C-101", "seats": 30, "per_bench": 2, "is_active": False})
        self.assertEqual(r.status_code, 201)
        self.allot()
        self.assertEqual(c.delete(f"/api/exam-halls/{self.h1.id}/").status_code, 400)
        self.assertEqual(c.delete(f"/api/exam-halls/{r.data['id']}/").status_code, 204)
        self.assertEqual(self.c(self.kavya).get("/api/exam-halls/").status_code, 403)

    def test_halls_from_timetable_rooms(self):
        from modules.timetable.models import Room
        Room.objects.create(name="C-101", capacity=60)
        Room.objects.create(name="Lab 2", kind="lab", capacity=30)
        Room.objects.create(name="B-201", capacity=60)          # already a hall
        r = self.c(self.exam).post("/api/exam-halls/from-rooms/")
        self.assertEqual(r.data["added"], 2)
        halls = {h["name"]: h for h in r.data["halls"]}
        self.assertEqual((halls["C-101"]["seats"], halls["C-101"]["is_active"]), (30, True))
        self.assertFalse(halls["Lab 2"]["is_active"])


class SeatingTests(SeatingBase):

    def test_seating_waits_for_the_published_timetable(self):
        self.session.timetable_published = False
        self.session.save()
        self.assertEqual(self.allot().status_code, 400)

    def test_alternate_puts_different_papers_on_a_bench(self):
        r = self.allot()
        self.assertEqual((r.status_code, r.data["seated"], r.data["unseated"]), (200, 5, 0))
        p = self.plan()
        self.assertEqual(p["same_neighbours"], 0)
        h1 = next(h for h in p["halls"] if h["name"] == "B-201")["seat_map"]
        self.assertEqual([s["code"] for s in h1], ["CS501", "CS301", "CS501", "CS301"])
        # a second run gives the same seats again, it does not add more
        self.allot()
        self.assertEqual(self.plan()["seated"], 5)

    def test_equal_papers_still_alternate(self):
        ExamRegistration.objects.filter(student=self.s5c).delete()     # 2 x CS301, 2 x CS501
        self.allot()
        p = self.plan()
        self.assertEqual((p["seated"], p["same_neighbours"]), (4, 0))

    def test_spaced_seats_one_per_bench_and_reports_who_has_no_seat(self):
        self.c(self.exam).patch(f"{self.base}/rules/", {"seating_mode": "spaced"}, format="json")
        r = self.allot()
        self.assertEqual((r.data["seated"], r.data["unseated"]), (4, 1))
        p = self.plan()
        self.assertEqual(len(p["not_seated"]), 1)
        self.assertTrue(all(s["seat"] % 2 == 1 for h in p["halls"] for s in h["seat_map"]))

    def test_hall_ticket_shows_hall_and_seat(self):
        self.session.hall_tickets_released = True
        self.session.save()
        EligibilityOverride.objects.create(student=self.kavya, semester=5, reason="Medical", created_by=self.exam)
        self.allot()
        t = self.c(self.kavya).get("/api/hall-ticket/").data
        cd = next(p for p in t["subjects"] if p["code"] == "CS501")
        cn = next(p for p in t["subjects"] if p["code"] == "CS502")
        self.assertEqual(cd["hall"], "B-201")
        self.assertIsNotNone(cd["seat"])
        self.assertIsNone(cn["hall"])          # that sitting has no seats yet


class InvigilationTests(SeatingBase):

    def setUp(self):
        super().setUp()
        from core.academics.models import TeachingAssignment
        from core.users.models import PrincipalTerm
        from modules.attendance.models import StaffLeaveRequest
        mk = User.objects.create_user
        self.t_leave = mk("t_leave", password="x", role="teacher", department=self.dept)
        self.t_teach = mk("t_teach", password="x", role="teacher", department=self.dept)
        self.t3 = mk("t3", password="x", role="teacher", department=self.dept)
        self.t4 = mk("t4", password="x", role="teacher", department=self.dept)
        self.principal = mk("principal", password="x", role="teacher", department=self.dept)
        self.hod = mk("hod", password="x", role="teacher", department=self.dept)
        self.dept.hod = self.hod
        self.dept.save()
        PrincipalTerm.objects.create(teacher=self.principal, start_date=self.today, is_current=True)
        TeachingAssignment.objects.create(teacher=self.t_teach, course=self.course, year=self.y3, subject=self.cd)
        self.Leave = StaffLeaveRequest
        StaffLeaveRequest.objects.create(teacher=self.t_leave, leave_type="casual", from_date=self.day(0),
                                         to_date=self.day(0), reason="x", status="approved")
        self.allot()

    def assign(self, n=0, sit="FN"):
        return self.c(self.exam).post(f"{self.base}/duties/assign/", {"date": self.day(n).isoformat(), "sitting": sit},
                                      format="json")

    def view(self, n=0, sit="FN"):
        return self.c(self.exam).get(f"{self.base}/duties/", {"date": self.day(n).isoformat(), "sitting": sit}).data

    def staff_on(self, v):
        return {s["username"] for h in v["halls"] for s in h["staff"]} | {s["username"] for s in v["relief"]}

    def test_duties_skip_leave_own_subject_principal_and_hods(self):
        r = self.assign()
        self.assertEqual((r.data["filled"], r.data["unfilled"]), (3, 0))      # 2 halls + 1 relief
        v = self.view()
        self.assertEqual(self.staff_on(v), {"ravi", "t3", "t4"})
        reasons = {s["username"]: s["reason"] for s in v["skipped"]}
        self.assertEqual(reasons, {"t_leave": "on leave", "t_teach": "teaches a paper of this sitting",
                                   "principal": "Principal", "hod": "HOD"})

    def test_two_invigilators_above_the_limit(self):
        self.c(self.exam).patch(f"{self.base}/rules/", {"two_invigilators_above": 3, "relief_per_sitting": 0},
                                format="json")
        self.assign()
        v = self.view()
        needed = {h["hall"]["name"]: (h["students"], h["needed"], len(h["staff"])) for h in v["halls"]}
        self.assertEqual(needed, {"B-201": (4, 2, 2), "B-202": (1, 1, 1)})

    def test_all_sittings_share_duties_fairly(self):
        self.c(self.exam).post(f"{self.base}/seating/allot/", {"all": True}, format="json")
        r = self.c(self.exam).post(f"{self.base}/duties/assign/", {"all": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        load = [x["duties"] for x in self.view()["load"] if x["username"] in ("ravi", "t3", "t4", "t_leave")]
        self.assertLessEqual(max(load) - min(load), 1)

    def test_leave_after_duties_is_flagged_with_a_replacement(self):
        self.assign()
        self.Leave.objects.create(teacher=self.t3, leave_type="casual", from_date=self.day(0), to_date=self.day(0),
                                  reason="x", status="approved")
        c = self.view()["conflicts"]
        self.assertEqual([x["staff"]["username"] for x in c], ["t3"])
        self.assertIsNone(c[0]["suggest"])                 # nobody free that day: everyone left is on duty or blocked
        t5 = User.objects.create_user("t5", password="x", role="teacher", department=self.dept)
        c = self.view()["conflicts"]
        self.assertEqual(c[0]["suggest"]["username"], "t5")
        url = f"/api/exam-duties/{c[0]['duty_id']}/"
        self.assertEqual(self.c(self.exam).patch(url, {"staff": self.t_leave.id}, format="json").status_code, 400)
        self.assertEqual(self.c(self.exam).patch(url, {"staff": self.t4.id}, format="json").status_code, 400)  # already on duty
        self.assertEqual(self.c(self.exam).patch(url, {"staff": t5.id}, format="json").status_code, 200)
        self.assertEqual(self.view()["conflicts"], [])

    def test_staff_see_their_own_duties(self):
        self.assign()
        r = self.c(self.t3).get("/api/exam-duties/me/")
        self.assertEqual(r.data["session"], "Nov/Dec 2026")
        self.assertEqual([(d["date"], d["sitting"]) for d in r.data["duties"]], [(self.day(0).isoformat(), "FN")])
