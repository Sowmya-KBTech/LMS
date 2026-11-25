from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from config.module_registry import module_enabled


# Monday=0 ... Sunday=6, matching date.weekday().
# Default is a six-day college week. Override in config/settings.py, e.g.
#     COLLEGE_WORKING_WEEKDAYS = [0, 1, 2, 3, 4]      # Mon-Fri only
#     COLLEGE_AFTERNOON_STARTS_AT = time(13, 0)
DEFAULT_WORKING_WEEKDAYS = [0, 1, 2, 3, 4, 5]


def _working_weekdays():
    return set(
        getattr(settings, "COLLEGE_WORKING_WEEKDAYS", DEFAULT_WORKING_WEEKDAYS)
    )


def _afternoon_starts_at():
    return getattr(settings, "COLLEGE_AFTERNOON_STARTS_AT", time(13, 0))


def each_date(from_date, to_date):
    """Every calendar date in the range, both ends included."""
    current = from_date
    while current <= to_date:
        yield current
        current += timedelta(days=1)


def holiday_dates(from_date, to_date):
    """Declared holidays in the range, taken from the timetable calendar."""
    if not module_enabled("timetable"):
        return set()  # no timetable module -> no timetable holidays
    from modules.timetable.models import Holiday

    return set(
        Holiday.objects.filter(
            date__gte=from_date, date__lte=to_date
        ).values_list("date", flat=True)
    )


def working_days(from_date, to_date):
    """
    The dates in the range that are actual college working days: the configured
    working weekdays, minus declared holidays.
    """
    weekdays = _working_weekdays()
    holidays = holiday_dates(from_date, to_date)
    return [
        d for d in each_date(from_date, to_date)
        if d.weekday() in weekdays and d not in holidays
    ]


def count_leave_days(from_date, to_date, session="full"):
    """
    Number of leave days to record. A half-day session is only meaningful on a
    single-date request, which the serializer enforces.
    """
    if to_date < from_date:
        return Decimal("0.0")

    days = len(working_days(from_date, to_date))
    if days and from_date == to_date and session in ("forenoon", "afternoon"):
        return Decimal("0.5")
    return Decimal(days)


def _slot_in_session(slot, session):
    """Is this time slot inside the requested half of the day?"""
    if session == "forenoon":
        return slot.start_time < _afternoon_starts_at()
    if session == "afternoon":
        return slot.start_time >= _afternoon_starts_at()
    return True


def affected_periods(teacher, from_date, to_date, session="full"):
    """
    The teacher's timetable periods that fall inside the leave dates.

    Returned as plain dicts so the API, the teacher's form preview and the
    HOD's approval screen all show exactly the same list. Covers both taught
    subjects and non-teaching activities (mentor hour, library) the teacher
    is assigned to.

    Substitution is NOT handled here. This list only tells a human that cover
    may be needed.
    """
    if not module_enabled("timetable"):
        return []  # no timetable module -> no periods to cover
    from modules.timetable.models import TimetableEntry
    from django.db.models import Q

    if not from_date or not to_date or to_date < from_date:
        return []

    entries = (
        TimetableEntry.objects.filter(
            Q(assignment__teacher=teacher) | Q(class_activity__teacher=teacher)
        )
        .select_related(
            "time_slot", "room",
            "assignment__subject", "assignment__course", "assignment__year",
            "class_activity__activity", "class_activity__year",
        )
    )

    # Group by weekday once, then walk the dates.
    by_weekday = {}
    for entry in entries:
        by_weekday.setdefault(entry.day_of_week, []).append(entry)

    out = []
    for day in working_days(from_date, to_date):
        # TimetableEntry.DAY_CHOICES is Monday=0 ... Saturday=5, which is the
        # same numbering as date.weekday().
        for entry in by_weekday.get(day.weekday(), []):
            if not _slot_in_session(entry.time_slot, session):
                continue

            if entry.kind == TimetableEntry.Kind.ACTIVITY and entry.class_activity:
                subject = entry.class_activity.activity.name
                year = entry.class_activity.year
                course_name = getattr(getattr(year, "course", None), "name", "")
            else:
                assignment = entry.assignment
                if assignment is None:
                    continue
                subject = assignment.subject.name
                year = assignment.year
                course_name = assignment.course.name

            out.append({
                "date": day.isoformat(),
                "day_of_week": entry.get_day_of_week_display(),
                "period_no": entry.time_slot.period_no,
                "start_time": entry.time_slot.start_time.strftime("%H:%M"),
                "end_time": entry.time_slot.end_time.strftime("%H:%M"),
                "subject": subject,
                "course": course_name,
                "year": getattr(year, "year_number", None),
                "room": entry.room.name if entry.room else None,
                "entry_id": entry.id,
            })

    out.sort(key=lambda p: (p["date"], p["period_no"]))
    return out


