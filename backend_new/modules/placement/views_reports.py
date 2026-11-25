"""
Offer policy (dream / super dream), NIRF / NAAC placement report and the
higher-studies records that report needs.

    GET/PUT          /api/placement/policy/
    GET              /api/placement/report/nirf/?passing_year=2026
    GET/POST         /api/placement/higher-studies/?passing_year=2026
    DELETE           /api/placement/higher-studies/<id>/
"""
import statistics
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users.models import User

from .models import HigherStudies, Offer, PlacementPolicy
from .permissions import can_manage_placement, can_view_placement_staff, scope_students_for


# ===================== OFFER POLICY =====================
def _policy_json(p):
    return {
        "tiers_enabled": p.tiers_enabled,
        "final_year_only": p.final_year_only,
        "higher_package_only": p.higher_package_only,
        "dream_min_lpa": p.dream_min_lpa,
        "super_dream_min_lpa": p.super_dream_min_lpa,
        "updated_at": p.updated_at,
    }


def _decimal_or_none(value, label):
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a number.")
    if d < 0:
        raise ValueError(f"{label} cannot be negative.")
    return d


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def placement_policy(request):
    policy = PlacementPolicy.current()
    if request.method == "GET":
        data = _policy_json(policy)
        data["can_edit"] = can_manage_placement(request.user)
        return Response(data)

    if not can_manage_placement(request.user):
        return Response({"detail": "Only the placement officer can change the policy."},
                        status=status.HTTP_403_FORBIDDEN)
    try:
        dream = _decimal_or_none(request.data.get("dream_min_lpa"), "Dream package")
        superd = _decimal_or_none(request.data.get("super_dream_min_lpa"), "Super dream package")
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    enabled = bool(request.data.get("tiers_enabled"))
    if enabled and dream is None and superd is None:
        return Response({"detail": "Set at least the Dream package to turn tiers on."},
                        status=status.HTTP_400_BAD_REQUEST)
    if dream is not None and superd is not None and superd <= dream:
        return Response({"detail": "Super dream package must be higher than Dream."},
                        status=status.HTTP_400_BAD_REQUEST)
    policy.tiers_enabled = enabled
    # college rules: keep the saved value when the field isn't sent
    for field in ("final_year_only", "higher_package_only"):
        if field in request.data:
            setattr(policy, field, bool(request.data.get(field)))
    policy.dream_min_lpa = dream
    policy.super_dream_min_lpa = superd
    policy.updated_by = request.user
    policy.save()
    data = _policy_json(policy)
    data["can_edit"] = True
    return Response(data)


# ===================== NIRF / NAAC =====================
def _passing_years(students):
    """{student_id: passing_year} -- batch_year + course duration (as exams.services)."""
    duration = {}
    out = {}
    for s in students:
        if not s.batch_year or not s.course_id:
            continue
        if s.course_id not in duration:
            duration[s.course_id] = s.course.years.count()
        if duration[s.course_id] > 0:
            out[s.id] = s.batch_year + duration[s.course_id]
    return out


def _fmt(d):
    return None if d is None else round(float(d), 2)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def nirf_report(request):
    """
    Per-department placement figures for one graduating batch, in the shape
    NIRF / NAAC ask for: students, placed, median salary, higher studies.
    """
    user = request.user
    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    students = list(
        scope_students_for(user, User.objects.filter(role="student"))
        .select_related("department", "course")
    )
    years_of = _passing_years(students)
    years = sorted(set(years_of.values()), reverse=True)
    if not years:
        return Response({"passing_year": None, "years": [], "rows": [], "totals": None})

    try:
        year = int(request.query_params.get("passing_year") or years[0])
    except ValueError:
        year = years[0]

    batch = [s for s in students if years_of.get(s.id) == year]
    batch_ids = [s.id for s in batch]

    best = {}
    for sid, pkg in (
        Offer.objects
        .filter(application__student_id__in=batch_ids, status="accepted")
        .values_list("application__student_id", "package_lpa")
    ):
        if sid not in best or (pkg is not None and (best[sid] is None or pkg > best[sid])):
            best[sid] = pkg
    higher = set(
        HigherStudies.objects.filter(student_id__in=batch_ids).values_list("student_id", flat=True)
    )

    groups = {}
    for s in batch:
        groups.setdefault(s.department.name if s.department else "No department", []).append(s)

    def summarise(label, members):
        ids = [m.id for m in members]
        placed = [i for i in ids if i in best]
        pkgs = [best[i] for i in placed if best[i] is not None]
        n = len(ids)
        return {
            "department": label,
            "students": n,
            "placed": len(placed),
            "placement_percent": round(len(placed) * 100 / n, 1) if n else 0,
            "median_lpa": _fmt(statistics.median(pkgs)) if pkgs else None,
            "highest_lpa": _fmt(max(pkgs)) if pkgs else None,
            "average_lpa": _fmt(sum(pkgs) / len(pkgs)) if pkgs else None,
            "higher_studies": len([i for i in ids if i in higher]),
        }

    rows = [summarise(k, v) for k, v in sorted(groups.items())]
    return Response({
        "passing_year": year,
        "years": years,
        "rows": rows,
        "totals": summarise("All departments", batch),
    })


# ===================== HIGHER STUDIES =====================
def _hs_json(h):
    s = h.student
    return {
        "id": h.id,
        "student": s.id,
        "student_name": s.username,
        "roll_number": s.roll_number,
        "department_name": s.department.name if s.department else None,
        "institution": h.institution,
        "programme": h.programme,
        "admission_year": h.admission_year,
        "remarks": h.remarks,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def higher_studies_list(request):
    user = request.user
    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
    scoped = scope_students_for(user, User.objects.filter(role="student"))

    if request.method == "POST":
        roll = (request.data.get("roll_number") or "").strip()
        institution = (request.data.get("institution") or "").strip()
        if not roll or not institution:
            return Response({"detail": "Roll number and institution are required."},
                            status=status.HTTP_400_BAD_REQUEST)
        student = scoped.filter(roll_number__iexact=roll).first()
        if not student:
            return Response({"detail": f"No student with roll number {roll} in your scope."},
                            status=status.HTTP_404_NOT_FOUND)
        year = request.data.get("admission_year")
        try:
            year = int(year) if year not in (None, "") else None
        except ValueError:
            return Response({"detail": "Admission year must be a number."},
                            status=status.HTTP_400_BAD_REQUEST)
        h, _ = HigherStudies.objects.update_or_create(
            student=student,
            defaults={
                "institution": institution[:200],
                "programme": (request.data.get("programme") or "").strip()[:150],
                "admission_year": year,
                "remarks": (request.data.get("remarks") or "").strip()[:255],
                "recorded_by": user,
            },
        )
        return Response(_hs_json(h), status=status.HTTP_201_CREATED)

    qs = HigherStudies.objects.filter(student__in=scoped).select_related("student__department", "student__course")
    year = request.query_params.get("passing_year")
    items = list(qs)
    if year:
        years_of = _passing_years([h.student for h in items])
        items = [h for h in items if str(years_of.get(h.student_id)) == str(year)]
    return Response([_hs_json(h) for h in items])


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def higher_studies_detail(request, pk):
    user = request.user
    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
    scoped = scope_students_for(user, User.objects.filter(role="student"))
    h = HigherStudies.objects.filter(pk=pk, student__in=scoped).first()
    if not h:
        return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
    h.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
