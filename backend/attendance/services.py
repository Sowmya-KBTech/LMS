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