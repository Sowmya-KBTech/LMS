"""Step 6.4 - auto-fill never overwrites changes made while the solver was running."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from ortools.sat.python import cp_model

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.users.models import Department
from modules.automation.background import start_job
from modules.automation.models import BackgroundJob
from modules.timetable.models import TimeSlot, TimetableApproval, TimetableEntry
from modules.timetable.tasks import class_fingerprint, run_autofill

User = get_user_model()
REAL_SOLVE = cp_model.CpSolver.Solve


class AutofillSafeSaveTests(TestCase):

    def setUp(self):
        dept = Department.objects.create(name="Safe Dept", code="SF")
        course = Course.objects.create(name="B.E Safe")
        self.year = Year.objects.create(course=course, year_number=1)
        self.admin = User.objects.create_user("sf_admin", "a@example.com", "pw", role="admin")
        self.hod = User.objects.create_user("sf_hod", "h@example.com", "pw", role="teacher")
        teacher = User.objects.create_user("sf_t", "t@example.com", "pw",
                                           role="teacher", department=dept)
        self.tas = []
        for i, code in enumerate(["SF101", "SF102"]):
            subj = Subject.objects.create(name=f"Subject {i}", code=code, year=self.year,
                                          semester=1, weekly_hours=2)
            self.tas.append(TeachingAssignment.objects.create(
                teacher=teacher, course=course, year=self.year, subject=subj))
        self.slots = [TimeSlot.objects.create(period_no=n, start_time=datetime.time(8 + n, 0),
                                              end_time=datetime.time(8 + n, 50))
                      for n in range(1, 5)]
        self.approval = TimetableApproval.objects.create(
            year=self.year, semester=1, course=course,
            status=TimetableApproval.Status.DRAFT)

    def job(self, user):
        return start_job("timetable_autofill", user, "",
                         {"year": self.year.id, "semester": 1})

    def entries(self):
        return TimetableEntry.objects.filter(assignment__year=self.year).count()

    def run_with(self, job, during_solve):
        """Run the task; `during_solve()` happens while the solver is thinking."""
        def solve(solver_self, model, *args, **kwargs):
            during_solve()
            return REAL_SOLVE(solver_self, model, *args, **kwargs)
        with mock.patch.object(cp_model.CpSolver, "Solve", solve):
            result = run_autofill(str(job.id))
        job.refresh_from_db()
        return result

    def test_normal_run_saves(self):
        job = self.job(self.admin)
        self.assertEqual(self.run_with(job, lambda: None), "done")
        self.assertEqual(self.entries(), 4)

    def test_entry_added_during_solve_means_nothing_saved(self):
        job = self.job(self.admin)

        def hod_adds_a_period():
            TimetableEntry.objects.create(assignment=self.tas[0], day_of_week=4,
                                          time_slot=self.slots[3])
        self.assertEqual(self.run_with(job, hod_adds_a_period), "failed")
        self.assertEqual(job.status, "failed")
        self.assertIn("changed while auto-fill was running", job.error)
        self.assertEqual(self.entries(), 1)          # only the HOD's own period

    def test_entry_moved_during_solve_means_nothing_saved(self):
        e = TimetableEntry.objects.create(assignment=self.tas[0], day_of_week=0,
                                          time_slot=self.slots[0])
        job = self.job(self.admin)

        def hod_moves_it():
            TimetableEntry.objects.filter(id=e.id).update(day_of_week=1)
        self.assertEqual(self.run_with(job, hod_moves_it), "failed")
        self.assertEqual(self.entries(), 1)

    def test_submitted_during_solve_blocks_a_non_admin(self):
        job = self.job(self.hod)

        def gets_submitted():
            TimetableApproval.objects.filter(id=self.approval.id).update(
                status=TimetableApproval.Status.SUBMITTED)
        self.assertEqual(self.run_with(job, gets_submitted), "failed")
        self.assertIn("submitted", job.error)
        self.assertEqual(self.entries(), 0)

    def test_admin_may_still_fill_a_submitted_timetable(self):
        job = self.job(self.admin)

        def gets_submitted():
            TimetableApproval.objects.filter(id=self.approval.id).update(
                status=TimetableApproval.Status.SUBMITTED)
        self.assertEqual(self.run_with(job, gets_submitted), "done")
        self.assertEqual(self.entries(), 4)

    def test_fingerprint_changes_on_add_move_delete(self):
        f0 = class_fingerprint(self.year.id, 1)
        e = TimetableEntry.objects.create(assignment=self.tas[0], day_of_week=0,
                                          time_slot=self.slots[0])
        f1 = class_fingerprint(self.year.id, 1)
        TimetableEntry.objects.filter(id=e.id).update(time_slot=self.slots[1])
        f2 = class_fingerprint(self.year.id, 1)
        e.delete()
        f3 = class_fingerprint(self.year.id, 1)
        self.assertEqual(len({f0, f1, f2}), 3)
        self.assertEqual(f0, f3)                     # back to the same timetable

    def test_other_class_changes_do_not_block(self):
        other_year = Year.objects.create(course=self.year.course, year_number=2)
        subj = Subject.objects.create(name="Other", code="SF201", year=other_year,
                                      semester=1, weekly_hours=1)
        other_ta = TeachingAssignment.objects.create(
            teacher=self.admin, course=self.year.course, year=other_year, subject=subj)
        job = self.job(self.admin)

        def other_class_edit():
            TimetableEntry.objects.create(assignment=other_ta, day_of_week=3,
                                          time_slot=self.slots[2])
        self.assertEqual(self.run_with(job, other_class_edit), "done")
        self.assertEqual(self.entries(), 4)
        self.assertEqual(BackgroundJob.objects.get(id=job.id).status, "done")