
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import regulations as R
from .models import Course, CourseCategory, Regulation, RegulationBatch
from .models_regulations import ARREARS_IN_GPA, GRADE_OUTCOMES, REATTEMPT_INTERNAL, SUBJECT_KINDS
from .permissions import can_manage_academics


def can_manage_regulations(user):
    """The academic admin (and main admin), or the exam admin."""
    if can_manage_academics(user):
        return True
    return getattr(user, "role", "") == "admin" and (user.sub_role or "") == "exam_admin"


def _is_staff(user):
    return user.is_superuser or getattr(user, "role", "") in ("admin", "teacher")


def _deny(text="Only the academic or exam admin can change regulations."):
    return Response({"detail": text}, status=403)


def _students_by_batch():
    User = get_user_model()
    return dict(User.objects.filter(role="student", is_active=True, batch_year__isnull=False)
                .values_list("batch_year").annotate(n=Count("id")))


def _f(d):
    return None if d is None else float(d)


def _summary(reg, students=None):
    students = students if students is not None else _students_by_batch()
    years = list(reg.batches.values_list("batch_year", flat=True))
    return {"id": reg.id, "name": reg.name, "description": reg.description, "is_default": reg.is_default,
            "batches": years, "students": sum(students.get(y, 0) for y in years)}


def _detail(reg, user):
    data = _summary(reg)
    data.update({
        "arrears_in_gpa": reg.arrears_in_gpa,
        "reattempt_internal": reg.reattempt_internal,
        "subjects": reg.subjects.count(),
        "can_edit": can_manage_regulations(user),
        "can_delete_reason": R.can_delete(reg),
        "pass_rules": [{"kind": r.kind, "kind_label": r.get_kind_display(), "internal_max": r.internal_max,
                        "end_max": r.end_max, "min_end_pct": _f(r.min_end_pct), "min_total_pct": _f(r.min_total_pct)}
                       for r in sorted(reg.pass_rules.all(), key=lambda r: R.KINDS.index(r.kind))],
        "grades": [{"code": g.code, "meaning": g.meaning, "outcome": g.outcome,
                    "outcome_label": g.get_outcome_display(), "min_mark": _f(g.min_mark),
                    "max_mark": _f(top), "points": _f(g.points)} for g, top in R.grade_ranges(reg)],
        "classes": [{"name": c.name, "min_cgpa": _f(c.min_cgpa), "first_attempt_only": c.first_attempt_only,
                     "extra_years": c.extra_years} for c in reg.classes.all()],
    })
    return data


