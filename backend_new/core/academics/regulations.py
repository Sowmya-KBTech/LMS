"""
WAVE 3 PART 1A - CBCS rules: regulations, categories and credit requirements.

  regulation_for_batch(year)   which regulation an admission batch follows
  regulation_for_student(u)    the same, for a student (User.batch_year)
  subjects_of(reg, course)     the subjects of a course under a regulation
                               (a subject with no regulation = the default one)
  grade_ranges(reg)            the grade scale with each pass grade's "to" mark
  create_regulation(...)       blank, from the template, or a copy
  save_rules(reg, data)        checks and saves pass rules, grades, degree class
  curriculum(course, reg)      credits required vs credits in the subject list

Every number is a college setting. TEMPLATE is only a starting point that the
college checks against its own university's rules.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from .models import (CourseCategory, CreditRequirement, DegreeClass, GradeBand, PassRule, Regulation,
                     RegulationBatch, Subject)
from .models_regulations import GRADE_OUTCOMES, SUBJECT_KINDS


class RegulationError(Exception):
    """A rule was broken. The message is shown to the user as it is."""


KINDS = [k for k, _ in SUBJECT_KINDS]
OUTCOMES = [o for o, _ in GRADE_OUTCOMES]
MAX_GRADES = 15
MAX_CLASSES = 6

# A starting point only (a common pattern in Indian universities).
TEMPLATE = {
    "pass_rules": [
        {"kind": "theory", "internal_max": 40, "end_max": 60, "min_end_pct": 45, "min_total_pct": 50},
        {"kind": "practical", "internal_max": 60, "end_max": 40, "min_end_pct": 50, "min_total_pct": 50},
        {"kind": "project", "internal_max": 40, "end_max": 60, "min_end_pct": 50, "min_total_pct": 50},
    ],
    "grades": [
        {"code": "O", "meaning": "Outstanding", "outcome": "pass", "min_mark": 91, "points": 10},
        {"code": "A+", "meaning": "Excellent", "outcome": "pass", "min_mark": 81, "points": 9},
        {"code": "A", "meaning": "Very good", "outcome": "pass", "min_mark": 71, "points": 8},
        {"code": "B+", "meaning": "Good", "outcome": "pass", "min_mark": 61, "points": 7},
        {"code": "B", "meaning": "Above average", "outcome": "pass", "min_mark": 56, "points": 6},
        {"code": "C", "meaning": "Average", "outcome": "pass", "min_mark": 50, "points": 5},
        {"code": "RA", "meaning": "Re-appear (arrear)", "outcome": "fail", "min_mark": None, "points": 0},
        {"code": "SA", "meaning": "Shortage of attendance", "outcome": "arrear", "min_mark": None, "points": 0},
        {"code": "W", "meaning": "Withdrawn", "outcome": "excluded", "min_mark": None, "points": None},
    ],
    "classes": [
        {"name": "First class with distinction", "min_cgpa": 8.5, "first_attempt_only": True, "extra_years": 0},
        {"name": "First class", "min_cgpa": 6.5, "first_attempt_only": False, "extra_years": 1},
        {"name": "Second class", "min_cgpa": 0, "first_attempt_only": False, "extra_years": None},
    ],
}

TEMPLATE_CATEGORIES = [
    ("HSMC", "Humanities and social sciences", True),
    ("BSC", "Basic sciences", True),
    ("ESC", "Engineering sciences", True),
    ("PCC", "Professional core", True),
    ("PEC", "Professional electives", True),
    ("OEC", "Open electives", True),
    ("EEC", "Employability (projects, internship)", True),
    ("MC", "Mandatory courses (no credit)", False),
]


# ---------------------------------------------------------------- who follows what
def default_regulation():
    return Regulation.objects.filter(is_default=True).first()


def regulation_for_batch(batch_year):
    if batch_year:
        row = RegulationBatch.objects.select_related("regulation").filter(batch_year=batch_year).first()
        if row:
            return row.regulation
    return default_regulation()


def regulation_for_student(student):
    return regulation_for_batch(getattr(student, "batch_year", None))


def subjects_of(regulation, course=None):
    """Subjects under this regulation; a subject with no regulation belongs to the default."""
    q = Q(regulation=regulation)
    if regulation.is_default:
        q |= Q(regulation__isnull=True)
    qs = Subject.objects.filter(q)
    if course is not None:
        qs = qs.filter(year__course=course)
    return qs


# ---------------------------------------------------------------- the grade scale
def grade_ranges(regulation):
    """Grades in order; each pass grade gets 'to' = the next pass grade's start - 1 (top = 100)."""
    grades = list(regulation.grades.all())
    passes = sorted([g for g in grades if g.outcome == "pass"], key=lambda g: g.min_mark, reverse=True)
    upper = {}
    top = Decimal("100")
    for g in passes:
        upper[g.id] = top
        top = g.min_mark - 1
    return [(g, upper.get(g.id)) for g in grades]


