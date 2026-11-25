"""
WAVE 1 TESTS - student leave (student -> class in-charge -> HOD).

Run:  python manage.py test modules.attendance.tests_student_leave -v 2
"""
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Year, YearTutor
from core.notifications.models import Notification
from core.users.models import Department, ParentProfile, User
from modules.attendance.models import ODRequest, StudentLeaveRequest

TODAY = timezone.localdate()


def day(n):
    return str(TODAY + timedelta(days=n))


class StudentLeaveTests(TestCase):

    def setUp(self):
        media_root = tempfile.mkdtemp(prefix="kbtc-leave-")        # uploads never touch real media/
        media = override_settings(MEDIA_ROOT=media_root, MULTITENANT_RELATIVE_MEDIA_ROOT="%s")
        media.enable()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        self.addCleanup(media.disable)
        mk = User.objects.create_user
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.other_hod = mk("hod2", password="x", role="teacher")
        Department.objects.create(name="Civil", code="CE", hod=self.other_hod)
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.tutor = mk("tutor1", password="x", role="teacher", department=self.dept)
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.year)
        other_course = Course.objects.create(name="B.E Civil")
        other_year = Year.objects.create(course=other_course, year_number=2)
        self.other_tutor = mk("tutor2", password="x", role="teacher")
        YearTutor.objects.create(teacher=self.other_tutor, course=other_course, year=other_year)
        self.student = mk("stu1", password="x", role="student", department=self.dept,
                          course=self.course, year=2)
        self.classmate = mk("stu2", password="x", role="student", department=self.dept,
                            course=self.course, year=2)
        self.parent = mk("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)

    def as_(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def apply(self, user=None, **over):
        body = dict(leave_type="personal", from_date=day(1), to_date=day(2), reason="Sister's wedding")
        body.update(over)
        return self.as_(user or self.student).post("/api/users/leave/create/", body, format="multipart")

    def act(self, who, url, pk, action="approve", remark=""):
        return self.as_(who).post(f"/api/users/{url}/leave/{pk}/action/",
                                  {"action": action, "remark": remark}, format="json")

    # ---------------- the full road ----------------
    def test_student_tutor_hod_approve(self):
        r = self.apply()
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        self.assertTrue(Notification.objects.filter(recipient=self.tutor, notification_type="leave").exists())

        self.assertEqual([x["id"] for x in self.as_(self.tutor).get("/api/users/tutor/leave/").json()], [pk])
        self.assertEqual(self.as_(self.hod).get("/api/users/hod/leave/").json(), [])   # not yet
        self.assertEqual(self.act(self.tutor, "tutor", pk).status_code, 200)

        self.assertEqual([x["id"] for x in self.as_(self.hod).get("/api/users/hod/leave/").json()], [pk])
        r = self.act(self.hod, "hod", pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "approved")
        self.assertTrue(Notification.objects.filter(recipient=self.student, title="Leave approved").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.parent, title="Leave approved").exists())

    def test_reject_needs_a_remark_and_closes_it(self):
        pk = self.apply().json()["id"]
        r = self.act(self.tutor, "tutor", pk, action="reject")
        self.assertEqual(r.status_code, 400)
        self.assertIn("why", r.json()["detail"])
        r = self.act(self.tutor, "tutor", pk, action="reject", remark="Exam that week")
        self.assertEqual(r.json()["status"], "rejected")
        self.assertEqual(self.as_(self.hod).get("/api/users/hod/leave/").json(), [])
        self.assertTrue(Notification.objects.filter(recipient=self.student,
                                                    title="Leave request rejected").exists())

    def test_no_class_in_charge_goes_straight_to_the_hod(self):
        YearTutor.objects.all().delete()
        pk = self.apply().json()["id"]
        self.assertEqual(StudentLeaveRequest.objects.get(pk=pk).stage, "awaiting_hod")
        self.assertEqual(self.act(self.hod, "hod", pk).status_code, 200)

    # ---------------- who may do what ----------------
    def test_only_students_apply(self):
        self.assertEqual(self.apply(user=self.tutor).status_code, 403)
        self.assertEqual(self.apply(user=self.parent).status_code, 403)

    def test_other_class_and_department_cannot_review(self):
        pk = self.apply().json()["id"]
        self.assertEqual(self.as_(self.other_tutor).get("/api/users/tutor/leave/").json(), [])
        self.assertEqual(self.act(self.other_tutor, "tutor", pk).status_code, 404)
        self.assertEqual(self.act(self.hod, "hod", pk).status_code, 404)        # tutor first
        self.act(self.tutor, "tutor", pk)
        self.assertEqual(self.act(self.other_hod, "hod", pk).status_code, 404)
        self.assertEqual(StudentLeaveRequest.objects.get(pk=pk).status, "pending")

    def test_cancel_only_own_pending(self):
        pk = self.apply().json()["id"]
        self.assertEqual(self.as_(self.classmate).post(f"/api/users/leave/{pk}/cancel/").status_code, 404)
        self.assertEqual(self.as_(self.student).post(f"/api/users/leave/{pk}/cancel/").json()["status"],
                         "cancelled")
        self.assertEqual(self.as_(self.student).post(f"/api/users/leave/{pk}/cancel/").status_code, 400)
        self.assertEqual(self.as_(self.tutor).get("/api/users/tutor/leave/").json(), [])

    def test_students_see_only_their_own(self):
        self.apply()
        self.assertEqual(len(self.as_(self.student).get("/api/users/leave/").json()), 1)
        self.assertEqual(self.as_(self.classmate).get("/api/users/leave/").json(), [])

    # ---------------- rules ----------------
    def test_date_rules(self):
        for over, reason in (({"from_date": day(3), "to_date": day(1)}, "before the start"),
                             ({"from_date": day(1), "to_date": day(31)}, "at most 30 days"),
                             ({"from_date": day(-8), "to_date": day(-8)}, "7 days ago"),
                             ({"reason": "  "}, "reason")):
            r = self.apply(**over)
            self.assertEqual(r.status_code, 400, over)
            self.assertIn(reason, str(r.content), over)
        self.assertEqual(self.apply(from_date=day(-7), to_date=day(-7)).status_code, 201)   # recent sick day

    def test_long_sick_leave_needs_a_certificate(self):
        r = self.apply(leave_type="sick", from_date=day(0), to_date=day(2))
        self.assertEqual(r.status_code, 400)
        self.assertIn("medical certificate", str(r.content))
        cert = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 ok", content_type="application/pdf")
        self.assertEqual(self.apply(leave_type="sick", from_date=day(0), to_date=day(2), proof=cert).status_code, 201)
        self.assertEqual(self.apply(leave_type="sick", from_date=day(5), to_date=day(6)).status_code, 201)

    def test_proof_must_be_pdf_or_image(self):
        bad = SimpleUploadedFile("cert.exe", b"MZ", content_type="application/octet-stream")
        r = self.apply(proof=bad)
        self.assertEqual(r.status_code, 400)
        self.assertIn("PDF, JPG or PNG", str(r.content))

    def test_no_overlap_with_leave_or_on_duty(self):
        self.assertEqual(self.apply().status_code, 201)
        r = self.apply(from_date=day(2), to_date=day(3))
        self.assertEqual(r.status_code, 400)
        self.assertIn("already have a leave", str(r.content))
        ODRequest.objects.create(student=self.student, from_date=day(10), to_date=day(10),
                                 category="sports", reason="match", status="approved")
        r = self.apply(from_date=day(9), to_date=day(11))
        self.assertIn("on-duty", str(r.content))

    # ---------------- attendance register ----------------
    def test_register_lists_students_on_approved_leave(self):
        pk = self.apply(from_date=day(1), to_date=day(1)).json()["id"]
        self.apply(user=self.classmate, from_date=day(1), to_date=day(1))          # stays pending
        url = f"/api/attendance/od_students/?date={day(1)}"
        self.assertEqual(self.as_(self.tutor).get(url).json()["leave_ids"], [])
        self.act(self.tutor, "tutor", pk)
        self.act(self.hod, "hod", pk)
        data = self.as_(self.tutor).get(url).json()
        self.assertEqual(data["leave_ids"], [self.student.id])
        self.assertEqual(data["student_ids"], [])                                   # not on duty

    def test_proof_file_rule(self):
        from core.tenants.file_access import can_open
        cert = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 ok", content_type="application/pdf")
        pk = self.apply(leave_type="sick", from_date=day(0), to_date=day(2), proof=cert).json()["id"]
        name = StudentLeaveRequest.objects.get(pk=pk).proof.name
        for user in (self.student, self.parent, self.tutor, self.hod):
            self.assertTrue(can_open(user, name), user.username)
        for user in (self.classmate, self.other_tutor, self.other_hod):
            self.assertFalse(can_open(user, name), user.username)
