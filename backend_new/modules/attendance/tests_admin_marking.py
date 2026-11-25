"""Lead's decision: only the main admin (no sub-role), super admin and academic
admin may MARK or LOCK attendance as an admin. Exam / accounts / IQAC admins and
the placement officer are refused. Teachers still mark and lock their own class.
"""
from django.utils import timezone

from core.academics.tests_security_fixes import Base
from core.users.models import User
from modules.attendance.models import Attendance

REFUSED = "Only the academic admin or super admin can mark attendance."


class AdminMarkingTests(Base):

    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.super_admin = User.objects.create_user(username="sup", password="x", role="admin",
                                                    sub_role="super_admin")
        self.accounts = User.objects.create_user(username="acc", password="x", role="admin",
                                                 sub_role="accounts_admin")
        self.iqac = User.objects.create_user(username="iq", password="x", role="admin",
                                             sub_role="iqac_admin")

    def mark(self, user):
        return self.as_(user).post("/api/attendance/bulk_mark/", {
            "teaching_assignment": self.ta.id, "date": str(self.today), "hour": 1,
            "records": [{"student": self.student.id, "status": "present"}],
        }, format="json")

    def lock(self, user):
        return self.as_(user).post("/api/attendance/lock_session/", {
            "teaching_assignment": self.ta.id, "date": str(self.today), "hour": 1,
        }, format="json")

    def test_other_admin_types_cannot_mark(self):
        for user in (self.exam_admin, self.accounts, self.iqac, self.placement):
            r = self.mark(user)
            self.assertEqual(r.status_code, 403, user.username)
            self.assertEqual(r.data["error"], REFUSED, user.username)
        self.assertFalse(Attendance.objects.exists())          # nothing was saved

    def test_other_admin_types_cannot_lock(self):
        for user in (self.exam_admin, self.accounts, self.iqac, self.placement):
            r = self.lock(user)
            self.assertEqual(r.status_code, 403, user.username)
            self.assertEqual(r.data["error"],
                             "Only the academic admin or super admin can lock attendance.")

    def test_main_super_and_academic_admin_are_not_refused(self):
        # other rules (holiday, time window) may still apply - only the role check is tested
        for user in (self.main_admin, self.super_admin, self.academic):
            r = self.mark(user)
            self.assertNotEqual(r.status_code, 403, (user.username, getattr(r, "data", "")))
            r = self.lock(user)
            self.assertNotEqual(r.status_code, 403, (user.username, getattr(r, "data", "")))

    def test_teacher_still_marks_own_class(self):
        r = self.mark(self.teacher)
        self.assertNotEqual(r.status_code, 403, getattr(r, "data", ""))