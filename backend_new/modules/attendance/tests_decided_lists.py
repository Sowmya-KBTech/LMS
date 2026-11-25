"""
Student requests page: ?show=decided on the class in-charge / HOD review lists
(on duty and leave). Without it, the lists still return only what waits for you.

Run:  python manage.py test modules.attendance.tests_decided_lists -v 2
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Year, YearTutor
from core.users.models import Department, User
from modules.attendance.models import ODRequest, StudentLeaveRequest

TODAY = timezone.localdate()


class DecidedListTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.other_hod = mk("hod2", password="x", role="teacher")
        self.civil = Department.objects.create(name="Civil", code="CE", hod=self.other_hod)
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.tutor = mk("tutor1", password="x", role="teacher", department=self.dept)
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.year)
        self.student = mk("stu1", password="x", role="student", department=self.dept,
                          course=self.course, year=2)
        self.outsider = mk("stu9", password="x", role="student", department=self.civil)

    def get(self, user, url, decided=False):
        c = APIClient()
        c.force_authenticate(user=user)
        r = c.get(f"/api/users/{url}/" + ("?show=decided" if decided else ""))
        self.assertEqual(r.status_code, 200, r.content)
        return [x["id"] for x in r.json()]

    def od(self, student=None, **kw):
        return ODRequest.objects.create(student=student or self.student, from_date=TODAY, to_date=TODAY,
                                        category=ODRequest.Category.PAPER, reason="Symposium", **kw)

    def leave(self, student=None, **kw):
        return StudentLeaveRequest.objects.create(student=student or self.student, leave_type="personal",
                                                  from_date=TODAY, to_date=TODAY, reason="Wedding", **kw)

    def test_hod_od_waiting_and_decided_are_separate(self):
        now = timezone.now()
        waiting = self.od(stage=ODRequest.Stage.AWAITING_HOD, tutor_reviewed_at=now)
        approved = self.od(status=ODRequest.Status.APPROVED, hod_reviewed_at=now)
        rejected = self.od(status=ODRequest.Status.REJECTED, hod_reviewed_at=now - timedelta(hours=1))
        self.od(student=self.outsider, status=ODRequest.Status.APPROVED, hod_reviewed_at=now)  # other dept
        self.assertEqual(self.get(self.hod, "hod/od"), [waiting.id])
        self.assertEqual(self.get(self.hod, "hod/od", decided=True), [approved.id, rejected.id])  # newest first

    def test_tutor_od_decided_includes_forwarded_ones(self):
        now = timezone.now()
        forwarded = self.od(stage=ODRequest.Stage.AWAITING_HOD, tutor_reviewed_at=now)
        waiting = self.od()
        self.assertEqual(self.get(self.tutor, "tutor/od"), [waiting.id])
        self.assertEqual(self.get(self.tutor, "tutor/od", decided=True), [forwarded.id])

    def test_hod_leave_waiting_and_decided(self):
        now = timezone.now()
        waiting = self.leave(stage=StudentLeaveRequest.Stage.AWAITING_HOD, tutor_reviewed_at=now)
        done = self.leave(status=StudentLeaveRequest.Status.APPROVED, hod_reviewed_at=now)
        self.assertEqual(self.get(self.hod, "hod/leave"), [waiting.id])
        self.assertEqual(self.get(self.hod, "hod/leave", decided=True), [done.id])

    def test_tutor_leave_decided(self):
        now = timezone.now()
        rejected = self.leave(status=StudentLeaveRequest.Status.REJECTED,
                              stage=StudentLeaveRequest.Stage.CLOSED, tutor_reviewed_at=now)
        self.assertEqual(self.get(self.tutor, "tutor/leave"), [])
        self.assertEqual(self.get(self.tutor, "tutor/leave", decided=True), [rejected.id])

    def test_other_hod_sees_nothing(self):
        self.od(status=ODRequest.Status.APPROVED, hod_reviewed_at=timezone.now())
        self.assertEqual(self.get(self.other_hod, "hod/od", decided=True), [])
