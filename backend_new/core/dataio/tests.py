"""
Import & Export: the importers added for meeting point 2.

  teaching_assignments, exam_schedule, prior_academics,
  drive_attendance, offers, round_results

Each test drives the real API (/api/dataio/<key>/...) with a real Excel
file, the same way the ImportExport menu does.

Run:  python manage.py test core.dataio -v 2
"""
import datetime
import decimal
import io

from django.test import TestCase
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department, PriorAcademics, User


def next_weekday(start, weekday):
    """First date on/after `start` that falls on `weekday` (Mon=0)."""
    return start + datetime.timedelta(days=(weekday - start.weekday()) % 7)


class _Answer:
    """Shaped like the old /import/ and /preview/ answer, for the tests."""
    content = b""

    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data

    def json(self):
        return self.data


def post_upload(client, key, data, commit):
    """
    The old waiting /import/ and /preview/ URLs were removed (20-11-2026).
    Upload through /start/ exactly like the screen does, run the job inside
    the test (no worker needed) and return what the old URL used to answer:
    status 200 (400 when a save failed) and .data = the report.
    Errors found before the job starts (403, bad file, ...) are returned as is.
    """
    from modules.automation.models import BackgroundJob

    from config.celery import set_eager      # works on Celery 5.5 and 5.7
    eager = set_eager(True)
    try:
        r = client.post(f"/api/dataio/{key}/start/",
                        {**data, "commit": "true" if commit else "false"}, format="multipart")
    finally:
        set_eager(eager)
    if r.status_code != 202:
        return r
    job = BackgroundJob.objects.get(id=r.data["job_id"])
    if job.status != "done":
        return _Answer(500, {"detail": job.error, "status": job.status})
    report = dict(job.result or {})
    report.pop("_one_time", None)
    return _Answer(400 if commit and not report.get("saved") else 200, report)


class ImporterTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.cse = Department.objects.create(name="Computer Science", code="CS")
        self.course = Course.objects.create(name="B.E Mechanical")
        self.y2 = Year.objects.create(course=self.course, year_number=2)
        self.thermo = Subject.objects.create(name="Thermodynamics", code="ME301", year=self.y2, semester=3)
        self.fluid = Subject.objects.create(name="Fluid Mechanics", code="ME302", year=self.y2, semester=3)
        self.admin = User.objects.create_user(username="admin1", password="x", role="admin", sub_role="super_admin")
        self.teacher = User.objects.create_user(username="priya", password="x", role="teacher",
                                                department=self.dept, employee_id="TCH900")
        self.s1 = User.objects.create_user(username="s1", password="x", role="student", department=self.dept,
                                           course=self.course, year=2, semester=3, first_name="Aarthi")
        self.s2 = User.objects.create_user(username="s2", password="x", role="student", department=self.cse,
                                           course=self.course, year=2, semester=3, first_name="Bala")
        self.s1.refresh_from_db()
        self.s2.refresh_from_db()

    # ---------- helpers ----------
    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def headers(self, key, options=None):
        r = self.client.get(f"/api/dataio/{key}/template/", options or {})
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:300]))
        return [c.value for c in next(load_workbook(io.BytesIO(r.content)).active.iter_rows(max_row=1))]

    def upload(self, key, rows, options=None, commit=True):
        wb = Workbook()
        ws = wb.active
        ws.append(self.headers(key, options))
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = f"{key}.xlsx"
        return post_upload(self.client, key, {**(options or {}), "mode": "upsert", "file": buf}, commit)

    def export_rows(self, key, params=None):
        r = self.client.get(f"/api/dataio/{key}/export/", params or {})
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:300]))
        return list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))

    def assert_saved(self, r):
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:400]))
        self.assertTrue(r.data.get("saved"), r.data)

    def assert_refused(self, r, text):
        body = str(getattr(r, "data", r.content)).lower()
        self.assertFalse(getattr(r, "data", {}).get("saved", False), body)
        self.assertIn(text.lower(), body)


