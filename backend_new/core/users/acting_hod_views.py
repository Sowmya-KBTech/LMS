"""
#50 ACTING HOD - admin APIs (main admin only).

GET  /api/users/acting-hod/                        list + history (?department=<id>)
POST /api/users/acting-hod/                        assign {department, teacher, start_date, end_date, reason}
GET  /api/users/acting-hod/candidates/?department=<id>
POST /api/users/acting-hod/<id>/extend/            {end_date, reason}
POST /api/users/acting-hod/<id>/end/               {reason}
"""
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users import acting_hod as rules
from core.users.models import ActingHOD, Department, User


def _forbidden():
    return Response({"detail": "Only the main admin can manage Acting HOD."}, status=403)


def _assignments():
    return (ActingHOD.objects
            .select_related("department", "teacher", "assigned_by", "ended_by",
                            "nominated_by", "approved_by", "rejected_by")
            .prefetch_related("logs__done_by"))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def acting_hod_list(request):
    if not rules.is_main_admin(request.user):
        return _forbidden()

    if request.method == "POST":
        d = request.data
        try:
            a = rules.assign(request.user, d.get("department"), d.get("teacher"),
                             d.get("start_date"), d.get("end_date"), d.get("reason"))
        except rules.ActingHODError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(rules.serialize(a), status=201)

    qs = _assignments()
    dept = request.query_params.get("department")
    if dept:
        if not str(dept).isdigit():
            return Response({"detail": "Pick a department."}, status=400)
        qs = qs.filter(department_id=int(dept))

    today = timezone.localdate()
    departments = [
        {"id": x.id, "name": x.name, "hod": x.hod_id,
         "hod_name": x.hod.username if x.hod else None}
        for x in Department.objects.select_related("hod")
    ]
    return Response({
        "today": today.isoformat(),
        "departments": departments,
        "assignments": [rules.serialize(a, today) for a in qs],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def acting_hod_candidates(request):
    if not rules.is_main_admin(request.user):
        return _forbidden()
    dept_id = request.query_params.get("department", "")
    if not str(dept_id).isdigit():
        return Response({"detail": "Pick a department."}, status=400)
    dept = Department.objects.select_related("hod").filter(pk=int(dept_id)).first()
    if dept is None:
        return Response({"detail": "Department not found."}, status=404)

    teachers = (User.objects.filter(role="teacher", is_active=True, department=dept)
                .exclude(pk=dept.hod_id).order_by("username"))
    return Response({
        "department": {"id": dept.id, "name": dept.name},
        "hod": dept.hod.username if dept.hod else None,
        "teachers": [
            {"id": t.id, "username": t.username, "name": t.get_full_name() or t.username}
            for t in teachers
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acting_hod_extend(request, pk):
    if not rules.is_main_admin(request.user):
        return _forbidden()
    try:
        a = rules.extend(request.user, pk, request.data.get("end_date"),
                         request.data.get("reason"))
    except ActingHOD.DoesNotExist:
        return Response({"detail": "Assignment not found."}, status=404)
    except rules.ActingHODError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(rules.serialize(a))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acting_hod_end(request, pk):
    if not rules.is_main_admin(request.user):
        return _forbidden()
    try:
        a = rules.end_early(request.user, pk, request.data.get("reason"))
    except ActingHOD.DoesNotExist:
        return Response({"detail": "Assignment not found."}, status=404)
    except rules.ActingHODError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(rules.serialize(a))



# ---- Step 3b: approve / reject a HOD's nomination ----
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acting_hod_approve(request, pk):
    if not rules.is_main_admin(request.user):
        return _forbidden()
    try:
        a = rules.approve(request.user, pk)
    except ActingHOD.DoesNotExist:
        return Response({"detail": "Nomination not found."}, status=404)
    except rules.ActingHODError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(rules.serialize(a))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acting_hod_reject(request, pk):
    if not rules.is_main_admin(request.user):
        return _forbidden()
    try:
        a = rules.reject(request.user, pk, request.data.get("reason"))
    except ActingHOD.DoesNotExist:
        return Response({"detail": "Nomination not found."}, status=404)
    except rules.ActingHODError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(rules.serialize(a))



# ---- Step 4: banner info for the logged-in teacher (information only) ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def acting_hod_me(request):
    return Response(rules.banner_info(request.user))