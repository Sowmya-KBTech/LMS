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


def attendance_map(students):
    """
    {student_id: percentage|None} from attendance.Attendance.

    (Moved here from mentoring/utils.py - mentoring and class groups both use it.)

    Scoped to each student's CURRENT semester. Counting every record a student
    has ever had dilutes a third year's figure with two prior years, and that
    number drives the "below 75%" list a mentor acts on.

    F("student__semester") matches each row against its own student's semester,
    so one query handles a list spanning several. This is the same rule
    exams._attendance_percent uses for the hall ticket, so a student is never
    below the line on one screen and above it on another.

    'duty_leave' counts as present, matching how OD approval marks it.
    """
    from django.db.models import F
    from .models import Attendance

    ids = [s.id if hasattr(s, "id") else s for s in students]
    rows = Attendance.objects.filter(
        student_id__in=ids,
        teaching_assignment__subject__semester=F("student__semester"),
    ).values_list("student_id", "status")

    acc = {}
    for sid, st in rows:
        total, present = acc.get(sid, (0, 0))
        acc[sid] = (total + 1, present + (1 if st in ("present", "duty_leave") else 0))

    out = {sid: None for sid in ids}
    for sid, (total, present) in acc.items():
        out[sid] = round(present / total * 100) if total else None
    return out


def mark_duty_leave(od):
    """
    What an APPROVED on-duty does to attendance - ONE definition, used by the
    HOD approval (od_views) and by placement drive attendance
    (placement/services.create_drive_od), which already called this name.

    Periods already marked inside the OD's dates become duty_leave. Periods
    marked later show the student as On duty on the register automatically
    (/attendance/od_students/). Returns {"created": 0, "updated": n}.
    """
    from .models import Attendance
    updated = (Attendance.objects
               .filter(student=od.student, date__gte=od.from_date, date__lte=od.to_date)
               .exclude(status="duty_leave")
               .update(status="duty_leave", marked_by=od.hod_reviewed_by))
    return {"created": 0, "updated": updated}
