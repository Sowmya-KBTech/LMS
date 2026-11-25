"""
CO-PO PART A - programme outcomes, CO-PO mapping and attainment rules (rules + API).

  GET    /api/outcomes/programme/?course=<id>     POs (whole college) + that course's PSOs
  POST   /api/outcomes/programme/                 {kind: po|pso, course?, text}   code PO13 / PSO3 is given
  PATCH  /api/outcomes/programme/<id>/            {text}
  DELETE /api/outcomes/programme/<id>/            refused while any CO is mapped to it
  POST   /api/outcomes/programme/standard/        adds whichever of the 12 standard POs are missing
  GET    /api/outcomes/subjects/?course=<id>      the course's subjects and how far their mapping is
  GET    /api/outcomes/mapping/<subject_id>/      COs x (POs + PSOs) grid with 1 / 2 / 3
  PUT    /api/outcomes/mapping/<subject_id>/      {cells: [{co, po, strength}]} replaces the subject's grid
  GET    /api/outcomes/rules/?department=<id>     the rules in force (the department's own, else the college's)
  PUT    /api/outcomes/rules/?department=<id>     save (no department = the college rules)
  DELETE /api/outcomes/rules/?department=<id>     the department goes back to the college rules

Who
  * POs (whole college) and the college rules: college admins
  * a course's PSOs: college admins, and the HOD of a department that teaches the course
  * a subject's mapping: its teachers, its HOD, college admins (same rule as editing its COs)
  * a department's own rules: its HOD and college admins
  * reading: any staff member
"""
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AttainmentRule, COPOMap, CourseOutcome, ProgramOutcome
from .views import can_edit_outcomes, hod_departments

# The 12 programme outcomes every engineering programme in India uses (short titles)
STANDARD_POS = [
    "Engineering knowledge", "Problem analysis", "Design and development of solutions",
    "Investigation of complex problems", "Modern tool usage", "The engineer and society",
    "Environment and sustainability", "Ethics", "Individual and team work", "Communication",
    "Project management and finance", "Life-long learning",
]
RULE_INTS = {
    "student_target_pct": (1, 100), "level3_pct": (1, 100), "level2_pct": (1, 100), "level1_pct": (1, 100),
    "internal_share": (0, 100), "direct_share": (0, 100), "survey_min_pct": (0, 100),
}
RULE_BOOLS = ("use_ia", "use_online_tests", "use_assignments")


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def _is_admin(user):
    from core.permissions import is_college_admin
    return is_college_admin(user)


def _is_staff(user):
    return _is_admin(user) or getattr(user, "role", None) == "teacher"


def _model(name):
    return apps.get_model("courses", name)


# ============================================================ who ===
def can_edit_psos(user, course_id):
    if _is_admin(user):
        return True
    depts = hod_departments(user)
    if not course_id or not depts.exists():
        return False
    Subject, TA = _model("Subject"), _model("TeachingAssignment")
    return (Subject.objects.filter(year__course_id=course_id, department__in=depts).exists()
            or TA.objects.filter(course_id=course_id, teacher__department__in=depts).exists())


def can_edit_rules(user, department_id):
    if _is_admin(user):
        return True
    return bool(department_id) and hod_departments(user).filter(id=department_id).exists()


# ============================================================ data ===
def outcome_row(po):
    return {"id": po.id, "kind": po.kind, "code": po.code, "text": po.text, "course": po.course_id,
            "links": getattr(po, "n_links", None)}


def outcomes_for_course(course_id):
    """The college POs, then this course's PSOs."""
    pos = list(ProgramOutcome.objects.filter(course__isnull=True, kind=ProgramOutcome.PO).order_by("order", "id"))
    psos = list(ProgramOutcome.objects.filter(course_id=course_id, kind=ProgramOutcome.PSO)
                .order_by("order", "id")) if course_id else []
    return pos, psos


def _next_code(kind, course_id):
    prefix = "PO" if kind == ProgramOutcome.PO else "PSO"
    qs = ProgramOutcome.objects.filter(kind=kind)
    qs = qs.filter(course__isnull=True) if kind == ProgramOutcome.PO else qs.filter(course_id=course_id)
    used = set(qs.values_list("code", flat=True))
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}", n


def subject_course_id(subject):
    return subject.year.course_id if subject.year_id else None


def mapping_view(subject, user):
    course_id = subject_course_id(subject)
    pos, psos = outcomes_for_course(course_id)
    cos = list(CourseOutcome.objects.filter(subject=subject).order_by("order", "id"))
    cells = {f"{m.outcome_id}-{m.program_outcome_id}": m.strength
             for m in COPOMap.objects.filter(outcome__subject=subject)}
    columns = pos + psos
    average = {}
    for po in columns:
        vals = [cells[f"{co.id}-{po.id}"] for co in cos if f"{co.id}-{po.id}" in cells]
        average[po.id] = round(sum(vals) / len(vals), 1) if vals else None
    return {
        "subject": {"id": subject.id, "code": subject.code or "", "name": subject.name,
                    "semester": subject.semester, "course": course_id},
        "cos": [{"id": c.id, "code": c.code, "text": c.text} for c in cos],
        "columns": [outcome_row(p) for p in columns],
        "cells": cells, "average": average,
        "can_edit": can_edit_outcomes(user, subject.id),
    }