# ======================================================================
class TeachingAssignmentImportTests(ImporterTestBase):

    def test_import_by_code_and_employee_id_then_skip_duplicate(self):
        self.as_user(self.admin)
        row = ["B.E Mechanical", 2, 3, "ME301", "TCH900", "Priya"]
        self.assert_saved(self.upload("teaching_assignments", [row]))
        self.assertEqual(TeachingAssignment.objects.filter(subject=self.thermo, teacher=self.teacher).count(), 1)
        # same file again: skipped, never duplicated
        r = self.upload("teaching_assignments", [row])
        self.assert_saved(r)
        self.assertEqual(r.data["counts"]["skip"], 1)
        self.assertEqual(TeachingAssignment.objects.count(), 1)

    def test_unknown_teacher_and_wrong_semester_refused(self):
        self.as_user(self.admin)
        self.assert_refused(self.upload("teaching_assignments", [["B.E Mechanical", 2, 3, "ME301", "NOPE1", ""]]),
                            "teacher 'nope1' not found")
        self.assert_refused(self.upload("teaching_assignments", [["B.E Mechanical", 2, 5, "ME301", "TCH900", ""]]),
                            "doesn't belong to year 2")

    def test_export_round_trip(self):
        TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y2, subject=self.fluid)
        rows = self.as_user(self.admin) and self.export_rows("teaching_assignments")
        self.assertIn(("B.E Mechanical", 2, 3, "ME302", "TCH900", "priya"), [tuple(r) for r in rows])

    def test_teacher_cannot_use(self):
        r = self.as_user(self.teacher).get("/api/dataio/teaching_assignments/template/")
        self.assertEqual(r.status_code, 403)


# ======================================================================
class ExamScheduleImportTests(ImporterTestBase):

    def setUp(self):
        super().setUp()
        self.mon = next_weekday(datetime.date.today() + datetime.timedelta(days=30), 0)
        self.sat = self.mon + datetime.timedelta(days=5)

    def d(self, day):
        return day.strftime("%d-%m-%Y")

    def test_import_and_update_schedule(self):
        from modules.exams.models import ExamSchedule
        self.as_user(self.admin)
        self.assert_saved(self.upload("exam_schedule", [
            ["B.E Mechanical", 2, 3, "ME301", "", self.d(self.mon), "FN"],
            ["B.E Mechanical", 2, 3, "Fluid Mechanics", "", self.d(self.mon), "AN"],
        ]))
        self.assertEqual(ExamSchedule.objects.count(), 2)
        # move Thermodynamics to Tuesday - updated, not duplicated
        tue = self.mon + datetime.timedelta(days=1)
        self.assert_saved(self.upload("exam_schedule", [["B.E Mechanical", 2, 3, "ME301", "", self.d(tue), "FN"]]))
        self.assertEqual(ExamSchedule.objects.get(subject=self.thermo).exam_date, tue)
        self.assertEqual(ExamSchedule.objects.count(), 2)

    def test_weekend_refused(self):
        self.as_user(self.admin)
        self.assert_refused(self.upload("exam_schedule", [["B.E Mechanical", 2, 3, "ME301", "", self.d(self.sat), "FN"]]),
                            "no exams on weekends")

    def test_clash_inside_file_refused(self):
        self.as_user(self.admin)
        r = self.upload("exam_schedule", [
            ["B.E Mechanical", 2, 3, "ME301", "", self.d(self.mon), "FN"],
            ["B.E Mechanical", 2, 3, "ME302", "", self.d(self.mon), "FN"],
        ])
        self.assert_refused(r, "clash")
        self.assertEqual(r.data["counts"]["error"], 2)

    def test_clash_with_saved_schedule_refused(self):
        from modules.exams.models import ExamSchedule
        ExamSchedule.objects.create(subject=self.fluid, semester=3, exam_date=self.mon, session="FN")
        self.as_user(self.admin)
        self.assert_refused(self.upload("exam_schedule", [["B.E Mechanical", 2, 3, "ME301", "", self.d(self.mon), "FN"]]),
                            "fluid mechanics is also on")

    def test_swapping_two_saved_exams_in_one_file_is_fine(self):
        """A moves to B's slot while B moves away - no false clash."""
        from modules.exams.models import ExamSchedule
        tue = self.mon + datetime.timedelta(days=1)
        ExamSchedule.objects.create(subject=self.thermo, semester=3, exam_date=self.mon, session="FN")
        ExamSchedule.objects.create(subject=self.fluid, semester=3, exam_date=tue, session="FN")
        self.as_user(self.admin)
        self.assert_saved(self.upload("exam_schedule", [
            ["B.E Mechanical", 2, 3, "ME301", "", self.d(tue), "FN"],
            ["B.E Mechanical", 2, 3, "ME302", "", self.d(self.mon), "FN"],
        ]))
        self.assertEqual(ExamSchedule.objects.get(subject=self.thermo).exam_date, tue)

    def test_teacher_cannot_use(self):
        self.assertEqual(self.as_user(self.teacher).get("/api/dataio/exam_schedule/template/").status_code, 403)


