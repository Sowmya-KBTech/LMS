"""
TIMETABLE VALIDATION TESTS (meeting point 5)

Proves the clash rules hold at every step:
  place a cell  ->  submit  ->  admin approve  ->  move a cell

Two departments share one teacher (X) and one room (R1), so a clash is
always "another department booked them first".

Run:  python manage.py test modules.timetable -v 2
"""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.timetable.models import (
    ActivityType, ClassActivity, Room, TimeSlot, TimetableApproval, TimetableEntry,
)
from modules.timetable.services import availability, validate_submission

MON, TUE = 0, 1
SATURDAY = 5          # no longer a working day
SEM = 1

URL_PLACE = "/api/timetable/"
URL_SUBMIT = "/api/timetable/submit/"
URL_MOVE = "/api/timetable/move/"


def url_action(pk):
    return f"/api/timetable/approvals/{pk}/action/"


class TimetableTestBase(TestCase):
    """Two departments (A = Mechanical, B = ECE), each with one class."""

    def setUp(self):
        self.client = APIClient()

        # ---- people ----
        self.admin = User.objects.create_user(username="admin1", password="x", role="admin")
        self.hod_a = User.objects.create_user(username="hod_a", password="x", role="teacher")
        self.hod_b = User.objects.create_user(username="hod_b", password="x", role="teacher")
        self.x = User.objects.create_user(username="teacher_x", password="x", role="teacher",
                                          first_name="Ravi", last_name="Kumar")
        self.y = User.objects.create_user(username="teacher_y", password="x", role="teacher")

        # ---- departments, each with its HOD ----
        self.dept_a = Department.objects.create(name="Mechanical", code="ME", hod=self.hod_a)
        self.dept_b = Department.objects.create(name="ECE", code="EC", hod=self.hod_b)

        # ---- classes ----
        self.course_a = Course.objects.create(name="B.E Mechanical")
        self.course_b = Course.objects.create(name="B.E ECE")
        self.year_a = Year.objects.create(course=self.course_a, year_number=1)
        self.year_b = Year.objects.create(course=self.course_b, year_number=1)

        # an HOD's classes are found through the department's students
        User.objects.create_user(username="stu_a", password="x", role="student",
                                 department=self.dept_a, course=self.course_a, year=1, semester=SEM)
        User.objects.create_user(username="stu_b", password="x", role="student",
                                 department=self.dept_b, course=self.course_b, year=1, semester=SEM)

        # ---- subjects + teaching assignments ----
        sub_a1 = Subject.objects.create(name="Thermodynamics", year=self.year_a, semester=SEM, weekly_hours=4)
        sub_a2 = Subject.objects.create(name="Mechanics", year=self.year_a, semester=SEM, weekly_hours=4)
        sub_b1 = Subject.objects.create(name="Signals", year=self.year_b, semester=SEM, weekly_hours=4)

        self.ta_a1 = TeachingAssignment.objects.create(teacher=self.x, course=self.course_a,
                                                       year=self.year_a, subject=sub_a1)
        self.ta_a2 = TeachingAssignment.objects.create(teacher=self.y, course=self.course_a,
                                                       year=self.year_a, subject=sub_a2)
        self.ta_b1 = TeachingAssignment.objects.create(teacher=self.x, course=self.course_b,
                                                       year=self.year_b, subject=sub_b1)

        # ---- bell schedule + room ----
        t = datetime.time
        self.p1 = TimeSlot.objects.create(period_no=1, start_time=t(9, 0), end_time=t(9, 50))
        self.p2 = TimeSlot.objects.create(period_no=2, start_time=t(9, 50), end_time=t(10, 40))
        self.brk = TimeSlot.objects.create(period_no=99, start_time=t(10, 40), end_time=t(10, 55),
                                           label="Break", is_break=True)
        self.room = Room.objects.create(name="R1")

    # ---------- helpers ----------
    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def place(self, user, ta, day, slot, room=None):
        self.as_user(user)
        data = {"kind": "class", "assignment": ta.id, "day_of_week": day, "time_slot": slot.id}
        if room:
            data["room"] = room.id
        return self.client.post(URL_PLACE, data, format="json")

    def entry(self, ta, day, slot, room=None):
        """Put a cell straight into the database (setup, no checks)."""
        return TimetableEntry.objects.create(assignment=ta, day_of_week=day, time_slot=slot, room=room)

    def approval(self, year, course, status):
        return TimetableApproval.objects.create(
            year=year, course=course, semester=SEM, status=status, last_active=timezone.now(),
        )

    def move(self, user, entry, day, slot_id):
        self.as_user(user)
        return self.client.post(URL_MOVE, {"entry": entry.id, "day": day, "slot": slot_id}, format="json")

    def detail(self, response):
        data = response.data
        if isinstance(data, dict):
            return str(data.get("detail", data))
        return str(data)


