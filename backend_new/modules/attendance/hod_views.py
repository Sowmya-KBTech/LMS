# HOD attendance overview. Moved here from users/views.py.
# URL unchanged (/api/users/hod-attendance/) - see attendance/users_urls.py.
# ===================== IMPORTS =====================


from rest_framework.decorators import (api_view, permission_classes)
from rest_framework.response import Response
from rest_framework.permissions import (IsAuthenticated)

from core.users.models import (User, Department)


# ===================== HOD: DEPARTMENT ATTENDANCE =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_attendance(request):
    """
    Attendance overview for the HOD's department.
    At-risk list: students whose overall attendance % is below 80%
    (red < 75, amber 75-80), sorted lowest first.
    Daily per-class absence is the tutor's concern, not the HOD's.
    """
    user = request.user

    from core.users.acting_hod import hod_departments   # #50 ACTING HOD
    departments = hod_departments(user)
    if not departments.exists():
        return Response({"is_hod": False, "departments": []})

    from modules.attendance.services import attendance_percentage

    THRESHOLD = 75
    WARN_BAND = 80

    result = []
    for dept in departments:
        students = list(
            User.objects.filter(role="student", department=dept)
            .order_by("roll_number")
        )

        at_risk = []
        for s in students:
            pct = attendance_percentage(s.id)
            if pct is None:
                continue   # no attendance records for this student

            if pct < WARN_BAND:
                at_risk.append({
                    "id": s.id,
                    "username": s.username,
                    "roll_number": s.roll_number,
                    "year": s.year,
                    "semester": s.semester,
                    "percent": pct,
                    "level": "danger" if pct < THRESHOLD else "warn",
                })

        at_risk.sort(key=lambda x: x["percent"])

        result.append({
            "id": dept.id,
            "name": dept.name,
            "total_students": len(students),
            "below_75": sum(1 for r in at_risk if r["level"] == "danger"),
            "near_75": sum(1 for r in at_risk if r["level"] == "warn"),
            "at_risk": at_risk,
        })

    return Response({"is_hod": True, "departments": result})