# ---------------------------------------------------------------- regulations
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def regulation_list(request):
    if not _is_staff(request.user):
        return Response({"detail": "Only staff can see regulations."}, status=403)
    if request.method == "GET":
        students = _students_by_batch()
        assigned = set(RegulationBatch.objects.values_list("batch_year", flat=True))
        return Response({
            "regulations": [_summary(r, students) for r in Regulation.objects.all()],
            "unassigned_batches": sorted(y for y in students if y not in assigned),
            "can_edit": can_manage_regulations(request.user),
            "options": {
                "kinds": [{"value": v, "label": l} for v, l in SUBJECT_KINDS],
                "outcomes": [{"value": v, "label": l} for v, l in GRADE_OUTCOMES],
                "arrears_in_gpa": [{"value": v, "label": l} for v, l in ARREARS_IN_GPA],
                "reattempt_internal": [{"value": v, "label": l} for v, l in REATTEMPT_INTERNAL],
            },
        })
    if not can_manage_regulations(request.user):
        return _deny()
    copy_from = None
    if request.data.get("start_from") == "copy":
        copy_from = Regulation.objects.filter(pk=request.data.get("copy_from")).first() \
            if str(request.data.get("copy_from") or "").isdigit() else None
    try:
        reg = R.create_regulation(request.data.get("name"), request.data.get("start_from"), request.user,
                                  copy_from=copy_from)
    except R.RegulationError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(_detail(reg, request.user), status=201)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def regulation_detail(request, pk):
    if not _is_staff(request.user):
        return Response({"detail": "Only staff can see regulations."}, status=403)
    reg = get_object_or_404(Regulation, pk=pk)
    if request.method == "GET":
        return Response(_detail(reg, request.user))
    if not can_manage_regulations(request.user):
        return _deny()
    if request.method == "DELETE":
        reason = R.can_delete(reg)
        if reason:
            return Response({"detail": reason}, status=400)
        reg.delete()
        return Response(status=204)
    try:
        R.save_rules(reg, request.data)
    except R.RegulationError as e:
        return Response({"detail": str(e)}, status=400)
    reg.refresh_from_db()
    return Response(_detail(reg, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def regulation_make_default(request, pk):
    if not can_manage_regulations(request.user):
        return _deny()
    reg = get_object_or_404(Regulation, pk=pk)
    R.make_default(reg)
    return Response(_detail(reg, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def regulation_add_batch(request, pk):
    if not can_manage_regulations(request.user):
        return _deny()
    reg = get_object_or_404(Regulation, pk=pk)
    try:
        R.assign_batch(reg, request.data.get("batch_year"))
    except R.RegulationError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(_detail(reg, request.user))


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def regulation_remove_batch(request, pk, year):
    if not can_manage_regulations(request.user):
        return _deny()
    reg = get_object_or_404(Regulation, pk=pk)
    RegulationBatch.objects.filter(regulation=reg, batch_year=year).delete()
    return Response(_detail(reg, request.user))


# ---------------------------------------------------------------- categories
def _category(c):
    return {"id": c.id, "code": c.code, "name": c.name, "carries_credit": c.carries_credit, "order": c.order}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def category_list(request):
    if not _is_staff(request.user):
        return Response({"detail": "Only staff can see categories."}, status=403)
    if request.method == "GET":
        return Response([_category(c) for c in CourseCategory.objects.all()])
    if not can_manage_academics(request.user):
        return _deny("Only the academic admin can change categories.")
    code = str(request.data.get("code") or "").strip().upper()
    name = str(request.data.get("name") or "").strip()
    if not code or len(code) > 10 or not code.replace("-", "").isalnum():
        return Response({"detail": "Give a short code of letters and numbers, like PCC."}, status=400)
    if not name:
        return Response({"detail": "Give the category a name."}, status=400)
    if CourseCategory.objects.filter(code=code).exists():
        return Response({"detail": f"{code} already exists."}, status=400)
    top = CourseCategory.objects.order_by("-order").values_list("order", flat=True).first() or 0
    c = CourseCategory.objects.create(code=code, name=name[:80], order=top + 1,
                                      carries_credit=bool(request.data.get("carries_credit", True)))
    return Response(_category(c), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def category_template(request):
    if not can_manage_academics(request.user):
        return _deny("Only the academic admin can change categories.")
    made = R.add_template_categories()
    return Response({"added": made, "categories": [_category(c) for c in CourseCategory.objects.all()]})


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def category_detail(request, pk):
    if not can_manage_academics(request.user):
        return _deny("Only the academic admin can change categories.")
    c = get_object_or_404(CourseCategory, pk=pk)
    if request.method == "DELETE":
        # Blocked only by real use: a subject in this category, or a course
        # that needs more than 0 credits of it. A saved "0 credits required"
        # row is just the page's default and is removed with the category.
        n_subjects = c.subjects.count()
        if n_subjects:
            return Response({"detail": f"{c.code} is used by {n_subjects} subject{'s' if n_subjects != 1 else ''}. "
                                       f"Move them to another category first."}, status=400)
        if c.requirements.filter(credits__gt=0).exists():
            return Response({"detail": f"A course still needs credits in {c.code}. "
                                       f"Set its credits required to 0 first."}, status=400)
        c.delete()                       # its 0-credit requirement rows go with it (CASCADE)
        return Response(status=204)
    if "name" in request.data:
        name = str(request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "Give the category a name."}, status=400)
        c.name = name[:80]
    if "carries_credit" in request.data:
        c.carries_credit = bool(request.data.get("carries_credit"))
    c.save()
    return Response(_category(c))


# ---------------------------------------------------------------- curriculum
def _course_and_regulation(source):
    course = get_object_or_404(Course, pk=source.get("course")) if str(source.get("course") or "").isdigit() else None
    reg_id = source.get("regulation")
    reg = (get_object_or_404(Regulation, pk=reg_id) if str(reg_id or "").isdigit() else R.default_regulation())
    return course, reg


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def curriculum_view(request):
    if not _is_staff(request.user):
        return Response({"detail": "Only staff can see this."}, status=403)
    course, reg = _course_and_regulation(request.query_params)
    if course is None:
        return Response({"detail": "Choose a course."}, status=400)
    if reg is None:
        return Response({"detail": "Create a regulation first."}, status=400)
    data = R.curriculum(course, reg)
    data["can_edit"] = can_manage_academics(request.user)
    return Response(data)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def curriculum_requirements(request):
    if not can_manage_academics(request.user):
        return _deny("Only the academic admin can change credit requirements.")
    course, reg = _course_and_regulation(request.data)
    if course is None or reg is None:
        return Response({"detail": "Choose a course and a regulation."}, status=400)
    try:
        R.save_requirements(course, reg, request.data.get("items"))
    except R.RegulationError as e:
        return Response({"detail": str(e)}, status=400)
    data = R.curriculum(course, reg)
    data["can_edit"] = True
    return Response(data)