"""
Attendance Import/Export must follow the same window as the register
(#46): a file can't change a locked period, can't change a saved period
without a reason, and can't enter a class after the late-entry deadline.

Run:  python manage.py test modules.attendance -v 2
"""
import datetime
import io

from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.attendance.models import Attendance, AttendanceCorrection


class AttendanceImportWindowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept = Department.objects.create(name="Mechanical", code="ME")
        course = Course.objects.create(name="B.E Mechanical")
        y1 = Year.objects.create(course=course, year_number=1)
        subject = Subject.objects.create(name="Applied Calculus", code="MA101", year=y1, semester=1)
        self.teacher = User.objects.create_user(username="t1", password="x", role="teacher", department=dept)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=course, year=y1, subject=subject)
        self.s1 = User.objects.create_user(username="s1", password="x", role="student", department=dept,
                                           course=course, year=1, semester=1, first_name="Aarthi")
        Enrollment.objects.create(student=self.s1, teaching_assignment=self.ta)
        self.s1.refresh_from_db()
        self.client.force_authenticate(user=self.teacher)
        self.today = timezone.localdate()

    # ---------- helpers ----------
    def _headers(self):
        t = self.client.get("/api/dataio/attendance/template/", {"teaching_assignment": self.ta.id})
        self.assertEqual(t.status_code, 200)
        return [c.value for c in next(load_workbook(io.BytesIO(t.content)).active.iter_rows(max_row=1))]

    def _file(self, day, period, status):
        wb = Workbook()
        ws = wb.active
        ws.append(self._headers())
        ws.append([self.s1.roll_number, "Aarthi", day.strftime("%d-%m-%Y"), period, status])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "attendance.xlsx"
        return buf

    def _import(self, day, period, status):
        from core.dataio.tests import post_upload    # the waiting /import/ URL was removed
        return post_upload(self.client, "attendance",
                           {"teaching_assignment": self.ta.id, "mode": "upsert",
                            "file": self._file(day, period, status)}, commit=True)

    def _saved(self, day, status, saved_on):
        a = Attendance.objects.create(teaching_assignment=self.ta, student=self.s1, date=day, hour=1,
                                      status=status, marked_by=self.teacher)
        Attendance.objects.filter(pk=a.pk).update(
            created_at=timezone.make_aware(datetime.datetime.combine(saved_on, datetime.time(10))))
        return a

    def _status(self, day):
        return Attendance.objects.get(student=self.s1, date=day, hour=1).status

    # ---------- tests ----------
    def test_import_into_todays_unmarked_period_works(self):
        r = self._import(self.today, 1, "P")
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:400]))
        self.assertEqual(self._status(self.today), "present")

    def test_import_cannot_change_a_locked_period(self):
        old = self.today - datetime.timedelta(days=30)
        self._saved(old, "absent", saved_on=old)
        r = self._import(old, 1, "P")
        self.assertNotEqual(r.status_code, 200)
        self.assertIn("locked", str(r.data).lower())
        self.assertEqual(self._status(old), "absent")          # untouched

    def test_import_cannot_change_a_saved_period_without_reason(self):
        day = self.today - datetime.timedelta(days=1)
        self._saved(day, "absent", saved_on=day)
        r = self._import(day, 1, "P")
        self.assertNotEqual(r.status_code, 200)
        self.assertIn("reason", str(r.data).lower())
        self.assertEqual(self._status(day), "absent")
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_late_entry_closed_for_old_unmarked_class(self):
        old = self.today - datetime.timedelta(days=30)
        r = self._import(old, 1, "P")
        self.assertNotEqual(r.status_code, 200)
        self.assertIn("late entry is closed", str(r.data).lower())
        self.assertFalse(Attendance.objects.filter(date=old).exists())

    def test_resending_the_same_status_on_a_locked_period_is_fine(self):
        old = self.today - datetime.timedelta(days=30)
        a = self._saved(old, "absent", saved_on=old)
        r = self._import(old, 1, "A")
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:400]))
        a.refresh_from_db()
        self.assertEqual(a.status, "absent")
        self.assertEqual(a.marked_by, self.teacher)

    def test_export_still_works(self):
        self._saved(self.today, "present", saved_on=self.today)
        r = self.client.get("/api/dataio/attendance/export/",
                            {"teaching_assignment": self.ta.id,
                             "from_date": str(self.today), "to_date": str(self.today)})
        self.assertEqual(r.status_code, 200)
        rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
        self.assertEqual(len(rows), 2, rows)
