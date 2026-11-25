"""
Placement-readiness card: one student's placement picture, built only from
data the college already has. Shown to the student's mentor, class tutor,
HOD and the placement office, so they can guide the student BEFORE drives.

    GET /api/placement/students/<student_id>/readiness/
"""
from django.apps import apps
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.module_registry import module_enabled
from core.academics.models import YearTutor
from core.users.models import Department, User
from modules.attendance.services import attendance_percentage
from modules.exams.services import get_academic_standing

from .models import Application, DriveAttendance, Offer, RoundResult
from .permissions import can_view_placement_staff, scope_students_for

LOW_ATTENDANCE = 75      # Anna University minimum
LOW_CGPA = 6.0           # the most common company cutoff
MANY_SKIPS = 3


def _hod_department_ids(user):
    """
    Ids of the departments this user is HOD of today. #50 ACTING HOD: with the
    Acting HOD feature installed (core/users/acting_hod.py, by the teammate)
    an Acting HOD counts during their dates; until then only the regular HOD -
    so this card never crashes for want of that file.
    """
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is not None:
        from core.users.acting_hod import hod_department_ids
        return set(hod_department_ids(user))
    return set(Department.objects.filter(hod=user).values_list("id", flat=True))


def can_view_readiness(user, student):
    if user.id == student.id:
        return True
    if can_view_placement_staff(user) and scope_students_for(
        user, User.objects.filter(pk=student.pk)
    ).exists():
        return True
    if user.role != "teacher":
        return False
    if student.department_id and student.department_id in _hod_department_ids(user):
        return True
    if YearTutor.objects.filter(
        teacher=user, course_id=student.course_id, year__year_number=student.year,
    ).exists():
        return True
    if module_enabled("mentoring"):
        MentorAllocation = apps.get_model("mentoring", "MentorAllocation")
        if MentorAllocation.objects.filter(student=student, mentor=user, is_active=True).exists():
            return True
    return False


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_readiness(request, student_id):
    student = (
        User.objects.filter(pk=student_id, role="student")
        .select_related("department", "course").first()
    )
    if not student:
        return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
    if not can_view_readiness(request.user, student):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    standing = get_academic_standing(student)
    cgpa = standing.get("cgpa")
    arrears = standing.get("arrears") or 0
    attendance = attendance_percentage(student.id)
    prior = getattr(student, "prior_academics", None)

    apps_qs = Application.objects.filter(student=student)
    applied = apps_qs.filter(status="applied").count()
    opted_out = apps_qs.filter(status="opted_out").count()
    attended = DriveAttendance.objects.filter(application__student=student, status="present").count()
    rounds_cleared = RoundResult.objects.filter(application__student=student, status="cleared").count()
    offers = [
        {
            "company": o.application.job_role.drive.company.name,
            "role": o.application.job_role.title,
            "package_lpa": o.package_lpa,
            "status": o.status,
            "status_display": o.get_status_display(),
        }
        for o in Offer.objects.filter(application__student=student)
        .select_related("application__job_role__drive__company").order_by("-package_lpa")
    ]
    placed = next((o for o in offers if o["status"] == "accepted"), None)

    # things to work on -- "high" blocks most drives, "medium" is worth fixing
    flags = []
    if prior is None:
        flags.append({"level": "high", "text": "10th / 12th marks not entered — most drives need them."})
    elif not prior.verified:
        flags.append({"level": "medium", "text": "10th / 12th marks entered but not verified by the coordinator."})
    if arrears:
        flags.append({"level": "high", "text": f"{arrears} standing arrear(s) — many companies allow none."})
    if cgpa is None:
        flags.append({"level": "medium", "text": "CGPA not available yet."})
    elif float(cgpa) < LOW_CGPA:
        flags.append({"level": "medium", "text": f"CGPA {cgpa} is below {LOW_CGPA}, a common company cutoff."})
    if attendance is not None and attendance < LOW_ATTENDANCE:
        flags.append({"level": "medium", "text": f"Attendance {attendance}% is below {LOW_ATTENDANCE}%."})
    if opted_out >= MANY_SKIPS:
        flags.append({"level": "medium", "text": f"Opted out of {opted_out} drives."})

    if placed:
        level, label = "placed", "Placed"
    elif any(f["level"] == "high" for f in flags):
        level, label = "not_ready", "Not ready"
    elif flags:
        level, label = "attention", "Needs attention"
    else:
        level, label = "ready", "Ready"

    return Response({
        "student": {
            "id": student.id,
            "name": student.get_full_name() or student.username,
            "roll_number": student.roll_number,
            "department": student.department.name if student.department else None,
            "year": student.year,
            "semester": student.semester,
        },
        "level": level,
        "level_label": label,
        "academics": {
            "cgpa": cgpa,
            "arrears": arrears,
            "attendance_percent": attendance,
            "tenth_percent": getattr(prior, "tenth_percent", None),
            "twelfth_percent": getattr(prior, "qualifying_percent", None) if prior else None,
            "marks_verified": bool(prior and prior.verified),
        },
        "drives": {
            "applied": applied,
            "opted_out": opted_out,
            "attended": attended,
            "rounds_cleared": rounds_cleared,
        },
        "offers": offers,
        "placed": placed,
        "flags": flags,
    })