"""Step 7.1 - Excel/CSV preview and import as a background (Celery) job."""
import datetime
import io
from unittest import mock

from openpyxl import Workbook, load_workbook

from config import celery_app
from core.dataio.tasks import rows_from_json, rows_to_json
from core.dataio.tests import ImporterTestBase
from core.users.models import User
from modules.automation.background import start_job
from modules.automation.models import BackgroundJob


class BackgroundImportTests(ImporterTestBase):

    def setUp(self):
        super().setUp()
        # run Celery tasks inside the test (no worker needed)
        from config.celery import set_eager      # works on Celery 5.5 and 5.7
        self.addCleanup(set_eager, set_eager(True))
        self.as_user(self.admin)

    # ---------- helpers ----------
    def student_file(self, change=None):
        """The students export, optionally with one cell changed, as an upload."""
        r = self.client.get("/api/dataio/students/export/")
        self.assertEqual(r.status_code, 200)
        rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
        if change:
            change(rows)
        wb = Workbook()
        for row in rows:
            wb.active.append(list(row))
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "students.xlsx"
        return buf

    def start(self, buf, commit, key="students"):
        return self.client.post(f"/api/dataio/{key}/start/",
                                {"mode": "upsert", "commit": "true" if commit else "false",
                                 "file": buf}, format="multipart")

    def job_of(self, r):
        return BackgroundJob.objects.get(id=r.data["job_id"])

    def rename_first_student(self, rows):
        col = list(rows[0]).index("Name")
        row = list(rows[1])
        row[col] = "Renamed"
        rows[1] = tuple(row)

    # ---------- tests ----------
    def test_preview_job_gives_the_report(self):
        r = self.start(self.student_file(), commit=False)
        self.assertEqual(r.status_code, 202)
        job = self.job_of(r)
        self.assertEqual((job.status, job.kind), ("done", "dataio_preview"))
        self.assertEqual((job.result["counts"]["total"], job.result["counts"]["error"]), (2, 0))
        self.assertFalse(job.result["saved"])

    def test_import_job_saves(self):
        r = self.start(self.student_file(self.rename_first_student), commit=True)
        job = self.job_of(r)
        self.assertEqual((job.status, job.kind, job.lock_key), ("done", "dataio_import", "dataio:students"))
        self.assertTrue(job.result["saved"])
        self.assertTrue(User.objects.filter(role="student", first_name="Renamed").exists())

    def test_file_with_errors_saves_nothing(self):
        def break_email(rows):
            col = list(rows[0]).index("Email")
            row = list(rows[1])
            row[col] = "not-an-email"
            rows[1] = tuple(row)
            self.rename_first_student(rows)
        job = self.job_of(self.start(self.student_file(break_email), commit=True))
        self.assertEqual(job.status, "done")                 # the check finished ...
        self.assertFalse(job.result["saved"])                # ... but nothing was saved
        self.assertGreater(job.result["counts"]["error"], 0)
        self.assertFalse(User.objects.filter(first_name="Renamed").exists())

    def test_second_import_of_same_type_is_refused(self):
        running = start_job("dataio_import", self.admin, "dataio:students")
        r = self.start(self.student_file(), commit=True)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["job_id"], str(running.id))

    def test_preview_is_not_blocked_by_a_running_import(self):
        start_job("dataio_import", self.admin, "dataio:students")
        self.assertEqual(self.start(self.student_file(), commit=False).status_code, 202)

    def test_bad_file_is_refused_before_any_job(self):
        buf = io.BytesIO(b"hello")
        buf.name = "notes.txt"
        r = self.start(buf, commit=True)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(BackgroundJob.objects.count(), 0)

    def test_permissions_unchanged(self):
        self.as_user(self.s1)                                # a student
        r = self.start(self.student_file_as_admin(), commit=True)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(BackgroundJob.objects.count(), 0)

    def student_file_as_admin(self):
        self.as_user(self.admin)
        buf = self.student_file()
        self.as_user(self.s1)
        return buf

    def test_redis_down_gives_503_and_failed_job(self):
        with mock.patch("core.dataio.tasks.run_import.delay", side_effect=ConnectionError("down")):
            r = self.start(self.student_file(), commit=True)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self.job_of(r).status, "failed")
        self.assertEqual(self.start(self.student_file(), commit=True).status_code, 202)   # lock is free

    def test_uploaded_rows_are_not_kept_after_the_job(self):
        job = self.job_of(self.start(self.student_file(), commit=False))
        self.assertEqual(job.params["rows"], [])
        self.assertEqual(job.params["key"], "students")

    def test_excel_dates_survive_the_trip_to_the_worker(self):
        rows = [(2, {"name": "A", "dob": datetime.date(2007, 6, 14), "n": "5"})]
        self.assertEqual(rows_from_json(rows_to_json(rows)), rows)

    def test_status_api_returns_the_report(self):
        job_id = self.start(self.student_file(), commit=False).data["job_id"]
        r = self.client.get(f"/api/jobs/{job_id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["result"]["counts"]["total"], 2)

    def test_old_waiting_endpoints_are_gone(self):          # removed 20-11-2026
        for url in ("/api/dataio/students/import/", "/api/dataio/students/preview/"):
            r = self.client.post(url, {"mode": "upsert", "file": self.student_file()},
                                 format="multipart")
            self.assertEqual(r.status_code, 404, url)


    # ---------- STEP 7.2: temporary passwords of new accounts are not kept ----------
    def new_student_file(self):
        def add_row(rows):
            header = list(rows[0])
            new = [""] * len(header)
            for label, value in (("Roll number", ""), ("Username", "newkid"),
                                 ("Name", "New Kid"), ("Email", "newkid@example.com")):
                new[header.index(label)] = value
            for label in header:                      # copy course/year/semester etc. from row 1
                if new[header.index(label)] == "" and label not in ("Roll number", "Username", "Email", "Name"):
                    new[header.index(label)] = rows[1][header.index(label)]
            rows.append(tuple(new))
        return self.student_file(add_row)

    def test_passwords_only_once_and_only_to_the_owner(self):
        r = self.start(self.new_student_file(), commit=True)
        job = self.job_of(r)
        self.assertTrue(job.result.get("saved"), job.result)
        self.assertTrue(job.result.get("extra"))                  # stored until first read

        other_admin = User.objects.create_user("admin2", password="x", role="admin", sub_role="super_admin")
        self.as_user(other_admin)
        seen_by_other = self.client.get(f"/api/jobs/{job.id}/").data["result"]
        self.assertNotIn("extra", seen_by_other)                  # never to someone else

        self.as_user(self.admin)
        first = self.client.get(f"/api/jobs/{job.id}/").data["result"]
        self.assertTrue(first["extra"])                           # the owner gets them once
        self.assertIn("password", first["extra"][0])
        second = self.client.get(f"/api/jobs/{job.id}/").data["result"]
        self.assertNotIn("extra", second)                         # ... and then they are gone
        job.refresh_from_db()
        self.assertNotIn("extra", job.result)
        self.assertTrue(job.result["saved"])