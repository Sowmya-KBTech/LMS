"""
WAVE 2 Part 1b TESTS - the Principal approves an HOD's own leave.

Run:  python manage.py test modules.attendance.tests_hod_leave -v 2
"""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.notifications.models import Notification
from core.users.models import ActingHOD, Department, User
from modules.attendance.models import StaffLeaveRequest


def next_working_day(days_ahead=14):
    day = timezone.localdate() + datetime.timedelta(days=days_ahead)
    while day.weekday() >= 5:
        day += datetime.timedelta(days=1)
    return day


class HodLeavePrincipalTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.dept
        self.hod.save()
        self.civil = Department.objects.create(name="Civil", code="CE")
        self.backup = mk("ravi", password="x", role="teacher", department=self.dept)
        self.teacher = mk("kavya", password="x", role="teacher", department=self.dept)
        self.principal = mk("meena", password="x", role="teacher", department=self.civil)
        self.day = next_working_day()

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_principal(self, teacher):
        r = self.c(self.admin).post("/api/users/principal/assign/", {"teacher": teacher.id})
        self.assertEqual(r.status_code, 201, r.content)

    def apply(self, user=None, **extra):
        data = {"leave_type": "casual", "from_date": self.day.isoformat(), "to_date": self.day.isoformat(),
                "session": "full", "reason": "Family function"}
        if (user or self.hod) == self.hod:
            data["backup"] = self.backup.id
        data.update(extra)
        return self.c(user or self.hod).post("/api/users/staff-leave/create/", data)

    def act(self, leave_id, action, remark="", user=None, who="principal"):
        return self.c(user or self.principal).post(
            f"/api/users/{who}/staff-leave/{leave_id}/action/", {"action": action, "remark": remark})

    # ---------------------------------------------------------------- routing
    def test_hod_leave_waits_for_the_principal(self):
        self.make_principal(self.principal)
        r = self.apply()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["status"], r.json()["level"], r.json()["hod_name"]), ("pending", "principal", "meena"))
        self.assertTrue(Notification.objects.filter(recipient=self.principal,
                                                    title="HOD leave request from hodme").exists())
        self.assertIn("Principal still has to approve",
                      Notification.objects.get(recipient=self.backup).message)
        listed = self.c(self.principal).get("/api/users/principal/staff-leave/").json()
        self.assertEqual([x["id"] for x in listed], [r.json()["id"]])

    def test_without_a_principal_it_is_recorded_as_before(self):
        r = self.apply()
        self.assertEqual((r.json()["status"], r.json()["level"]), ("recorded", "hod"))

    def test_the_principals_own_hod_leave_is_recorded(self):
        self.make_principal(self.hod)                         # the HOD is also the Principal
        self.assertEqual(self.apply().json()["status"], "recorded")

    def test_preview_names_the_principal(self):
        self.make_principal(self.principal)
        p = self.c(self.hod).get(f"/api/users/staff-leave/preview/?from={self.day}&to={self.day}").json()
        self.assertEqual((p["approver"], p["approver_role"], p["approver_department"]), ("meena", "principal", None))
        t = self.c(self.teacher).get(f"/api/users/staff-leave/preview/?from={self.day}&to={self.day}").json()
        self.assertEqual((t["approver"], t["approver_role"]), ("hodme", "hod"))

    # ---------------------------------------------------------------- deciding
    def test_principal_approves(self):
        self.make_principal(self.principal)
        lid = self.apply().json()["id"]
        r = self.act(lid, "approve")
        self.assertEqual(r.status_code, 200, r.content)
        leave = StaffLeaveRequest.objects.get(id=lid)
        self.assertEqual((leave.status, leave.decided_by), ("approved", self.principal))
        self.assertTrue(Notification.objects.filter(recipient=self.hod, title="Leave approved by the Principal").exists())
        self.assertEqual(Notification.objects.filter(recipient=self.backup).count(), 2)   # applied + approved
        covering = self.c(self.backup).get("/api/users/staff-leave/covering/").json()
        self.assertEqual([x["id"] for x in covering], [lid])
        hist = self.c(self.principal).get("/api/users/principal/staff-leave/history/").json()
        self.assertEqual([x["id"] for x in hist], [lid])
        self.assertEqual(self.act(lid, "approve").status_code, 400)                     # already decided

    def test_reject_needs_a_remark_and_ends_the_acting_nomination(self):
        self.make_principal(self.principal)
        r = self.apply(nominate_acting="true")
        self.assertEqual(r.status_code, 201, r.content)
        lid = r.json()["id"]
        self.assertEqual(ActingHOD.objects.filter(leave_id=lid, ended_at__isnull=True).count(), 1)
        self.assertEqual(self.act(lid, "reject").status_code, 400)
        r = self.act(lid, "reject", "Exam week - please move the dates")
        self.assertEqual(r.json()["status"], "rejected")
        self.assertEqual(ActingHOD.objects.filter(leave_id=lid, ended_at__isnull=True).count(), 0)
        self.assertTrue(Notification.objects.filter(recipient=self.hod, title="Leave rejected by the Principal").exists())
        self.assertEqual(self.c(self.backup).get("/api/users/staff-leave/covering/").json(), [])

    def test_who_may_decide(self):
        self.make_principal(self.principal)
        lid = self.apply().json()["id"]
        # the HOD route refuses an HOD's leave, even for an HOD
        self.assertEqual(self.act(lid, "approve", user=self.hod, who="hod").status_code, 403)
        # only the Principal uses the Principal routes
        for u in (self.hod, self.backup, self.admin):
            self.assertEqual(self.act(lid, "approve", user=u).status_code, 403, u.username)
            self.assertEqual(self.c(u).get("/api/users/principal/staff-leave/").status_code, 403, u.username)
        # a normal teacher's leave stays with the HOD
        tid = self.apply(user=self.teacher).json()["id"]
        self.assertEqual(self.act(tid, "approve").status_code, 403)
        hod_list = self.c(self.hod).get("/api/users/hod/staff-leave/").json()
        self.assertEqual([x["id"] for x in hod_list], [tid])
        self.assertEqual(StaffLeaveRequest.objects.get(id=lid).status, "pending")

    def test_principal_can_open_the_leave_and_the_new_principal_decides(self):
        self.make_principal(self.principal)
        lid = self.apply().json()["id"]
        self.assertEqual(self.c(self.principal).get(f"/api/users/staff-leave/{lid}/").status_code, 200)
        self.make_principal(self.teacher)                                  # Principal changes
        self.assertEqual(self.act(lid, "approve").status_code, 403)        # old Principal: no longer
        self.assertEqual(self.act(lid, "approve", user=self.teacher).status_code, 200)

    def test_cancel_while_waiting(self):
        self.make_principal(self.principal)
        lid = self.apply().json()["id"]
        r = self.c(self.hod).post(f"/api/users/staff-leave/{lid}/cancel/")
        self.assertEqual(r.json()["status"], "cancelled")
        self.assertTrue(Notification.objects.filter(recipient=self.principal,
                                                    title="HOD leave request cancelled by hodme").exists())
        self.assertEqual(self.c(self.principal).get("/api/users/principal/staff-leave/").json(), [])

    def test_dashboard_does_not_count_it_as_waiting_at_hods(self):
        self.make_principal(self.principal)
        self.apply()
        data = self.c(self.principal).get("/api/users/principal/dashboard/").json()
        self.assertEqual(data["totals"]["pending"], 0)

    def test_an_acting_hod_does_not_get_the_hods_leave(self):
        from core.users import acting_hod
        self.make_principal(self.principal)
        lid = self.apply().json()["id"]
        today = timezone.localdate()
        acting_hod.assign(self.admin, self.dept.id, self.backup.id, today, today + datetime.timedelta(days=30),
                          "HOD away for a conference")
        listed = self.c(self.backup).get("/api/users/hod/staff-leave/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertNotIn(lid, [x["id"] for x in listed.json()])
        self.assertEqual(self.act(lid, "approve", user=self.backup, who="hod").status_code, 403)


# ====================================================================== HRIS PART A
import shutil       # noqa: E402
import tempfile     # noqa: E402

from django.core.files.uploadedfile import SimpleUploadedFile   # noqa: E402
from django.test import override_settings                       # noqa: E402

from core.tenants.file_access import can_open                    # noqa: E402
from core.users.models import FacultyProfile, LeaveRule, StaffDocument   # noqa: E402


class HrisTests(TestCase):
    """Staff records: who sees what, the service record, documents and the leave balance."""

    def setUp(self):
        media_root = tempfile.mkdtemp(prefix="kbtc-hris-")
        media = override_settings(MEDIA_ROOT=media_root, MULTITENANT_RELATIVE_MEDIA_ROOT="%s")
        media.enable()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        self.addCleanup(media.disable)
        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.hod = mk("hodme", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.hod.department = self.dept
        self.hod.save()
        self.civil = Department.objects.create(name="Civil", code="CE")
        self.teacher = mk("kavya", password="x", role="teacher", department=self.dept,
                          sub_role="assistant_professor")
        self.other = mk("anand", password="x", role="teacher", department=self.civil)
        self.day = next_working_day()

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def apply(self, day, leave_type="casual"):
        return self.c(self.teacher).post("/api/users/staff-leave/create/", {
            "leave_type": leave_type, "from_date": day.isoformat(), "to_date": day.isoformat(),
            "session": "full", "reason": "Family function"})

    # ---------------------------------------------------------------- leave balance
    def test_leave_beyond_the_balance_is_refused_and_an_adjustment_allows_it(self):
        self.c(self.admin).get("/api/users/hris/leave-rules/")           # creates the starting rules
        LeaveRule.objects.filter(leave_type="casual").update(days_per_year=1)
        self.assertEqual(self.apply(self.day).status_code, 201)           # waiting counts against the balance
        second = next_working_day(21)
        if second.year != self.day.year:
            second = self.day + datetime.timedelta(days=1)
            while second.weekday() >= 5:
                second += datetime.timedelta(days=1)
        r = self.apply(second)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("Only 0 days of casual leave are left", r.json()["leave_type"][0])
        self.assertIn("1 waiting for approval", r.json()["leave_type"][0])
        # a leave type with no limit is not checked
        LeaveRule.objects.filter(leave_type="earned").update(days_per_year=None)
        self.assertEqual(self.apply(second, "earned").status_code, 201)
        StaffLeaveRequest.objects.filter(leave_type="earned").delete()
        # only the admin adjusts; +1 casual makes room
        url = f"/api/users/hris/staff/{self.teacher.id}/leave-adjust/"
        body = {"leave_type": "casual", "days": "1", "reason": "Worked on Saturday", "year": second.year}
        self.assertEqual(self.c(self.hod).post(url, body).status_code, 403)
        self.assertEqual(self.c(self.admin).post(url, body).status_code, 201)
        self.assertEqual(self.apply(second).status_code, 201)
        bal = self.c(self.teacher).get(f"/api/users/hris/leave-balance/?year={second.year}").json()
        casual = next(r for r in bal["rows"] if r["leave_type"] == "casual")
        self.assertEqual((casual["allowed"], casual["waiting"], casual["available"]), (2, 2, 0))

    def test_leave_rules_only_the_admin_changes_them(self):
        body = {"rules": [{"leave_type": "casual", "days_per_year": 8}]}
        self.assertEqual(self.c(self.teacher).put("/api/users/hris/leave-rules/", body, format="json").status_code, 403)
        r = self.c(self.admin).put("/api/users/hris/leave-rules/",
                                   {"rules": [{"leave_type": "casual", "days_per_year": 7.3}]}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.c(self.admin).put("/api/users/hris/leave-rules/", body, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(LeaveRule.objects.get(leave_type="casual").days_per_year, 8)

    # ---------------------------------------------------------------- who sees what
    def test_directory_and_records_follow_the_department(self):
        self.assertEqual(self.c(self.teacher).get("/api/users/hris/staff/").status_code, 403)
        names = {r["name"] for r in self.c(self.hod).get("/api/users/hris/staff/").json()["rows"]}
        self.assertEqual(names, {"hodme", "kavya"})                       # not Civil
        names = {r["name"] for r in self.c(self.admin).get("/api/users/hris/staff/").json()["rows"]}
        self.assertTrue({"kavya", "anand", "hodme"} <= names)
        self.assertEqual(self.c(self.hod).get(f"/api/users/hris/staff/{self.other.id}/").status_code, 403)
        self.assertEqual(self.c(self.teacher).get(f"/api/users/hris/staff/{self.teacher.id}/").status_code, 200)
        self.assertEqual(self.c(self.teacher).get(f"/api/users/hris/staff/{self.hod.id}/").status_code, 403)
        # only the admin changes job details
        url = f"/api/users/hris/staff/{self.teacher.id}/"
        self.assertEqual(self.c(self.hod).patch(url, {"aicte_id": "1-123"}, format="json").status_code, 403)
        r = self.c(self.admin).patch(url, {"aicte_id": "1-123", "employment_type": "permanent",
                                           "designation": "librarian"}, format="json")
        self.assertEqual(r.status_code, 400)                              # not a teaching designation
        r = self.c(self.admin).patch(url, {"aicte_id": "1-123", "employment_type": "permanent"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FacultyProfile.objects.get(user=self.teacher).aicte_id, "1-123")
        self.assertEqual(self.c(self.hod).get("/api/users/hris/reports/faculty-list/").status_code, 200)
        self.assertEqual(self.c(self.teacher).get("/api/users/hris/reports/strength/").status_code, 403)

    # ---------------------------------------------------------------- service record
    def test_service_record_changes_the_account(self):
        url = f"/api/users/hris/staff/{self.teacher.id}/service/"
        promo = {"kind": "promotion", "date": "2026-06-01", "new_designation": "associate_professor"}
        self.assertEqual(self.c(self.hod).post(url, promo).status_code, 403)
        r = self.c(self.admin).post(url, promo)
        self.assertEqual(r.status_code, 201, r.content)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.sub_role, "associate_professor")
        self.assertEqual(r.json()["record"]["service"][0]["details"], "Assistant Professor → Associate Professor")
        r = self.c(self.admin).post(url, {"kind": "transfer", "date": "2026-07-01", "new_department": self.civil.id})
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.department, self.civil)
        self.c(self.admin).post(url, {"kind": "relieved", "date": "2026-08-01"})
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertEqual(str(FacultyProfile.objects.get(user=self.teacher).relieved_on), "2026-08-01")

    # ---------------------------------------------------------------- documents
    def test_documents_id_proof_is_hidden_from_the_hod(self):
        url = f"/api/users/hris/staff/{self.teacher.id}/documents/"

        def up(user, kind, name="a.pdf"):
            return self.c(user).post(url, {"kind": kind, "title": "Doc",
                                           "file": SimpleUploadedFile(name, b"%PDF-1.4 ok")}, format="multipart")
        self.assertEqual(up(self.other, "qualification").status_code, 403)
        self.assertEqual(up(self.teacher, "qualification", "a.exe").status_code, 400)
        self.assertEqual(up(self.teacher, "qualification").status_code, 201)
        self.assertEqual(up(self.teacher, "id_proof").status_code, 201)
        deg = StaffDocument.objects.get(kind="qualification").file.name
        idp = StaffDocument.objects.get(kind="id_proof").file.name
        self.assertTrue(can_open(self.hod, deg))
        self.assertFalse(can_open(self.hod, idp))
        self.assertTrue(can_open(self.teacher, idp))
        self.assertTrue(can_open(self.admin, idp))
        self.assertFalse(can_open(self.other, deg))
        listed = self.c(self.hod).get(f"/api/users/hris/staff/{self.teacher.id}/").json()["documents_list"]
        self.assertEqual([d["kind"] for d in listed], ["qualification"])
