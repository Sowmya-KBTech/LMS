"""
ELECTIVE RULES (meeting point 9) - the ONLY place they live.
The student screen, the HOD screen and the Excel import all call these.

  choose(student, option, by, reason="")   pick / move / allocate one student
  drop(student, option, by, reason="")     remove a choice
  assign_whole_class(option, by)           give the WHOLE class this option
                                           (colleges where everyone takes the
                                           same elective) - staff only

Rules
  * a student can only be given options from groups for THEIR OWN class
    (course + year + semester)
  * at most `picks` per group; with picks = 1, a new pick replaces the old one
  * seat limit: a full option can't take anyone new
  * STUDENTS acting for themselves: only when the college setting is
    "Students choose" AND the group's window is open
  * STAFF (admin, academic admin, the group's HOD): any time; MOVING or
    REMOVING an existing choice needs a reason (first allocation doesn't)
  * every change is written to ElectiveChange (who, when, from, to, why)

Choosing = an Enrollment in the option's teaching assignment, so attendance,
IA and results follow automatically.
"""
from django.db import transaction

from core.academics.permissions import can_manage_academics

from .models import Enrollment
from .models_electives import ElectiveChange, ElectiveGroup, ElectiveOption, ElectiveSetting

MIN_REASON = 10


class ElectiveError(Exception):
    """A rule was broken. The message is shown to the user as it is."""


# ===================== WHO =====================
def can_manage_group(user, group):
    """Admin / academic admin for every group; a HOD for their department's groups."""
    if can_manage_academics(user):
        return True
    if not getattr(user, "is_authenticated", False) or not group.department_id:
        return False
    from core.users.models import Department
    return Department.objects.filter(pk=group.department_id, hod=user).exists()


def manageable_groups(user):
    qs = ElectiveGroup.objects.select_related("course", "year", "department")
    if can_manage_academics(user):
        return qs
    from core.users.models import Department
    return qs.filter(department__in=Department.objects.filter(hod=user))


# ===================== WHAT =====================
def groups_for_student(student):
    """The elective groups of the student's own class, plus open electives offered to them."""
    from django.db.models import Q
    own = Q(course_id=student.course_id, year__year_number=student.year)
    # CBCS PART B: open electives of this semester offered to the student's course
    offered = Q(open_elective=True) & (Q(open_to__isnull=True) | Q(open_to=student.course_id))
    return (ElectiveGroup.objects
            .filter(own | offered, semester=student.semester)
            .distinct()
            .select_related("course", "year")
            .prefetch_related("options__teaching_assignment__subject",
                              "options__teaching_assignment__teacher", "options__requires", "open_to"))


def in_class(student, group):
    if student.semester != group.semester:
        return False
    if group.open_elective:                               # CBCS PART B
        courses = [c.id for c in group.open_to.all()]
        return not courses or student.course_id in courses
    return student.course_id == group.course_id and student.year == group.year.year_number


# ===================== CBCS PART B: OWN COURSE / PREREQUISITES =====================
def own_course(student, option):
    """An open elective option taught to the student's own course - not for them."""
    return option.group.open_elective and option.teaching_assignment.course_id == student.course_id


def passed_subjects(student):
    from modules.exams.models import ResultEntry
    return set(ResultEntry.objects.filter(result__student=student, result__is_published=True, is_pass=True)
               .values_list("subject_id", flat=True))


def prerequisite_problem(student, option, passed=None):
    """
    "" when the student may take it; else why not. A required subject counts
    as passed when a published result says so (any attempt).
    `passed` = set of subject ids already looked up (saves queries for lists).
    """
    needs = list(option.requires.all())
    if not needs:
        return ""
    if passed is None:
        passed = passed_subjects(student)
    missing = [s for s in needs if s.id not in passed]
    if not missing:
        return ""
    names = ", ".join(f"{s.code} {s.name}" if s.code else s.name for s in missing)
    return f"Needs {names} passed."


def blocked_reason(student, option, passed=None):
    if own_course(student, option):
        return "Taught to your own course; choose one from another department."
    return prerequisite_problem(student, option, passed)


def current_options(student, group):
    """The options of this group the student currently holds."""
    ta_ids = set(Enrollment.objects.filter(
        student=student,
        teaching_assignment__elective_option__group=group,
    ).values_list("teaching_assignment_id", flat=True))
    return [o for o in group.options.all() if o.teaching_assignment_id in ta_ids]


# ===================== CHECKS =====================
def _check_allowed(student, group, by, changing):
    if not in_class(student, group):
        raise ElectiveError(f"{group.name} is not for {student.username}'s class.")

    if by.pk == student.pk:
        if not ElectiveSetting.current().students_choose:
            raise ElectiveError("In this college your HOD allocates electives.")
        # CBCS PART A: a group inside a course registration window is chosen there
        from core.academics.course_registration import window_for_group
        if window_for_group(group) is not None:
            raise ElectiveError(f"Choose {group.name} in Course registration.")
        state = group.window_state()
        if state == "not_open":
            raise ElectiveError(f"Choosing for {group.name} opens on "
                                f"{group.opens_at.astimezone().strftime('%d %b %Y, %I:%M %p')}.")
        if state == "closed":
            raise ElectiveError(f"The last date for {group.name} has passed. Ask your HOD to change it.")
        return False                                   # no reason needed

    if not can_manage_group(by, group):
        raise ElectiveError("You can't change electives for this class.")
    return changing                                    # staff: reason needed when changing


def _need_reason(reason):
    if len((reason or "").strip()) < MIN_REASON:
        raise ElectiveError(f"Please give a reason (at least {MIN_REASON} characters) for changing "
                            f"an existing elective.")