# =====================================================================
#  1) PLACING A CELL
# =====================================================================
class PlaceCellTests(TimetableTestBase):

    def test_hod_can_place_a_free_cell(self):
        r = self.place(self.hod_a, self.ta_a1, MON, self.p1)
        self.assertEqual(r.status_code, 201, r.data)

    def test_class_cannot_have_two_things_in_one_cell(self):
        self.place(self.hod_a, self.ta_a1, MON, self.p1)
        r = self.place(self.hod_a, self.ta_a2, MON, self.p1)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already has something", self.detail(r))

    def test_same_teacher_cannot_teach_two_classes_at_once(self):
        self.place(self.hod_a, self.ta_a1, MON, self.p1)            # X in Mechanical
        r = self.place(self.hod_b, self.ta_b1, MON, self.p1)        # X in ECE, same period
        self.assertEqual(r.status_code, 400)
        self.assertIn("already booked", self.detail(r))
        self.assertFalse(TimetableEntry.objects.filter(assignment=self.ta_b1).exists())

    def test_same_room_cannot_be_double_booked(self):
        self.place(self.hod_a, self.ta_a2, MON, self.p1, room=self.room)   # Y in R1
        r = self.place(self.hod_b, self.ta_b1, MON, self.p1, room=self.room)  # X in R1
        self.assertEqual(r.status_code, 400)
        self.assertIn("R1 is already booked", self.detail(r))

    def test_activity_without_teacher_blocks_nobody(self):
        library = ActivityType.objects.create(name="Library")
        ca = ClassActivity.objects.create(activity=library, year=self.year_b, semester=SEM)  # no teacher
        self.place(self.hod_a, self.ta_a1, MON, self.p1)
        self.as_user(self.hod_b)
        r = self.client.post(URL_PLACE, {"kind": "activity", "class_activity": ca.id,
                                         "day_of_week": MON, "time_slot": self.p1.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_activity_with_teacher_clashes_like_a_lecture(self):
        mentor = ActivityType.objects.create(name="Mentor")
        ca = ClassActivity.objects.create(activity=mentor, year=self.year_b, semester=SEM, teacher=self.x)
        self.place(self.hod_a, self.ta_a1, MON, self.p1)
        self.as_user(self.hod_b)
        r = self.client.post(URL_PLACE, {"kind": "activity", "class_activity": ca.id,
                                         "day_of_week": MON, "time_slot": self.p1.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already booked", self.detail(r))

    def test_hod_cannot_edit_another_departments_class(self):
        r = self.place(self.hod_b, self.ta_a1, MON, self.p1)
        self.assertEqual(r.status_code, 403)

    def test_submitted_timetable_is_locked_for_the_hod(self):
        self.place(self.hod_a, self.ta_a1, MON, self.p1)
        self.as_user(self.hod_a)
        s = self.client.post(URL_SUBMIT, {"year": self.year_a.id, "semester": SEM}, format="json")
        self.assertEqual(s.status_code, 200, s.data)
        r = self.place(self.hod_a, self.ta_a2, TUE, self.p2)
        self.assertEqual(r.status_code, 403)


# =====================================================================
#  2) SUBMIT
# =====================================================================
class SubmitTests(TimetableTestBase):

    def test_clean_timetable_submits(self):
        self.place(self.hod_a, self.ta_a1, MON, self.p1)
        self.as_user(self.hod_a)
        r = self.client.post(URL_SUBMIT, {"year": self.year_a.id, "semester": SEM}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(TimetableApproval.objects.get(year=self.year_a).status, "submitted")

    def test_submit_refused_when_another_department_holds_the_teacher(self):
        # Both HODs drafted the same teacher in the same period (Layer 3 case).
        mine = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "draft")
        self.entry(self.ta_b1, MON, self.p1)
        self.approval(self.year_b, self.course_b, "draft")

        self.as_user(self.hod_a)
        r = self.client.post(URL_SUBMIT, {"year": self.year_a.id, "semester": SEM}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["conflicts"][0]["entry"], mine.id)
        self.assertEqual(TimetableApproval.objects.get(year=self.year_a).status, "draft")


# =====================================================================
#  3) ADMIN APPROVE / REJECT
# =====================================================================
class ApprovalTests(TimetableTestBase):

    def test_admin_approves_a_clean_submitted_timetable(self):
        self.entry(self.ta_a1, MON, self.p1)
        a = self.approval(self.year_a, self.course_a, "submitted")
        self.as_user(self.admin)
        r = self.client.post(url_action(a.id), {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        a.refresh_from_db()
        self.assertEqual(a.status, "approved")

    def test_approve_refused_when_it_clashes_with_an_approved_timetable(self):
        self.entry(self.ta_a1, MON, self.p1)                      # X, Mechanical, approved
        self.approval(self.year_a, self.course_a, "approved")
        self.entry(self.ta_b1, MON, self.p1)                      # X, ECE, same period
        b = self.approval(self.year_b, self.course_b, "submitted")

        self.as_user(self.admin)
        r = self.client.post(url_action(b.id), {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Cannot approve", self.detail(r))
        self.assertEqual(len(r.data["conflicts"]), 1)
        b.refresh_from_db()
        self.assertEqual(b.status, "submitted")                   # untouched
        self.assertIsNone(b.reviewed_by)

    def test_only_a_submitted_timetable_can_be_decided(self):
        self.entry(self.ta_a1, MON, self.p1)
        a = self.approval(self.year_a, self.course_a, "approved")
        self.as_user(self.admin)
        r = self.client.post(url_action(a.id), {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Only a submitted timetable", self.detail(r))

    def test_reject_with_a_remark(self):
        self.entry(self.ta_a1, MON, self.p1)
        a = self.approval(self.year_a, self.course_a, "submitted")
        self.as_user(self.admin)
        r = self.client.post(url_action(a.id), {"action": "reject", "remark": "Add library"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        a.refresh_from_db()
        self.assertEqual(a.status, "rejected")
        self.assertEqual(a.remark, "Add library")

    def test_hod_cannot_approve(self):
        self.entry(self.ta_a1, MON, self.p1)
        a = self.approval(self.year_a, self.course_a, "submitted")
        self.as_user(self.hod_a)
        r = self.client.post(url_action(a.id), {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 403)


# =====================================================================
#  4) MOVE  (the "Move to Tue P3" button)
# =====================================================================
class MoveTests(TimetableTestBase):

    def test_move_to_a_free_cell(self):
        e = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "draft")
        r = self.move(self.hod_a, e, TUE, self.p2.id)
        self.assertEqual(r.status_code, 200, r.data)
        e.refresh_from_db()
        self.assertEqual((e.day_of_week, e.time_slot_id), (TUE, self.p2.id))

    def test_move_refused_on_teacher_clash(self):
        self.entry(self.ta_a1, MON, self.p1)                      # X busy Mon P1 (approved)
        self.approval(self.year_a, self.course_a, "approved")
        e = self.entry(self.ta_b1, TUE, self.p1)
        self.approval(self.year_b, self.course_b, "draft")

        r = self.move(self.hod_b, e, MON, self.p1.id)
        self.assertEqual(r.status_code, 409)
        self.assertIn("already booked", self.detail(r))
        e.refresh_from_db()
        self.assertEqual((e.day_of_week, e.time_slot_id), (TUE, self.p1.id))   # not moved

    def test_move_refused_on_class_clash(self):
        self.entry(self.ta_a1, MON, self.p1)
        e = self.entry(self.ta_a2, TUE, self.p1)
        self.approval(self.year_a, self.course_a, "draft")
        r = self.move(self.hod_a, e, MON, self.p1.id)
        self.assertEqual(r.status_code, 409)
        self.assertIn("already has something", self.detail(r))

    def test_move_refused_on_room_clash(self):
        self.entry(self.ta_a2, MON, self.p1, room=self.room)      # Y in R1 (approved)
        self.approval(self.year_a, self.course_a, "approved")
        e = self.entry(self.ta_b1, TUE, self.p1, room=self.room)
        self.approval(self.year_b, self.course_b, "draft")
        r = self.move(self.hod_b, e, MON, self.p1.id)
        self.assertEqual(r.status_code, 409)
        self.assertIn("R1 is already booked", self.detail(r))

    def test_move_refused_when_submitted(self):
        e = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "submitted")
        r = self.move(self.hod_a, e, TUE, self.p2.id)
        self.assertEqual(r.status_code, 403)

    def test_move_into_a_break_is_refused(self):
        e = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "draft")
        r = self.move(self.hod_a, e, MON, self.brk.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn("break", self.detail(r))

    def test_move_to_saturday_is_refused(self):
        e = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "draft")
        r = self.move(self.hod_a, e, SATURDAY, self.p1.id)
        self.assertEqual(r.status_code, 400)

    def test_moving_an_approved_timetable_sends_it_back_to_draft(self):
        e = self.entry(self.ta_a1, MON, self.p1)
        a = self.approval(self.year_a, self.course_a, "approved")
        r = self.move(self.hod_a, e, TUE, self.p2.id)
        self.assertEqual(r.status_code, 200, r.data)
        a.refresh_from_db()
        self.assertEqual(a.status, "draft")


# =====================================================================
#  5) SUGGESTIONS  (what the grid and the conflict panel offer)
# =====================================================================
class SuggestionTests(TimetableTestBase):

    def test_availability_never_offers_saturday(self):
        av = availability(self.ta_a1, year_id=self.year_a.id, semester=SEM)
        days = {c["day"] for c in av["free"] + av["blocked"]}
        self.assertTrue(days)
        self.assertLess(max(days), SATURDAY)

    def test_availability_greys_out_a_busy_teacher(self):
        self.entry(self.ta_b1, MON, self.p1)                      # X busy in ECE
        self.approval(self.year_b, self.course_b, "approved")
        av = availability(self.ta_a1, year_id=self.year_a.id, semester=SEM)
        blocked = {(c["day"], c["slot"]) for c in av["blocked"]}
        self.assertIn((MON, self.p1.id), blocked)

    def test_every_conflict_suggestion_can_actually_be_moved_to(self):
        # A clash is found at submit; the first "Move to" suggestion must work.
        self.entry(self.ta_b1, MON, self.p1)
        self.approval(self.year_b, self.course_b, "approved")
        e = self.entry(self.ta_a1, MON, self.p1)
        self.approval(self.year_a, self.course_a, "draft")

        conflicts = validate_submission(self.year_a.id, SEM)
        self.assertEqual(len(conflicts), 1)
        suggestions = conflicts[0]["suggestions"]
        self.assertTrue(suggestions)
        for s in suggestions:
            self.assertLess(s["day"], SATURDAY)

        first = suggestions[0]
        r = self.move(self.hod_a, e, first["day"], first["slot"])
        self.assertEqual(r.status_code, 200, r.data)