def rule_row(rule, department_id, inherited):
    data = {f: getattr(rule, f) for f in list(RULE_INTS) + list(RULE_BOOLS)}
    data.update(co_target=float(rule.co_target), po_target=float(rule.po_target),
                department=department_id, inherited=inherited, updated_at=rule.updated_at)
    return data


def college_rule():
    rule = AttainmentRule.objects.filter(department__isnull=True).first()
    return rule or AttainmentRule.objects.create()


def rule_for(department_id):
    """(rule, inherited) - the department's own rules when it has them, else the college's."""
    if department_id:
        own = AttainmentRule.objects.filter(department_id=department_id).first()
        if own:
            return own, False
        return college_rule(), True
    return college_rule(), False


def _clean_rule(data, rule):
    errors = {}
    for f, (lo, hi) in RULE_INTS.items():
        if f in data:
            try:
                v = int(data[f])
                if not lo <= v <= hi:
                    raise ValueError
                setattr(rule, f, v)
            except (TypeError, ValueError):
                errors[f] = f"Enter a whole number from {lo} to {hi}."
    for f in ("co_target", "po_target"):
        if f in data:
            try:
                v = Decimal(str(data[f]))
                if not Decimal(0) <= v <= Decimal(3):
                    raise InvalidOperation
                setattr(rule, f, v.quantize(Decimal("0.01")))
            except (InvalidOperation, ValueError):
                errors[f] = "Enter a level from 0 to 3."
    for f in RULE_BOOLS:
        if f in data:
            setattr(rule, f, data[f] in (True, "true", "True", "1", 1, "on"))
    if not errors and not (rule.level3_pct > rule.level2_pct > rule.level1_pct):
        errors["level3_pct"] = "Level 3 needs more students than level 2, and level 2 more than level 1."
    if not errors and not (rule.use_ia or rule.use_online_tests or rule.use_assignments):
        errors["use_ia"] = "Choose at least one source of internal marks."
    return errors


# ============================================================ API: POs / PSOs ===
def _course_id(value):
    return int(value) if str(value or "").isdigit() else None


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def programme_outcomes(request):
    user = request.user
    if not _is_staff(user):
        return _error("Only staff can see programme outcomes.", status.HTTP_403_FORBIDDEN)
    if request.method == "GET":
        from django.db.models import Count
        course_id = _course_id(request.query_params.get("course"))
        pos, psos = outcomes_for_course(course_id)
        counts = dict(ProgramOutcome.objects.filter(id__in=[p.id for p in pos + psos])
                      .annotate(n=Count("co_links")).values_list("id", "n"))
        for p in pos + psos:
            p.n_links = counts.get(p.id, 0)
        return Response({"pos": [outcome_row(p) for p in pos], "psos": [outcome_row(p) for p in psos],
                         "can_edit_pos": _is_admin(user),
                         "can_edit_psos": bool(course_id) and can_edit_psos(user, course_id)})

    kind = request.data.get("kind")
    text = (request.data.get("text") or "").strip()
    course_id = _course_id(request.data.get("course"))
    if kind not in (ProgramOutcome.PO, ProgramOutcome.PSO):
        return _error("Choose PO or PSO.")
    if not text:
        return _error("Write the outcome.")
    if kind == ProgramOutcome.PO:
        if not _is_admin(user):
            return _error("Only a college admin changes the POs.", status.HTTP_403_FORBIDDEN)
        course_id = None
    else:
        if not course_id or not _model("Course").objects.filter(pk=course_id).exists():
            return _error("Choose the course this PSO belongs to.")
        if not can_edit_psos(user, course_id):
            return _error("Only a college admin or this course's HOD changes its PSOs.", status.HTTP_403_FORBIDDEN)
    code, n = _next_code(kind, course_id)
    po = ProgramOutcome.objects.create(kind=kind, course_id=course_id, code=code, text=text[:300], order=n)
    return Response(outcome_row(po), status=status.HTTP_201_CREATED)