def _n(d):
    """50.00 -> '50', 7.5 -> '7.5' (for messages)."""
    return format(Decimal(d).normalize(), "f")


def _num(value, name, lo=None, hi=None, allow_none=False):
    if value in (None, ""):
        if allow_none:
            return None
        raise RegulationError(f"{name} is needed.")
    try:
        d = Decimal(str(value))
    except Exception:
        raise RegulationError(f"{name} must be a number.")
    if lo is not None and d < lo or hi is not None and d > hi:
        raise RegulationError(f"{name} must be between {lo} and {hi}.")
    return d


def _check_rules(data):
    """Turn a regulation's posted rules into clean rows, or raise RegulationError."""
    rules = {}
    for r in data.get("pass_rules") or []:
        kind = r.get("kind")
        if kind not in KINDS or kind in rules:
            raise RegulationError("Give one pass rule each for theory, practical and project.")
        label = kind.capitalize()
        internal = _num(r.get("internal_max"), f"{label}: internal marks", 0, 200)
        end = _num(r.get("end_max"), f"{label}: end-semester marks", 0, 200)
        if internal + end <= 0:
            raise RegulationError(f"{label}: internal and end-semester marks cannot both be 0.")
        if internal != internal.to_integral_value() or end != end.to_integral_value():
            raise RegulationError(f"{label}: marks must be whole numbers.")
        rules[kind] = {"kind": kind, "internal_max": int(internal), "end_max": int(end),
                       "min_end_pct": _num(r.get("min_end_pct"), f"{label}: pass mark in the end-semester exam", 0, 100),
                       "min_total_pct": _num(r.get("min_total_pct"), f"{label}: pass mark in the total", 0, 100)}
    if set(rules) != set(KINDS):
        raise RegulationError("Give one pass rule each for theory, practical and project.")

    grades, codes = [], set()
    for i, g in enumerate(data.get("grades") or [], start=1):
        code = str(g.get("code") or "").strip().upper()
        if not code or len(code) > 4:
            raise RegulationError(f"Grade {i}: write a short grade code (up to 4 letters).")
        if code in codes:
            raise RegulationError(f"Grade {code} is listed twice.")
        codes.add(code)
        outcome = g.get("outcome") or "pass"
        if outcome not in OUTCOMES:
            raise RegulationError(f"Grade {code}: choose what it counts as.")
        row = {"code": code, "meaning": str(g.get("meaning") or "").strip()[:60], "outcome": outcome, "order": i,
               "min_mark": None, "points": None}
        if outcome == "pass":
            row["min_mark"] = _num(g.get("min_mark"), f"Grade {code}: marks from", 0, 100)
            row["points"] = _num(g.get("points"), f"Grade {code}: grade points", 0, 10)
        elif outcome in ("fail", "arrear"):
            row["points"] = Decimal("0")
        grades.append(row)
    if not grades or len(grades) > MAX_GRADES:
        raise RegulationError(f"Give the grade scale (1 to {MAX_GRADES} grades).")
    passes = [g for g in grades if g["outcome"] == "pass"]
    if not passes:
        raise RegulationError("Add at least one pass grade.")
    if sum(1 for g in grades if g["outcome"] == "fail") != 1:
        raise RegulationError("Mark exactly one grade as 'Arrear · write again' (e.g. RA). "
                              "It is given when a pass rule is not met.")
    starts = [g["min_mark"] for g in passes]
    if len(set(starts)) != len(starts):
        raise RegulationError("Two pass grades start at the same mark.")
    lowest_pass = min(r["min_total_pct"] for r in rules.values())
    if min(starts) > lowest_pass:
        raise RegulationError(f"The lowest pass grade starts at {_n(min(starts))}%, but a student can pass with "
                              f"{_n(lowest_pass)}%. Make it start at {_n(lowest_pass)} or lower.")
    by_start = sorted(passes, key=lambda g: g["min_mark"])
    for low, high in zip(by_start, by_start[1:]):
        if high["points"] < low["points"]:
            raise RegulationError(f"Grade {high['code']} is for higher marks than {low['code']} "
                                  f"but has fewer grade points.")

    classes = []
    for i, c in enumerate(data.get("classes") or [], start=1):
        name = str(c.get("name") or "").strip()[:60]
        if not name:
            raise RegulationError(f"Degree class {i}: give it a name.")
        extra = c.get("extra_years")
        classes.append({"name": name, "order": i,
                        "min_cgpa": _num(c.get("min_cgpa"), f"{name}: minimum CGPA", 0, 10),
                        "first_attempt_only": bool(c.get("first_attempt_only")),
                        "extra_years": None if extra in (None, "") else int(_num(extra, f"{name}: extra years", 0, 10))})
    if len(classes) > MAX_CLASSES:
        raise RegulationError(f"At most {MAX_CLASSES} degree classes.")
    return list(rules.values()), grades, classes


