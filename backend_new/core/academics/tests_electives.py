"""
Electives - Step 1: the tables and the rules (meeting point 9).

Run:  python manage.py test core.academics.tests_electives -v 2
"""
import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.academics.electives import ElectiveError, assign_whole_class, choose, drop, groups_for_student
from core.academics.models import (Course, ElectiveChange, ElectiveGroup, ElectiveOption, ElectiveSetting,
                                   Enrollment, Subject, TeachingAssignment, Year)
from core.users.models import Department, User


class ElectiveTestBase(TestCase):
    def setUp(self):
        self.mech = Department.objects.create(name="Mechanical", code="ME")
        self.cse = Department.objects.create(name="Computer Science", code="CS")
        self.course = Course.objects.create(name="B.E Mechanical")
        self.y3 = Year.objects.create(course=self.course, year_number=3)

        self.admin = User.objects.create_user(username="admin", password="x", role="admin")
        self.hod = User.objects.create_user(username="hodme", password="x", role="teacher", department=self.mech)
        self.other_hod = User.objects.create_user(username="hodcs", password="x", role="teacher",
                                                  department=self.cse)
        self.mech.hod = self.hod
        self.mech.save()
        self.cse.hod = self.other_hod
        self.cse.save()
        self.teacher = User.objects.create_user(username="priya", password="x", role="teacher",
                                                department=self.mech)

        self.aarthi = self.student("aarthi")
        self.bala = self.student("bala")

        self.group = ElectiveGroup.objects.create(course=self.course, year=self.y3, semester=5,
                                                  name="Professional Elective I", department=self.mech)
        self.robotics = self.option("Robotics", "ME5E1")
        self.composites = self.option("Composite Materials", "ME5E2")

    # ---------- helpers ----------
    def student(self, username, semester=5):
        return User.objects.create_user(username=username, password="x", role="student", department=self.mech,
                                        course=self.course, year=3, semester=semester)

    def option(self, name, code, seats=None, group=None):
        sub = Subject.objects.create(name=name, code=code, year=self.y3, semester=5, is_elective=True)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=sub)
        return ElectiveOption.objects.create(group=group or self.group, teaching_assignment=ta, seat_limit=seats)

    def has(self, student, option):
        return Enrollment.objects.filter(student=student, teaching_assignment=option.teaching_assignment).exists()

    def staff_mode(self):
        s = ElectiveSetting.current()
        s.mode = ElectiveSetting.STAFF
        s.save()