def _may_edit(user, po):
    return _is_admin(user) if po.kind == ProgramOutcome.PO else can_edit_psos(user, po.course_id)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def programme_outcome_detail(request, pk):
    po = ProgramOutcome.objects.filter(pk=pk).first()
    if po is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    if not _may_edit(request.user, po):
        return _error("You can't change this outcome.", status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        n = po.co_links.count()
        if n:
            return _error(f"{n} course outcome(s) are mapped to {po.code}. Clear them from the mapping first.")
        po.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    text = (request.data.get("text") or "").strip()
    if not text:
        return _error("Write the outcome.")
    po.text = text[:300]
    po.save(update_fields=["text"])
    return Response(outcome_row(po))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def programme_outcomes_standard(request):
    if not _is_admin(request.user):
        return _error("Only a college admin changes the POs.", status.HTTP_403_FORBIDDEN)
    have = set(ProgramOutcome.objects.filter(course__isnull=True).values_list("code", flat=True))
    added = [ProgramOutcome(kind=ProgramOutcome.PO, code=f"PO{i}", text=t, order=i)
             for i, t in enumerate(STANDARD_POS, start=1) if f"PO{i}" not in have]
    ProgramOutcome.objects.bulk_create(added)
    return Response({"added": len(added)})


# ============================================================ API: mapping ===
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mapping_subjects(request):
    """The course's subjects, each with its CO count and how many COs are mapped."""
    from django.db.models import Count, Q
    if not _is_staff(request.user):
        return _error("Only staff.", status.HTTP_403_FORBIDDEN)
    course_id = _course_id(request.query_params.get("course"))
    if not course_id:
        return Response([])
    subjects = (_model("Subject").objects.filter(year__course_id=course_id)
                .annotate(n_cos=Count("course_outcomes", distinct=True),
                          n_mapped=Count("course_outcomes", filter=Q(course_outcomes__po_links__isnull=False),
                                         distinct=True))
                .order_by("semester", "code", "name"))
    return Response([{"id": s.id, "code": s.code or "", "name": s.name, "semester": s.semester,
                      "cos": s.n_cos, "mapped": s.n_mapped} for s in subjects])


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def mapping_detail(request, subject_id):
    user = request.user
    if not _is_staff(user):
        return _error("Only staff.", status.HTTP_403_FORBIDDEN)
    subject = _model("Subject").objects.select_related("year").filter(pk=subject_id).first()
    if subject is None:
        return _error("Subject not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        return Response(mapping_view(subject, user))
    if not can_edit_outcomes(user, subject.id):
        return _error("Only this subject's teachers, its HOD or an admin can change its mapping.",
                      status.HTTP_403_FORBIDDEN)
    rows = request.data.get("cells")
    if not isinstance(rows, list):
        return _error("Send the list of cells.")
    pos, psos = outcomes_for_course(subject_course_id(subject))
    allowed_po = {p.id for p in pos + psos}
    allowed_co = set(CourseOutcome.objects.filter(subject=subject).values_list("id", flat=True))
    links, seen = [], set()
    for row in rows:
        try:
            co, po, strength = int(row.get("co")), int(row.get("po")), int(row.get("strength") or 0)
        except (TypeError, ValueError, AttributeError):
            return _error("Each cell needs a CO, a PO and a strength.")
        if co not in allowed_co or po not in allowed_po:
            return _error("That CO or PO doesn't belong to this subject's course.")
        if strength not in (0, 1, 2, 3):
            return _error("Strength is 1 (low), 2 (medium) or 3 (high).")
        if (co, po) in seen:
            return _error("Each CO and PO pair can be given once.")
        seen.add((co, po))
        if strength:
            links.append(COPOMap(outcome_id=co, program_outcome_id=po, strength=strength))
    with transaction.atomic():
        COPOMap.objects.filter(outcome__subject=subject).delete()
        COPOMap.objects.bulk_create(links)
    return Response(mapping_view(subject, user))


# ============================================================ API: rules ===
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def attainment_rules(request):
    user = request.user
    if not _is_staff(user):
        return _error("Only staff.", status.HTTP_403_FORBIDDEN)
    dept_id = _course_id(request.query_params.get("department"))
    if dept_id and not apps.get_model("users", "Department").objects.filter(pk=dept_id).exists():
        return _error("Department not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        rule, inherited = rule_for(dept_id)
        data = rule_row(rule, dept_id, inherited)
        data["can_edit"] = can_edit_rules(user, dept_id)
        return Response(data)
    if not can_edit_rules(user, dept_id):
        return _error("Only a college admin, or this department's HOD, changes these rules.",
                      status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        if dept_id:
            AttainmentRule.objects.filter(department_id=dept_id).delete()
        rule, inherited = rule_for(dept_id)
        return Response(rule_row(rule, dept_id, inherited))
    if dept_id:
        rule = AttainmentRule.objects.filter(department_id=dept_id).first()
        if rule is None:                         # start from the college numbers
            base = college_rule()
            rule = AttainmentRule(department_id=dept_id, **{f: getattr(base, f) for f in
                                  list(RULE_INTS) + list(RULE_BOOLS) + ["co_target", "po_target"]})
    else:
        rule = college_rule()
    errors = _clean_rule(request.data, rule)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    rule.updated_by = user
    rule.save()
    data = rule_row(rule, dept_id, False)
    data["can_edit"] = True
    return Response(data)