@transaction.atomic
def save_rules(regulation, data):
    """Replace a regulation's pass rules, grade scale and degree classes (all or nothing)."""
    rules, grades, classes = _check_rules(data)
    for key in ("arrears_in_gpa", "reattempt_internal"):
        if key in data:
            valid = [v for v, _ in Regulation._meta.get_field(key).choices]
            if data[key] not in valid:
                raise RegulationError("Choose one of the options for each setting.")
            setattr(regulation, key, data[key])
    if "description" in data:
        regulation.description = str(data.get("description") or "").strip()[:200]
    if "name" in data:
        _set_name(regulation, data["name"])
    regulation.save()
    regulation.pass_rules.all().delete()
    regulation.grades.all().delete()
    regulation.classes.all().delete()
    PassRule.objects.bulk_create([PassRule(regulation=regulation, **r) for r in rules])
    GradeBand.objects.bulk_create([GradeBand(regulation=regulation, **g) for g in grades])
    DegreeClass.objects.bulk_create([DegreeClass(regulation=regulation, **c) for c in classes])
    return regulation


def _set_name(regulation, name):
    name = str(name or "").strip()
    if not name or len(name) > 30:
        raise RegulationError("Give the regulation a short name, like R2021.")
    if Regulation.objects.filter(name__iexact=name).exclude(pk=regulation.pk).exists():
        raise RegulationError(f"A regulation named {name} already exists.")
    regulation.name = name


def _rules_of(regulation):
    return {
        "pass_rules": list(regulation.pass_rules.values("kind", "internal_max", "end_max", "min_end_pct",
                                                         "min_total_pct")),
        "grades": list(regulation.grades.values("code", "meaning", "outcome", "min_mark", "points")),
        "classes": list(regulation.classes.values("name", "min_cgpa", "first_attempt_only", "extra_years")),
    }


@transaction.atomic
def create_regulation(name, start_from, by, copy_from=None):
    """start_from: 'template' (the starting point above), 'copy' (of copy_from) or 'blank'."""
    reg = Regulation(created_by=by)
    _set_name(reg, name)
    reg.is_default = not Regulation.objects.filter(is_default=True).exists()   # the first one is the default
    if start_from == "copy":
        if copy_from is None:
            raise RegulationError("Choose the regulation to copy.")
        reg.arrears_in_gpa = copy_from.arrears_in_gpa
        reg.reattempt_internal = copy_from.reattempt_internal
        reg.save()
        save_rules(reg, _rules_of(copy_from))
        CreditRequirement.objects.bulk_create([
            CreditRequirement(regulation=reg, course_id=r.course_id, category_id=r.category_id, credits=r.credits)
            for r in copy_from.requirements.all()])
    elif start_from == "template":
        reg.save()
        save_rules(reg, TEMPLATE)
    elif start_from == "blank":
        reg.save()
        # a blank regulation still needs its three pass rules (all zero = "fill me in")
        PassRule.objects.bulk_create([PassRule(regulation=reg, kind=k, internal_max=0, end_max=0,
                                               min_end_pct=0, min_total_pct=0) for k in KINDS])
    else:
        raise RegulationError("Choose how to start: from the template, a copy or blank.")
    return reg


