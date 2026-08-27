# attendance/services.py
"""Single source of truth for attendance calculations."""

# The one place the "what counts as attended" rule lives.
# Duty leave (approved OD) counts as present.
PRESENT_STATUSES = ["present", "duty_leave"]


def attendance_percentage(student_ids, from_date=None, to_date=None):
    """
    Overall attendance % for one or more students.
    Returns a float rounded to 1 decimal, or None if there are no records.
    Accepts a single id or a list/tuple/set of ids.
    """
    from .models import Attendance

    if not isinstance(student_ids, (list, tuple, set)):
        student_ids = [student_ids]

    records = Attendance.objects.filter(student_id__in=student_ids)

    if from_date:
        records = records.filter(date__gte=from_date)
    if to_date:
        records = records.filter(date__lte=to_date)

    total = records.count()
    if total == 0:
        return None

    counted = records.filter(status__in=PRESENT_STATUSES).count()
    return round((counted / total) * 100, 1)


# =====================================================
#  ON-DUTY -> ATTENDANCE
#
#  Lives here, beside PRESENT_STATUSES, because it writes the very status that
#  rule counts. Two places deciding what an approved OD does to attendance
#  would drift the first time one of them changed.
#
#  This REPLACES the old _mark_od_attendance() in users/views.py, which ran
#  .update() over rows that already existed:
#
#      Attendance.objects.filter(student=..., date__gte=..., date__lte=...)
#                        .update(status="duty_leave", ...)
#
#  That works when a teacher has already marked the student, and does nothing
#  at all when nobody has. For a placement drive, where the student is out for
#  the whole day, "nobody has" is the normal case -- the approval would leave
#  no trace and the student would simply have no record for that day.
# =====================================================

import datetime

from django.db import transaction

from events.holidays import holiday_dates


def _periods_for(student, date):
    """
    Every (teaching_assignment_id, period_no) this student had on `date`.

    Finds the student's classes the SAME way timetable/views.py does:
    enrolments first, then a course/year/semester fallback. 17 of 74 students
    currently have no enrolment rows, and a lookup that only read enrolments
    would quietly create nothing for them.

    Attendance.hour lines up with TimeSlot.period_no. Break slots are numbered
    101/102 and carry is_break=True -- nobody takes attendance for lunch.
    """
    from courses.models import Enrollment
    from timetable.models import TimetableEntry

    weekday = date.weekday()          # Monday = 0, matching TimetableEntry.MON
    if weekday > 5:                   # Sunday
        return []

    entries = (
        TimetableEntry.objects
        .filter(day_of_week=weekday, time_slot__is_break=False)
        .select_related("assignment", "time_slot")
    )

    assignment_ids = list(
        Enrollment.objects
        .filter(student=student)
        .values_list("teaching_assignment_id", flat=True)
    )

    if assignment_ids:
        entries = entries.filter(assignment_id__in=assignment_ids)
    else:
        if not (student.course_id and student.year and student.semester):
            return []
        entries = entries.filter(
            assignment__course_id=student.course_id,
            assignment__year__year_number=student.year,
            assignment__subject__semester=student.semester,
        )

    # Activities (library, sports) have no assignment and no attendance.
    return [
        (e.assignment_id, e.time_slot.period_no)
        for e in entries
        if e.assignment_id
    ]


def _dates_between(from_date, to_date):
    """
    Every date in the range, inclusive, skipping Sundays and holidays.

    Holidays come from events/holidays.py -- the one source the whole system
    reads. There used to be a second holiday table in the timetable app
    holding dates nothing else could see.
    """
    holidays = holiday_dates()

    out = []
    day = from_date
    while day <= to_date:
        if day.weekday() != 6 and day not in holidays:
            out.append(day)
        day += datetime.timedelta(days=1)
    return out


@transaction.atomic
def mark_duty_leave(od_request):
    """
    Write duty_leave attendance for every period an approved OD covers.

    Returns {'created': n, 'updated': n, 'dates': [...]}.

    Only runs for an APPROVED request -- a pending OD must not excuse anyone.

    Existing rows are UPDATED, not skipped. A teacher may have marked the
    student absent before the OD came through, and leaving that row alone
    would mean the approval changed nothing for exactly the student who
    needed it. The unique constraint on (assignment, student, date, hour)
    makes a blind create impossible anyway.
    """
    from .models import Attendance, ODRequest

    if od_request.status != ODRequest.Status.APPROVED:
        return {"created": 0, "updated": 0, "dates": []}

    student = od_request.student
    dates = _dates_between(od_request.from_date, od_request.to_date)

    # whoever approved it -- so a duty_leave row traces back to a decision
    # rather than appearing from nowhere
    approver = od_request.hod_reviewed_by or od_request.tutor_reviewed_by

    created = 0
    updated = 0

    for date in dates:
        for assignment_id, period_no in _periods_for(student, date):

            _row, was_created = Attendance.objects.update_or_create(
                teaching_assignment_id=assignment_id,
                student=student,
                date=date,
                hour=period_no,
                defaults={
                    "status": "duty_leave",
                    "marked_by": approver,
                },
            )

            if was_created:
                created += 1
            else:
                updated += 1

    return {
        "created": created,
        "updated": updated,
        "dates": [str(d) for d in dates],
    }