# ======================================================================
class PlacementImportTestBase(ImporterTestBase):
    def setUp(self):
        super().setUp()
        from modules.placement.models import Application, Company, Drive, JobRole, PlacementCoordinator
        self.officer = User.objects.create_user(username="officer", password="x", role="admin",
                                                sub_role="placement_officer")
        self.coord = User.objects.create_user(username="coord", password="x", role="teacher", department=self.dept)
        PlacementCoordinator.objects.create(teacher=self.coord, department=self.dept)
        company = Company.objects.create(name="Acme Engineering", category="core")
        self.drive = Drive.objects.create(company=company, status="published",
                                          drive_date=datetime.date.today())
        self.role = JobRole.objects.create(drive=self.drive, title="Graduate Engineer Trainee",
                                           package_lpa=decimal.Decimal("4.50"))
        self.app1 = Application.objects.create(student=self.s1, job_role=self.role, status="applied")
        self.app2 = Application.objects.create(student=self.s2, job_role=self.role, status="applied")


class PriorAcademicsImportTests(PlacementImportTestBase):
    COLS = 13

    def row(self, roll, tenth="88.4", lateral="No", twelfth="91.25", diploma="", verified=""):
        r = [""] * self.COLS
        r[0], r[2], r[5], r[6], r[9], r[12] = roll, tenth, lateral, twelfth, diploma, verified
        return r

    def test_officer_imports_marks(self):
        self.as_user(self.officer)
        self.assert_saved(self.upload("prior_academics", [self.row(self.s1.roll_number)]))
        rec = PriorAcademics.objects.get(student=self.s1)
        self.assertEqual(rec.tenth_percent, decimal.Decimal("88.40"))
        self.assertEqual(rec.twelfth_percent, decimal.Decimal("91.25"))
        self.assertFalse(rec.verified)

    def test_model_rule_regular_student_needs_12th(self):
        self.as_user(self.officer)
        self.assert_refused(self.upload("prior_academics", [self.row(self.s1.roll_number, twelfth="")]),
                            "12th percentage is required")

    def test_lateral_entry_needs_diploma(self):
        self.as_user(self.officer)
        self.assert_refused(self.upload("prior_academics", [self.row(self.s1.roll_number, lateral="Yes", twelfth="")]),
                            "diploma percentage is required")
        self.assert_saved(self.upload("prior_academics", [
            self.row(self.s1.roll_number, lateral="Yes", twelfth="", diploma="78")]))

    def test_verified_yes_sets_verifier_and_changed_marks_reset_it(self):
        self.as_user(self.officer)
        self.assert_saved(self.upload("prior_academics", [self.row(self.s1.roll_number, verified="Yes")]))
        rec = PriorAcademics.objects.get(student=self.s1)
        self.assertTrue(rec.verified)
        self.assertEqual(rec.verified_by, self.officer)
        # marks change, Verified left blank -> must be checked again
        self.assert_saved(self.upload("prior_academics", [self.row(self.s1.roll_number, tenth="70")]))
        rec.refresh_from_db()
        self.assertFalse(rec.verified)
        self.assertIsNone(rec.verified_by)

    def test_coordinator_limited_to_own_department(self):
        self.as_user(self.coord)
        self.assert_saved(self.upload("prior_academics", [self.row(self.s1.roll_number)]))
        self.assert_refused(self.upload("prior_academics", [self.row(self.s2.roll_number)]),
                            "not a student you manage")
        rolls = [r[0] for r in self.export_rows("prior_academics")[1:]]
        self.assertEqual(rolls, [self.s1.roll_number])

    def test_student_cannot_use(self):
        self.assertEqual(self.as_user(self.s1).get("/api/dataio/prior_academics/template/").status_code, 403)


class DriveAttendanceImportTests(PlacementImportTestBase):

    def opts(self):
        return {"job_role": self.role.id}

    def test_present_creates_od_like_the_screen(self):
        from modules.placement.models import DriveAttendance
        self.as_user(self.officer)
        self.assert_saved(self.upload("drive_attendance", [[self.s1.roll_number, "", "P", ""],
                                                           [self.s2.roll_number, "", "A", "sick"]], self.opts()))
        a1 = DriveAttendance.objects.get(application=self.app1)
        self.assertEqual(a1.status, "present")
        self.assertIsNotNone(a1.od_request_id)          # same service as the screen
        self.assertEqual(DriveAttendance.objects.get(application=self.app2).remarks, "sick")

    def test_present_to_absent_cancels_od(self):
        from modules.attendance.models import ODRequest
        self.as_user(self.officer)
        self.assert_saved(self.upload("drive_attendance", [[self.s1.roll_number, "", "P", ""]], self.opts()))
        self.assert_saved(self.upload("drive_attendance", [[self.s1.roll_number, "", "A", ""]], self.opts()))
        od = ODRequest.objects.get(student=self.s1)
        self.assertEqual(od.status, ODRequest.Status.CANCELLED)

    def test_student_who_did_not_apply_refused(self):
        from modules.placement.models import Application
        Application.objects.filter(pk=self.app2.pk).update(status="opted_out")
        self.as_user(self.officer)
        self.assert_refused(self.upload("drive_attendance", [[self.s2.roll_number, "", "P", ""]], self.opts()),
                            "not on this list")

    def test_coordinator_sees_only_own_department(self):
        self.as_user(self.coord)
        rolls = [r[0] for r in self.export_rows("drive_attendance", self.opts())[1:]]
        self.assertEqual(rolls, [self.s1.roll_number])