# ===================== ACTIONS =====================
@transaction.atomic
def choose(student, option, by, reason=""):
    """
    Give `student` this option. Returns the ElectiveChange, or None if the
    student already had it. Raises ElectiveError when a rule is broken.
    """
    # lock the option row so two students can't take the last seat together
    option = (ElectiveOption.objects.select_for_update()
              .select_related("group__year", "teaching_assignment__subject")
              .get(pk=option.pk))
    group = option.group
    held = current_options(student, group)

    if option in held:
        return None

    replacing = held[0] if (len(held) >= group.picks and group.picks == 1) else None
    if len(held) >= group.picks and replacing is None:
        raise ElectiveError(f"You can take only {group.picks} from {group.name}. Remove one first.")

    if _check_allowed(student, group, by, changing=replacing is not None):
        _need_reason(reason)
    # CBCS PART B: never an option of the student's own course; prerequisites
    # stop the student, staff may still allocate (they know the exceptions)
    if own_course(student, option):
        raise ElectiveError(blocked_reason(student, option))
    if by.pk == student.pk and prerequisite_problem(student, option):
        raise ElectiveError(prerequisite_problem(student, option))

    if option.seat_limit is not None and option.seats_taken >= option.seat_limit:
        raise ElectiveError(f"{option.teaching_assignment.subject.name} is full "
                            f"({option.seats_taken}/{option.seat_limit}).")

    if replacing is not None:
        Enrollment.objects.filter(student=student,
                                  teaching_assignment_id=replacing.teaching_assignment_id).delete()
    Enrollment.objects.get_or_create(student=student, teaching_assignment_id=option.teaching_assignment_id)

    return ElectiveChange.objects.create(
        student=student, group=group, from_option=replacing, to_option=option,
        changed_by=by, reason=(reason or "").strip()[:255],
    )


@transaction.atomic
def drop(student, option, by, reason=""):
    """Remove this option from the student. Returns the ElectiveChange, or None if they didn't have it."""
    option = (ElectiveOption.objects.select_related("group__year", "teaching_assignment__subject")
              .get(pk=option.pk))
    group = option.group
    if option not in current_options(student, group):
        return None

    if _check_allowed(student, group, by, changing=True):
        _need_reason(reason)

    Enrollment.objects.filter(student=student,
                              teaching_assignment_id=option.teaching_assignment_id).delete()
    return ElectiveChange.objects.create(
        student=student, group=group, from_option=option, to_option=None,
        changed_by=by, reason=(reason or "").strip()[:255],
    )


# ===================== WHOLE CLASS =====================
def class_students(group):
    """Active students of the group's class; for an open elective, everyone it is offered to."""
    from core.users.models import User
    qs = User.objects.filter(role="student", is_active=True, semester=group.semester)
    if group.open_elective:                               # CBCS PART B
        courses = [c.id for c in group.open_to.all()]
        if courses:
            qs = qs.filter(course_id__in=courses)
        return qs.order_by("course__name", "roll_number", "username")
    return qs.filter(course_id=group.course_id, year=group.year.year_number).order_by("roll_number", "username")


@transaction.atomic
def assign_whole_class(option, by):
    """
    Give every student of the class this option - for colleges where the whole
    class takes the same elective. Staff only (admin / academic admin / the
    group's HOD), in either college setting.

    * students who already have this option are left as they are
    * students who already hold a DIFFERENT option of this group are NOT
      moved (moving one student needs a reason - use choose() for that);
      they are reported back as `kept_other`
    * all or nothing on seats: if the seat limit can't fit everyone who needs
      a place, nobody is added and the error says how many seats are short
    * safe to run again later (new admissions): only the missing students
      are added

    Returns {"assigned": n, "already": n, "kept_other": [usernames]}.
    """
    option = (ElectiveOption.objects.select_for_update()
              .select_related("group__year", "teaching_assignment__subject")
              .get(pk=option.pk))
    group = option.group
    subject = option.teaching_assignment.subject.name

    if not can_manage_group(by, group):
        raise ElectiveError("You can't change electives for this class.")
    if group.open_elective:                               # CBCS PART B
        raise ElectiveError("An open elective can't be given to a whole class. Allocate students one by one.")

    students = list(class_students(group))
    other_ta_ids = [o.teaching_assignment_id for o in group.options.all() if o.pk != option.pk]
    holders = {}                                  # student_id -> set of TA ids in this group
    for sid, ta_id in Enrollment.objects.filter(
            student__in=students,
            teaching_assignment_id__in=other_ta_ids + [option.teaching_assignment_id],
    ).values_list("student_id", "teaching_assignment_id"):
        holders.setdefault(sid, set()).add(ta_id)

    already, kept_other, to_add = 0, [], []
    for st in students:
        held = holders.get(st.id, set())
        if option.teaching_assignment_id in held:
            already += 1
        elif len(held) >= group.picks:
            kept_other.append(st.username)        # full for this group - don't move silently
        else:
            to_add.append(st)

    if option.seat_limit is not None:
        free = option.seat_limit - option.seats_taken
        if len(to_add) > free:
            raise ElectiveError(
                f"{subject} has {max(free, 0)} seat(s) left but {len(to_add)} student(s) need a place. "
                f"Raise the seat limit or allocate students one by one.")

    Enrollment.objects.bulk_create(
        [Enrollment(student=st, teaching_assignment_id=option.teaching_assignment_id) for st in to_add],
        ignore_conflicts=True,
    )
    ElectiveChange.objects.bulk_create([
        ElectiveChange(student=st, group=group, from_option=None, to_option=option,
                       changed_by=by, reason="Whole-class allocation")
        for st in to_add
    ])
    return {"assigned": len(to_add), "already": already, "kept_other": kept_other}