@transaction.atomic
def make_default(regulation):
    Regulation.objects.filter(is_default=True).exclude(pk=regulation.pk).update(is_default=False)
    regulation.is_default = True
    regulation.save(update_fields=["is_default"])
    return regulation


def assign_batch(regulation, batch_year):
    try:
        year = int(batch_year)
    except (TypeError, ValueError):
        raise RegulationError("Give the batch's admission year, like 2024.")
    if not 2000 <= year <= 2100:
        raise RegulationError("Give the batch's admission year, like 2024.")
    row, _ = RegulationBatch.objects.update_or_create(batch_year=year, defaults={"regulation": regulation})
    return row


def can_delete(regulation):
    if regulation.is_default:
        return "The default regulation cannot be deleted. Make another one the default first."
    if regulation.batches.exists():
        return "Batches follow this regulation. Move them to another regulation first."
    if regulation.subjects.exists():
        return "Subjects belong to this regulation. Move them first."
    return None


def add_template_categories():
    made = 0
    top = CourseCategory.objects.order_by("-order").values_list("order", flat=True).first() or 0
    for i, (code, name, credit) in enumerate(TEMPLATE_CATEGORIES, start=1):
        _, created = CourseCategory.objects.get_or_create(
            code=code, defaults={"name": name, "carries_credit": credit, "order": top + i})
        made += created
    return made


# ---------------------------------------------------------------- credits
def _fmt(d):
    return float(d) if d is not None else 0.0


def curriculum(course, regulation):
    """Credits required (per category) against the credits in the course's subject list."""
    subjects = list(subjects_of(regulation, course).select_related("category", "year").order_by("semester", "code", "name"))
    required = {r.category_id: r.credits for r in CreditRequirement.objects.filter(regulation=regulation, course=course)}
    have = {}
    for s in subjects:
        if s.category_id:
            have[s.category_id] = have.get(s.category_id, Decimal("0")) + (s.credits or 0)
    cats = []
    for c in CourseCategory.objects.all():
        req = required.get(c.id, Decimal("0"))
        got = have.get(c.id, Decimal("0"))
        if not c.carries_credit:
            check = "no_credit"
        elif got == req:
            check = "ok"
        elif got < req:
            check = "short"
        else:
            check = "over"
        cats.append({"id": c.id, "code": c.code, "name": c.name, "carries_credit": c.carries_credit,
                     "required": _fmt(req), "have": _fmt(got), "check": check,
                     "difference": _fmt(got - req)})
    semesters = {}
    for s in subjects:
        semesters.setdefault(s.semester, []).append({
            "id": s.id, "code": s.code or "", "name": s.name, "credits": _fmt(s.credits),
            "category": s.category_id, "category_code": s.category.code if s.category_id else "",
            "kind": s.kind, "lecture_hours": s.lecture_hours, "tutorial_hours": s.tutorial_hours,
            "practical_hours": s.practical_hours, "is_elective": s.is_elective,
            "own_regulation": s.regulation_id is not None,
        })
    total_required = sum((v for v in required.values()), Decimal("0"))
    total_have = sum((s.credits or 0 for s in subjects if not (s.category_id and not s.category.carries_credit)),
                     Decimal("0"))
    return {
        "course": {"id": course.id, "name": course.name},
        "regulation": {"id": regulation.id, "name": regulation.name, "is_default": regulation.is_default},
        "total_required": _fmt(total_required),
        "total_have": _fmt(total_have),
        "difference": _fmt(total_have - total_required),
        "no_category": sum(1 for s in subjects if not s.category_id),
        "categories": cats,
        "semesters": [{"semester": n, "credits": _fmt(sum((x["credits"] for x in rows), 0)), "subjects": rows}
                      for n, rows in sorted(semesters.items())],
    }


@transaction.atomic
def save_requirements(course, regulation, items):
    cats = {c.id: c for c in CourseCategory.objects.all()}
    clean = {}
    for it in items or []:
        cid = it.get("category")
        if cid not in cats:
            raise RegulationError("Unknown category.")
        clean[cid] = _num(it.get("credits"), f"{cats[cid].code}: credits required", 0, 400)
        if (clean[cid] * 2) != (clean[cid] * 2).to_integral_value():
            raise RegulationError(f"{cats[cid].code}: credits must be whole or half.")
    for cid, credits in clean.items():
        CreditRequirement.objects.update_or_create(regulation=regulation, course=course, category_id=cid,
                                                   defaults={"credits": credits})