class OfferImportTests(PlacementImportTestBase):

    def opts(self):
        return {"job_role": self.role.id}

    def test_blank_package_uses_role_package_then_update(self):
        from modules.placement.models import Offer
        self.as_user(self.officer)
        self.assert_saved(self.upload("offers", [[self.s1.roll_number, "", "", "01-07-2027", ""]], self.opts()))
        offer = Offer.objects.get(application=self.app1)
        self.assertEqual(offer.package_lpa, decimal.Decimal("4.50"))
        self.assertEqual(offer.status, "offered")
        # a later file with only remarks keeps the package
        self.assert_saved(self.upload("offers", [[self.s1.roll_number, "", "", "", "via campus"]], self.opts()))
        offer.refresh_from_db()
        self.assertEqual(offer.package_lpa, decimal.Decimal("4.50"))
        self.assertEqual(offer.remarks, "via campus")

    def test_import_never_changes_student_decision(self):
        from modules.placement.models import Offer
        Offer.objects.create(application=self.app1, package_lpa=4, status="accepted")
        self.as_user(self.officer)
        self.assert_saved(self.upload("offers", [[self.s1.roll_number, "", "5", "", ""]], self.opts()))
        self.assertEqual(Offer.objects.get(application=self.app1).status, "accepted")

    def test_coordinator_cannot_record_offers(self):
        r = self.as_user(self.coord).get("/api/dataio/offers/template/", self.opts())
        self.assertEqual(r.status_code, 403)


class RoundResultImportTests(PlacementImportTestBase):

    def setUp(self):
        super().setUp()
        from modules.placement.models import DriveRound
        self.r1 = DriveRound.objects.create(job_role=self.role, order=1, name="Aptitude")
        self.r2 = DriveRound.objects.create(job_role=self.role, order=2, name="Interview")

    def test_round_one_then_only_cleared_reach_round_two(self):
        from modules.placement.models import RoundResult
        self.as_user(self.officer)
        self.assert_saved(self.upload("round_results", [[self.s1.roll_number, "", "Cleared", ""],
                                                        [self.s2.roll_number, "", "Not cleared", ""]],
                                      {"round": self.r1.id}))
        self.assertEqual(RoundResult.objects.filter(round=self.r1).count(), 2)
        # s2 did not clear round 1 -> not in round 2
        self.assert_refused(self.upload("round_results", [[self.s2.roll_number, "", "Cleared", ""]],
                                        {"round": self.r2.id}), "not on this list")
        self.assert_saved(self.upload("round_results", [[self.s1.roll_number, "", "C", ""]], {"round": self.r2.id}))

    def test_bad_result_word_refused(self):
        self.as_user(self.officer)
        self.assert_refused(self.upload("round_results", [[self.s1.roll_number, "", "maybe", ""]],
                                        {"round": self.r1.id}), "not a valid result")


# ======================================================================
class ScreenStillWorksTests(PlacementImportTestBase):
    """The placement screens now call the shared service functions."""

    def test_screen_mark_attendance(self):
        r = self.as_user(self.officer).post(f"/api/placement/roles/{self.role.id}/attendance/",
                                            {"application": self.app1.id, "status": "present"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "present")

    def test_screen_record_offer(self):
        r = self.as_user(self.officer).post(f"/api/placement/roles/{self.role.id}/offers/",
                                            {"application": self.app1.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(decimal.Decimal(str(r.data["package_lpa"])), decimal.Decimal("4.50"))

    def test_screen_round_results(self):
        from modules.placement.models import DriveRound, RoundResult
        rd = DriveRound.objects.create(job_role=self.role, order=1, name="Aptitude")
        r = self.as_user(self.officer).post(f"/api/placement/rounds/{rd.id}/results/",
                                            {"results": [{"application": self.app1.id, "status": "cleared"}]},
                                            format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(RoundResult.objects.get(round=rd).status, "cleared")