# ======================================================================
class StudentsChooseTests(ElectiveTestBase):

    def test_default_setting_is_students_choose(self):
        self.assertTrue(ElectiveSetting.current().students_choose)

    def test_student_picks_and_it_becomes_an_enrollment(self):
        change = choose(self.aarthi, self.robotics, by=self.aarthi)
        self.assertTrue(self.has(self.aarthi, self.robotics))
        self.assertEqual(change.to_option, self.robotics)
        self.assertIsNone(change.from_option)

    def test_pick_one_group_replaces_the_old_choice(self):
        choose(self.aarthi, self.robotics, by=self.aarthi)
        change = choose(self.aarthi, self.composites, by=self.aarthi)
        self.assertFalse(self.has(self.aarthi, self.robotics))
        self.assertTrue(self.has(self.aarthi, self.composites))
        self.assertEqual(change.from_option, self.robotics)

    def test_choosing_the_same_again_does_nothing(self):
        choose(self.aarthi, self.robotics, by=self.aarthi)
        self.assertIsNone(choose(self.aarthi, self.robotics, by=self.aarthi))
        self.assertEqual(ElectiveChange.objects.count(), 1)

    def test_pick_two_group_limit(self):
        self.group.picks = 2
        self.group.save()
        third = self.option("Additive Manufacturing", "ME5E3")
        choose(self.aarthi, self.robotics, by=self.aarthi)
        choose(self.aarthi, self.composites, by=self.aarthi)
        with self.assertRaisesMessage(ElectiveError, "only 2"):
            choose(self.aarthi, third, by=self.aarthi)

    def test_seat_limit(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        choose(self.aarthi, self.robotics, by=self.aarthi)
        with self.assertRaisesMessage(ElectiveError, "full (1/1)"):
            choose(self.bala, self.robotics, by=self.bala)
        self.assertFalse(self.has(self.bala, self.robotics))

    def test_window_not_open_and_closed(self):
        self.group.opens_at = timezone.now() + datetime.timedelta(days=2)
        self.group.save()
        with self.assertRaisesMessage(ElectiveError, "opens on"):
            choose(self.aarthi, self.robotics, by=self.aarthi)
        self.group.opens_at = timezone.now() - datetime.timedelta(days=5)
        self.group.closes_at = timezone.now() - datetime.timedelta(days=1)
        self.group.save()
        with self.assertRaisesMessage(ElectiveError, "last date"):
            choose(self.aarthi, self.robotics, by=self.aarthi)

    def test_other_class_refused(self):
        sem6 = self.student("chitra", semester=6)
        with self.assertRaisesMessage(ElectiveError, "not for chitra's class"):
            choose(sem6, self.robotics, by=sem6)

    def test_student_can_drop_while_open(self):
        choose(self.aarthi, self.robotics, by=self.aarthi)
        drop(self.aarthi, self.robotics, by=self.aarthi)
        self.assertFalse(self.has(self.aarthi, self.robotics))

    def test_student_cannot_change_someone_else(self):
        with self.assertRaisesMessage(ElectiveError, "can't change electives"):
            choose(self.bala, self.robotics, by=self.aarthi)

    def test_groups_for_student(self):
        self.assertEqual(list(groups_for_student(self.aarthi)), [self.group])


# ======================================================================
class StaffAllocateTests(ElectiveTestBase):

    def setUp(self):
        super().setUp()
        self.staff_mode()

    def test_student_cannot_choose_in_staff_mode(self):
        with self.assertRaisesMessage(ElectiveError, "HOD allocates"):
            choose(self.aarthi, self.robotics, by=self.aarthi)

    def test_hod_allocates_without_reason_first_time(self):
        choose(self.aarthi, self.robotics, by=self.hod)
        self.assertTrue(self.has(self.aarthi, self.robotics))

    def test_moving_needs_a_reason(self):
        choose(self.aarthi, self.robotics, by=self.hod)
        with self.assertRaisesMessage(ElectiveError, "reason"):
            choose(self.aarthi, self.composites, by=self.hod)
        change = choose(self.aarthi, self.composites, by=self.hod, reason="Student asked, seat available")
        self.assertEqual(change.reason, "Student asked, seat available")
        self.assertEqual(change.changed_by, self.hod)

    def test_removing_needs_a_reason(self):
        choose(self.aarthi, self.robotics, by=self.hod)
        with self.assertRaisesMessage(ElectiveError, "reason"):
            drop(self.aarthi, self.robotics, by=self.hod)
        drop(self.aarthi, self.robotics, by=self.hod, reason="Wrong allocation, corrected")
        self.assertFalse(self.has(self.aarthi, self.robotics))

    def test_other_department_hod_refused(self):
        with self.assertRaisesMessage(ElectiveError, "can't change electives"):
            choose(self.aarthi, self.robotics, by=self.other_hod)

    def test_admin_can_allocate_any_group(self):
        choose(self.aarthi, self.robotics, by=self.admin)
        self.assertTrue(self.has(self.aarthi, self.robotics))

    def test_staff_can_change_after_last_date(self):
        ElectiveSetting.objects.filter(pk=1).update(mode=ElectiveSetting.STUDENTS)
        self.group.closes_at = timezone.now() - datetime.timedelta(days=1)
        self.group.save()
        choose(self.aarthi, self.robotics, by=self.hod)                  # allowed for staff
        self.assertTrue(self.has(self.aarthi, self.robotics))

    def test_seat_limit_applies_to_staff_too(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        choose(self.aarthi, self.robotics, by=self.hod)
        with self.assertRaisesMessage(ElectiveError, "full"):
            choose(self.bala, self.robotics, by=self.hod)


# ======================================================================
class ValidationTests(ElectiveTestBase):

    def test_group_semester_must_fit_year(self):
        g = ElectiveGroup(course=self.course, year=self.y3, semester=2, name="Wrong")
        with self.assertRaises(ValidationError):
            g.full_clean()

    def test_group_last_date_after_opening(self):
        now = timezone.now()
        g = ElectiveGroup(course=self.course, year=self.y3, semester=5, name="Dates",
                          opens_at=now, closes_at=now - datetime.timedelta(hours=1))
        with self.assertRaises(ValidationError):
            g.full_clean()

    def test_option_must_be_an_elective_of_this_class(self):
        core = Subject.objects.create(name="Heat Transfer", code="ME501", year=self.y3, semester=5)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=core)
        with self.assertRaisesMessage(ValidationError, "not marked as an elective"):
            ElectiveOption(group=self.group, teaching_assignment=ta).full_clean()

    def test_option_semester_must_match_group(self):
        sub = Subject.objects.create(name="Mechatronics", code="ME6E1", year=self.y3, semester=6, is_elective=True)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=sub)
        with self.assertRaisesMessage(ValidationError, "Semester 6 subject"):
            ElectiveOption(group=self.group, teaching_assignment=ta).full_clean()


