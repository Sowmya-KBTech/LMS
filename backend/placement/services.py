"""
Placement actions that reach outside the placement app.

Anything that writes to attendance, notifications or another module lives
here rather than in a view, so the rule has one home and both the officer's
screen and any future bulk import call the same code.
"""

from django.utils import timezone


def create_drive_od(application, marked_by=None):
    """
    Create (or update) the approved On-Duty for a student attending a drive.

    Returns (od_request, note). `od_request` is None when no OD is possible,
    and `note` says why -- the caller shows that rather than failing silently.

    APPROVED AND CLOSED IMMEDIATELY. The normal OD flow is student applies ->
    tutor approves -> HOD approves, which is right when a student initiates:
    a conference, a sports meet. A placement drive is the opposite -- the
    placement cell SENT them, and the drive attendance sheet is the proof.
    Making them apply for permission afterwards would be theatre.

    Re-marking a student updates the existing OD instead of creating a second
    one, which is why DriveAttendance keeps a link to it.
    """
    from attendance.models import ODRequest
    from attendance.services import mark_duty_leave

    job_role = application.job_role
    drive = job_role.drive
    student = application.student

    # No date, no OD. Guessing today would excuse the wrong day's classes --
    # worse than no OD at all, because it is wrong and invisible.
    if not drive.drive_date:
        return None, "No OD created: this drive has no date set."

    company = drive.company.name
    reason = f"Attended {company} placement drive ({job_role.title})"

    existing = getattr(application, "drive_attendance", None)
    od = existing.od_request if existing else None

    if od:
        od.from_date = drive.drive_date
        od.to_date = drive.drive_date
        od.reason = reason
        od.status = ODRequest.Status.APPROVED
        od.stage = ODRequest.Stage.CLOSED
        od.hod_reviewed_by = marked_by
        od.hod_reviewed_at = timezone.now()
        od.save()
    else:
        od = ODRequest.objects.create(
            student=student,
            from_date=drive.drive_date,
            to_date=drive.drive_date,
            category=ODRequest.Category.PLACEMENT,
            reason=reason,
            status=ODRequest.Status.APPROVED,
            stage=ODRequest.Stage.CLOSED,
            # recorded as the HOD reviewer so the approval is attributable to
            # the coordinator who marked attendance, not anonymous
            hod_reviewed_by=marked_by,
            hod_reviewed_at=timezone.now(),
        )

    # The same function the tutor/HOD approval path calls. One definition of
    # what an approved OD does to attendance.
    marked = mark_duty_leave(od)

    if marked["created"] == 0 and marked["updated"] == 0:
        note = (
            f"OD approved for {drive.drive_date}, but no periods were marked "
            f"— this student has no timetable for that day."
        )
    else:
        note = (
            f"OD approved for {drive.drive_date}. "
            f"{marked['created'] + marked['updated']} period(s) marked as duty leave."
        )

    return od, note


def cancel_drive_od(application):
    """
    Undo the OD when a student is changed from present to absent.

    The OD is CANCELLED, not deleted, and the duty_leave rows are left alone
    for a teacher to correct. Silently flipping a student's attendance back to
    absent across several periods would overwrite whatever a teacher had
    already recorded, including any legitimate correction they made.
    """
    from attendance.models import ODRequest

    existing = getattr(application, "drive_attendance", None)
    od = existing.od_request if existing else None

    if not od:
        return None, ""

    od.status = ODRequest.Status.CANCELLED
    od.stage = ODRequest.Stage.CLOSED
    od.save(update_fields=["status", "stage"])

    return od, (
        "OD cancelled. Any duty-leave periods already marked stay as they are "
        "— a teacher should correct them if needed."
    )