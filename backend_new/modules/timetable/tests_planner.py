"""
WAVE 1 TESTS - the student planner (/api/planner/).

Run:  python manage.py test modules.timetable.tests_planner -v 2
"""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import ParentProfile, User
from modules.attendance.models import StudentLeaveRequest
from modules.events.models import CalendarEvent
from modules.exams.models import ExamSchedule
from modules.learning.models import Assignment, Quiz, QuizAttempt, Submission
from modules.timetable.models import Holiday, Semester, TimeSlot, TimetableApproval, TimetableEntry

_today = datetime.date.today()
MON = _today - datetime.timedelta(days=_today.weekday()) + datetime.timedelta(days=7)   # next week's Monday


def at(day, hh=17):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, 0)))


class PlannerTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.teacher = mk("teach1", password="x", role="teacher")
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.thermo = Subject.objects.create(name="Thermo", code="ME301", year=self.year, semester=3)
        self.other = Subject.objects.create(name="Other class", code="ME999", year=self.year, semester=3)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.year,
                                                    subject=self.thermo)
        self.ta_other = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                          year=self.year, subject=self.other)
        self.student = mk("asha", password="x", role="student", course=self.course, year=2, semester=3)
        Enrollment.objects.create(student=self.student, teaching_assignment=self.ta)
        self.classmate = mk("bala", password="x", role="student", course=self.course, year=2, semester=3)
        Enrollment.objects.create(student=self.classmate, teaching_assignment=self.ta_other)

        self.sem_end = MON + datetime.timedelta(days=30)
        Semester.objects.create(name="This semester", start_date=MON - datetime.timedelta(days=90),
                                end_date=self.sem_end, is_active=True)
        slot = TimeSlot.objects.create(period_no=1, start_time=datetime.time(9, 0), end_time=datetime.time(9, 50))
        TimetableEntry.objects.create(assignment=self.ta, day_of_week=0, time_slot=slot)        # Mondays
        TimetableEntry.objects.create(assignment=self.ta_other, day_of_week=1, time_slot=slot)  # not hers
        TimetableApproval.objects.create(course=self.course, year=self.year, semester=3,
                                         status=TimetableApproval.Status.APPROVED)

        self.parent = mk("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

    def get(self, user, query="", start=MON, days=7):
        c = APIClient()
        c.force_authenticate(user=user)
        return c.get(f"/api/planner/?start={start.isoformat()}&days={days}{query}")

    def day(self, data, d):
        return next(x for x in data["days"] if x["date"] == d.isoformat())

    # ------------------------------------------------------------------
    def test_week_has_only_my_classes(self):
        r = self.get(self.student)
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual([c["subject"] for c in self.day(data, MON)["classes"]], ["Thermo"])
        self.assertEqual(self.day(data, MON)["classes"][0]["start"], "09:00")
        self.assertEqual(self.day(data, MON + datetime.timedelta(days=1))["classes"], [])   # classmate's subject
        self.assertEqual(data["summary"]["classes"], 1)

    def test_unapproved_timetable_is_hidden(self):
        TimetableApproval.objects.update(status="draft")
        self.assertEqual(self.get(self.student).json()["summary"]["classes"], 0)

    def test_no_classes_on_holidays_leave_or_after_the_semester(self):
        Holiday.objects.create(date=MON, name="Deepavali")
        data = self.get(self.student, days=14).json()
        self.assertEqual(self.day(data, MON)["holiday"], "Deepavali")
        self.assertEqual(self.day(data, MON)["classes"], [])
        next_mon = MON + datetime.timedelta(days=7)
        self.assertEqual(len(self.day(data, next_mon)["classes"]), 1)

        StudentLeaveRequest.objects.create(student=self.student, leave_type="sick", from_date=next_mon,
                                           to_date=next_mon, reason="fever", status="approved", stage="closed")
        data = self.get(self.student, days=14).json()
        self.assertTrue(self.day(data, next_mon)["on_leave"])
        self.assertEqual(self.day(data, next_mon)["classes"], [])

        after = self.sem_end + datetime.timedelta(days=1)                     # semester over
        self.assertEqual(self.get(self.student, start=after).json()["summary"]["classes"], 0)

    def test_assignment_and_quiz_status(self):
        wed = MON + datetime.timedelta(days=2)
        done = Assignment.objects.create(title="Lab 1", teaching_assignment=self.ta, created_by=self.teacher,
                                         due_date=at(wed))
        Assignment.objects.create(title="Lab 2", teaching_assignment=self.ta, created_by=self.teacher,
                                  due_date=at(wed, 18))
        Assignment.objects.create(title="Not mine", teaching_assignment=self.ta_other,
                                  created_by=self.teacher, due_date=at(wed))
        Submission.objects.create(assignment=done, student=self.student)
        quiz = Quiz.objects.create(title="Quiz 1", teaching_assignment=self.ta, created_by=self.teacher,
                                   due_date=at(wed, 10))
        items = self.day(self.get(self.student).json(), wed)["items"]
        self.assertEqual([(i["type"], i["title"], i["status"]) for i in items],
                         [("quiz", "Quiz 1", "pending"), ("assignment", "Lab 1", "submitted"),
                          ("assignment", "Lab 2", "pending")])
        QuizAttempt.objects.create(quiz=quiz, student=self.student)
        items = self.day(self.get(self.student).json(), wed)["items"]
        self.assertEqual(items[0]["status"], "attempted")

    def test_overdue(self):
        past = timezone.localdate() - datetime.timedelta(days=2)
        Assignment.objects.create(title="Old", teaching_assignment=self.ta, created_by=self.teacher,
                                  due_date=at(past))
        data = self.get(self.student, start=past, days=3).json()
        self.assertEqual(self.day(data, past)["items"][0]["status"], "overdue")
        self.assertEqual(data["summary"]["overdue"], 1)

    def test_exams_and_events(self):
        fri = MON + datetime.timedelta(days=4)
        ExamSchedule.objects.create(subject=self.thermo, semester=3, exam_date=fri, session="AN")
        ExamSchedule.objects.create(subject=self.other, semester=3, exam_date=fri, session="FN")
        CalendarEvent.objects.create(title="Sports day", event_type="event", audience="everyone",
                                     start_date=MON, end_date=MON + datetime.timedelta(days=1))
        CalendarEvent.objects.create(title="Staff meet", audience="teachers", start_date=MON)
        CalendarEvent.objects.create(title="Final years only", audience="students", year_number=4,
                                     start_date=MON)
        data = self.get(self.student).json()
        exams = [i for i in self.day(data, fri)["items"] if i["type"] == "exam"]
        self.assertEqual([(e["subject"], e["time"]) for e in exams], [("Thermo", "AN")])
        self.assertEqual([i["title"] for i in self.day(data, MON)["items"]], ["Sports day"])
        self.assertEqual([i["title"] for i in self.day(data, MON + datetime.timedelta(days=1))["items"]],
                         ["Sports day"])                                   # a 2-day event shows on both
        self.assertEqual(data["summary"]["exams"], 1)

    def test_parent_sees_their_child_only(self):
        r = self.get(self.parent, query=f"&child={self.student.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["student"]["id"], self.student.id)
        self.assertEqual(self.get(self.parent, query=f"&child={self.classmate.id}").status_code, 404)

    def test_who_may_open_it_and_bad_input(self):
        self.assertEqual(self.get(self.teacher).status_code, 403)
        c = APIClient()
        c.force_authenticate(user=self.student)
        self.assertEqual(c.get("/api/planner/?start=16-11-2026").status_code, 400)
        self.assertEqual(len(c.get("/api/planner/?days=500").json()["days"]), 42)     # capped
