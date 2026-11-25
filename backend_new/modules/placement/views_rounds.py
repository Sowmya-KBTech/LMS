"""
Drive rounds (optional): the placement office records who cleared each
selection round of a job role, from the shortlist the company sends back.

    GET/POST    /api/placement/roles/<role_id>/rounds/
    PATCH/DELETE /api/placement/rounds/<round_id>/
    GET/POST    /api/placement/rounds/<round_id>/results/
"""
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users.models import User

from .models import Application, DriveRound, JobRole, RoundResult
from .permissions import can_manage_placement, can_view_placement_staff, scope_students_for

TYPE_LABELS = dict(DriveRound.TYPE_CHOICES)


def _roster(round_obj, user):
    """Applications that are IN this round (derived, never stored)."""
    students = scope_students_for(user, User.objects.filter(role="student"))
    apps = Application.objects.filter(
        job_role=round_obj.job_role, status="applied", student__in=students,
    )
    prev = (
        DriveRound.objects
        .filter(job_role=round_obj.job_role, order__lt=round_obj.order)
        .order_by("-order")
        .first()
    )
    if prev:
        apps = apps.filter(round_results__round=prev, round_results__status="cleared")
    return apps.select_related("student__department").order_by("student__roll_number")


def _counts(round_obj, roster):
    ids = list(roster.values_list("id", flat=True))
    marks = dict(
        RoundResult.objects
        .filter(round=round_obj, application_id__in=ids)
        .values_list("application_id", "status")
    )
    counts = {"in_round": len(ids), "cleared": 0, "not_cleared": 0, "absent": 0}
    for st in marks.values():
        counts[st] += 1
    counts["pending"] = len(ids) - len(marks)
    return counts, marks


def _round_json(round_obj, user):
    counts, _ = _counts(round_obj, _roster(round_obj, user))
    return {
        "id": round_obj.id,
        "order": round_obj.order,
        "name": round_obj.name,
        "round_type": round_obj.round_type,
        "round_type_display": TYPE_LABELS.get(round_obj.round_type, round_obj.round_type),
        "round_date": round_obj.round_date,
        "counts": counts,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def role_rounds(request, role_id):
    user = request.user
    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = JobRole.objects.select_related("drive__company").filter(pk=role_id).first()
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "POST":
        if not can_manage_placement(user):
            return Response({"detail": "Only the placement officer can add rounds."},
                            status=status.HTTP_403_FORBIDDEN)
        round_type = request.data.get("round_type") or "other"
        if round_type not in TYPE_LABELS:
            return Response({"detail": "Unknown round type."}, status=status.HTTP_400_BAD_REQUEST)
        name = (request.data.get("name") or "").strip() or TYPE_LABELS[round_type]
        next_order = (role.rounds.aggregate(m=Max("order"))["m"] or 0) + 1
        rd = DriveRound.objects.create(
            job_role=role, order=next_order, name=name[:120], round_type=round_type,
            round_date=request.data.get("round_date") or None,
        )
        return Response(_round_json(rd, user), status=status.HTTP_201_CREATED)

    rounds = [_round_json(r, user) for r in role.rounds.all()]
    selected = rounds[-1]["counts"]["cleared"] if rounds else None
    return Response({
        "job_role": role.id,
        "role_title": role.title,
        "company_name": role.drive.company.name,
        "can_manage": can_manage_placement(user),
        "rounds": rounds,
        # cleared the LAST round = selected by the company
        "selected_count": selected,
    })


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def round_detail(request, round_id):
    user = request.user
    if not can_manage_placement(user):
        return Response({"detail": "Only the placement officer can change rounds."},
                        status=status.HTTP_403_FORBIDDEN)
    rd = DriveRound.objects.filter(pk=round_id).first()
    if not rd:
        return Response({"detail": "Round not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        rd.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if "name" in request.data:
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "Name cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        rd.name = name[:120]
    if "round_type" in request.data:
        if request.data["round_type"] not in TYPE_LABELS:
            return Response({"detail": "Unknown round type."}, status=status.HTTP_400_BAD_REQUEST)
        rd.round_type = request.data["round_type"]
    if "round_date" in request.data:
        rd.round_date = request.data.get("round_date") or None
    rd.save()
    return Response(_round_json(rd, user))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def round_results(request, round_id):
    """
    GET  -> students in this round with their result
    POST -> {"results": [{"application": 12, "status": "cleared", "remarks": ""}, ...]}
            status "" clears a mark. Only students IN the round can be marked.
    """
    user = request.user
    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
    rd = DriveRound.objects.select_related("job_role__drive__company").filter(pk=round_id).first()
    if not rd:
        return Response({"detail": "Round not found."}, status=status.HTTP_404_NOT_FOUND)

    roster = _roster(rd, user)

    if request.method == "POST":
        items = request.data.get("results")
        if items is None:
            items = [request.data]
        allowed = set(roster.values_list("id", flat=True))
        valid = set(TYPE for TYPE, _ in RoundResult.STATUS_CHOICES)
        changed = 0
        for item in items:
            try:
                app_id = int(item.get("application"))
            except (TypeError, ValueError):
                continue
            if app_id not in allowed:
                continue
            new_status = item.get("status") or ""
            if new_status == "":
                RoundResult.objects.filter(round=rd, application_id=app_id).delete()
                changed += 1
                continue
            if new_status not in valid:
                return Response({"detail": f"Unknown status '{new_status}'."},
                                status=status.HTTP_400_BAD_REQUEST)
            # same function the Import & Export file uses
            from .services import save_round_result
            save_round_result(rd, app_id, new_status, item.get("remarks"), user)
            changed += 1
        roster = _roster(rd, user)
        counts, _ = _counts(rd, roster)
        return Response({"changed": changed, "counts": counts})

    counts, marks = _counts(rd, roster)
    remarks = dict(
        RoundResult.objects.filter(round=rd).values_list("application_id", "remarks")
    )
    rows = [{
        "application": a.id,
        "student_name": a.student.username,
        "roll_number": a.student.roll_number,
        "department_name": a.student.department.name if a.student.department else None,
        "status": marks.get(a.id),
        "remarks": remarks.get(a.id, ""),
    } for a in roster]
    return Response({
        "round": _round_json(rd, user),
        "role_title": rd.job_role.title,
        "company_name": rd.job_role.drive.company.name,
        "counts": counts,
        "results": rows,
    })