# ======================================================================
class WholeClassTests(ElectiveTestBase):
    """Colleges where the whole class takes the same elective."""

    def setUp(self):
        super().setUp()
        self.staff_mode()
        self.chitra = self.student("chitra")
        self.sem6 = self.student("dinesh", semester=6)          # different class - never touched

    def test_hod_gives_whole_class_one_elective(self):
        result = assign_whole_class(self.robotics, by=self.hod)
        self.assertEqual(result, {"assigned": 3, "already": 0, "kept_other": []})
        for st in (self.aarthi, self.bala, self.chitra):
            self.assertTrue(self.has(st, self.robotics))
        self.assertFalse(self.has(self.sem6, self.robotics))
        self.assertEqual(ElectiveChange.objects.filter(reason="Whole-class allocation").count(), 3)

    def test_running_again_adds_only_new_students(self):
        assign_whole_class(self.robotics, by=self.hod)
        late = self.student("elango")                            # joined later
        result = assign_whole_class(self.robotics, by=self.hod)
        self.assertEqual(result["assigned"], 1)
        self.assertEqual(result["already"], 3)
        self.assertTrue(self.has(late, self.robotics))

    def test_student_already_in_another_option_is_not_moved(self):
        choose(self.aarthi, self.composites, by=self.hod)
        result = assign_whole_class(self.robotics, by=self.hod)
        self.assertEqual(result["kept_other"], ["aarthi"])
        self.assertTrue(self.has(self.aarthi, self.composites))
        self.assertFalse(self.has(self.aarthi, self.robotics))

    def test_seat_limit_all_or_nothing(self):
        self.robotics.seat_limit = 2
        self.robotics.save()
        with self.assertRaisesMessage(ElectiveError, "2 seat(s) left but 3 student(s) need a place"):
            assign_whole_class(self.robotics, by=self.hod)
        self.assertFalse(Enrollment.objects.filter(teaching_assignment=self.robotics.teaching_assignment).exists())

    def test_works_in_students_choose_setting_too(self):
        ElectiveSetting.objects.filter(pk=1).update(mode=ElectiveSetting.STUDENTS)
        self.assertEqual(assign_whole_class(self.robotics, by=self.admin)["assigned"], 3)

    def test_students_and_other_hods_cannot(self):
        for user in (self.aarthi, self.other_hod, self.teacher):
            with self.assertRaisesMessage(ElectiveError, "can't change electives"):
                assign_whole_class(self.robotics, by=user)