# ---------------------------------------------------------------- routing ---
def department_of(user):
    return getattr(user, "department", None)


def is_hod(user):
    """True if this user is the HOD of any department RIGHT NOW (#50 ACTING HOD aware)."""
    from core.users.acting_hod import is_hod as _is_hod

    return _is_hod(user)


def hod_departments(user):
    """Department ids this user is HOD of right now (#50 ACTING HOD aware)."""
    from core.users.acting_hod import hod_department_ids

    return hod_department_ids(user)


def approver_for(teacher):
    """
    The user who approves this teacher's leave: the HOD of their department.

    Returns (approver, error_message). The error message is what the API
    hands back to the teacher, so keep it readable.
    """
    dept = department_of(teacher)
    if dept is None:
        return None, "You are not linked to a department. Ask the admin to set it."

    # #50 ACTING HOD: route to the CURRENT HOD (the Acting HOD during their dates)
    from core.users.acting_hod import current_hod
    hod = current_hod(dept)
    if hod is None:
        return None, f"{dept.name} has no HOD set. Ask the admin to assign one."

    if hod.id == teacher.id or dept.hod_id == teacher.id:
        # The HOD's own leave has a backup and goes to the Principal (or is
        # recorded when none is set) - see staff_leave_create.
        return None, None

    return hod, None


def is_department_hod(teacher):
    """True if this teacher is the HOD of their own department."""
    # #50 ACTING HOD: the regular HOD AND the current (acting) HOD both name a
    # backup; the Principal approves (WAVE 2 Part 1b), or it is recorded if none is set.
    from core.users.acting_hod import is_current_hod_of
    dept = department_of(teacher)
    return bool(dept and (dept.hod_id == teacher.id or is_current_hod_of(teacher, dept)))


def backup_options(teacher):
    """Teachers in the same department who can cover, excluding the HOD."""
    from django.contrib.auth import get_user_model

    dept = department_of(teacher)
    if dept is None:
        return []
    User = get_user_model()
    return list(
        User.objects
        .filter(role="teacher", department=dept, is_active=True)
        .exclude(id=teacher.id)
                .order_by("username")
        .values("id", "username")
    )


def covering_warning(teacher, from_date, to_date, exclude_id=None):
    """
    If this teacher is the backup for an HOD leave that overlaps these dates,
    return a warning sentence. Otherwise return None.

    This only WARNS. It never blocks the teacher's leave.
    """
    from modules.attendance.models import StaffLeaveRequest

    if not from_date or not to_date:
        return None

    clash = (
        StaffLeaveRequest.objects
        .filter(
            backup=teacher,
            status__in=[StaffLeaveRequest.Status.RECORDED, StaffLeaveRequest.Status.APPROVED,
                        StaffLeaveRequest.Status.PENDING],     # WAVE 2 Part 1b: Principal approval
            from_date__lte=to_date,
            to_date__gte=from_date,
        )
        .exclude(pk=exclude_id)
        .select_related("teacher")
        .order_by("from_date")
        .first()
    )
    if clash is None:
        return None

    return (
        f"{teacher.username} is the backup for {clash.teacher.username} "
        f"from {clash.from_date.strftime('%d-%m-%Y')} "
        f"to {clash.to_date.strftime('%d-%m-%Y')}."
    )