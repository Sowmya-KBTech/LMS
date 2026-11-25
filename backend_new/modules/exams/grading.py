"""
WAVE 3 PART 1B - results under the student's regulation (CBCS).

  rules_for(student, subject)     the regulation, its pass rule for the subject's
                                  type, and its grade scale - or None (no
                                  regulation set up: the old fixed bands are used)
  grade(rules, ...)               grade, pass, grade points, outcome from marks
  record_result(...)              save one subject's result for one student,
                                  including arrear ATTEMPTS (a re-exam in a later
                                  session moves the old marks into the history)
  semester_summary(student)       SGPA per published semester, CGPA, credits,
                                  arrears with every attempt, degree class so far

Rules
  * The student's regulation decides (their admission batch, else the default).
  * Marks may come as internal + end-semester (checked against the pass rule) or
    as one total (only the total pass mark can be checked).
  * Failing a pass rule, or no marks (absent), gives the regulation's
    "Arrear · write again" grade (RA).
  * SA / W style grades are given by hand.
  * SGPA / CGPA: arrear subjects are left out until passed, or counted with 0
    points - the regulation's setting. W is never counted. Subjects whose
    category carries no credit (MC) are never counted.
"""
from decimal import Decimal

from django.db import transaction

from .models import ResultAttempt, ResultEntry, SemesterResult
from .services import compute_grade, GRADE_POINTS


class GradingError(Exception):
    """A mark or grade is not valid. The message is shown to the user."""


# ---------------------------------------------------------------- rules
def rules_for(student, subject):
    from core.academics.regulations import regulation_for_student
    reg = regulation_for_student(student)
    if reg is None:
        return None
    rule = reg.pass_rules.filter(kind=getattr(subject, "kind", "theory") or "theory").first()
    grades = list(reg.grades.all())
    if rule is None or not any(g.outcome == "fail" for g in grades):
        return None                                    # an unfinished regulation: old behaviour
    return {"regulation": reg, "rule": rule, "grades": grades}


def _f(v):
    return None if v is None else float(v)


def _pct(part, whole):
    return (float(part) * 100.0 / float(whole)) if whole else 0.0


def grade(rules, internal=None, end=None, total=None, max_marks=None, manual=None):
    """
    Returns a dict: grade, is_pass, points (Decimal|None), outcome,
    marks_obtained, max_marks, internal_marks, end_marks.
    Raises GradingError for marks out of range or an unknown manual grade.
    """
    if rules is None:                                   # no regulation: the old fixed bands
        if internal is not None or end is not None:
            raise GradingError("Internal and end-semester marks need a regulation. Enter the total instead.")
        if manual:
            raise GradingError("SA / W grades need a regulation.")
        mx = max_marks or 100
        if total is not None and not 0 <= total <= mx:
            raise GradingError(f"Marks {total:g} are out of range (0 to {mx}).")
        g, ok = compute_grade(total, mx)
        return {"grade": g, "is_pass": ok, "points": None, "outcome": "", "marks_obtained": total,
                "max_marks": mx, "internal_marks": None, "end_marks": None}

    rule, grades = rules["rule"], rules["grades"]
    by_code = {g.code: g for g in grades}
    fail = next(g for g in grades if g.outcome == "fail")

    if manual:
        g = by_code.get(str(manual).strip().upper())
        if g is None or g.outcome not in ("arrear", "excluded"):
            hand = ", ".join(x.code for x in grades if x.outcome in ("arrear", "excluded")) or "none"
            raise GradingError(f"'{manual}' can't be given by hand. Grades given by hand: {hand}.")
        return {"grade": g.code, "is_pass": False, "points": g.points, "outcome": g.outcome,
                "marks_obtained": total, "max_marks": max_marks or (rule.internal_max + rule.end_max),
                "internal_marks": internal, "end_marks": end}

    split = internal is not None or end is not None
    if split:
        if internal is None or end is None:
            raise GradingError("Enter both the internal and the end-semester marks (or neither, for absent).")
        if not 0 <= internal <= rule.internal_max:
            raise GradingError(f"Internal {internal:g} is out of range (0 to {rule.internal_max}).")
        if not 0 <= end <= rule.end_max:
            raise GradingError(f"End-semester {end:g} is out of range (0 to {rule.end_max}).")
        mx = rule.internal_max + rule.end_max
        total = internal + end
    else:
        mx = max_marks or (rule.internal_max + rule.end_max)
        if total is not None and not 0 <= total <= mx:
            raise GradingError(f"Marks {total:g} are out of range (0 to {mx}).")

    out = {"marks_obtained": total, "max_marks": mx, "internal_marks": internal, "end_marks": end}
    if total is None:                                   # absent
        return {**out, "grade": fail.code, "is_pass": False, "points": fail.points, "outcome": "fail"}
    pct_total = _pct(total, mx)
    ok = pct_total >= float(rule.min_total_pct)
    if split and rule.end_max:
        ok = ok and _pct(end, rule.end_max) >= float(rule.min_end_pct)
    if not ok:
        return {**out, "grade": fail.code, "is_pass": False, "points": fail.points, "outcome": "fail"}
    band = None
    for g in sorted((g for g in grades if g.outcome == "pass"), key=lambda g: g.min_mark, reverse=True):
        if pct_total >= float(g.min_mark):
            band = g
            break
    if band is None:            # cannot happen with a saved regulation (checked when it is saved)
        raise GradingError("The grade scale has no grade for these marks. Check the regulation.")
    return {**out, "grade": band.code, "is_pass": True, "points": band.points, "outcome": "pass"}


# ---------------------------------------------------------------- saving
def _snapshot(entry):
    return ResultAttempt(
        entry=entry, attempt=entry.attempt, exam_session=entry.exam_session,
        internal_marks=entry.internal_marks, end_marks=entry.end_marks,
        marks_obtained=entry.marks_obtained, max_marks=entry.max_marks,
        grade=entry.grade, grade_points=entry.grade_points, is_pass=entry.is_pass)


@transaction.atomic
def record_result(student, subject, semester, *, internal=None, end=None, total=None, max_marks=None,
                  manual=None, exam_session=""):
    """
    Save one subject's result. Returns (entry, action) with action one of
    'new', 'updated', 'new_attempt'. Raises GradingError.

    * same exam session (or none given) -> the marks are corrected in place;
      refused once the semester result is published (as the import already does)
    * a DIFFERENT session on a subject not yet passed -> a new attempt: the old
      marks move to the attempt history and the attempt number goes up
    * a different session on a subject already passed -> refused
    """
    exam_session = (exam_session or "").strip()[:30]
    rules = rules_for(student, subject)
    g = grade(rules, internal=internal, end=end, total=total, max_marks=max_marks, manual=manual)
    result, _ = SemesterResult.objects.get_or_create(student=student, semester=semester)
    entry = ResultEntry.objects.select_for_update().filter(result=result, subject=subject).first()

    fields = {"max_marks": g["max_marks"], "marks_obtained": g["marks_obtained"], "grade": g["grade"],
              "is_pass": g["is_pass"], "grade_points": g["points"], "outcome": g["outcome"],
              "internal_marks": g["internal_marks"], "end_marks": g["end_marks"]}
    if entry is None:
        entry = ResultEntry.objects.create(result=result, subject=subject, attempt=1,
                                           exam_session=exam_session, **fields)
        return entry, "new"

    new_session = bool(exam_session) and entry.exam_session and exam_session != entry.exam_session
    if not new_session:
        if result.is_published:
            raise GradingError("This result is already published. Unpublish it before changing marks, "
                               "or enter a re-exam with its new exam session.")
        if exam_session and not entry.exam_session:
            entry.exam_session = exam_session
        for k, v in fields.items():
            setattr(entry, k, v)
        entry.save()
        return entry, "updated"

    if entry.is_pass:
        raise GradingError("This subject is already passed. Only an arrear can be written again.")
    if ResultAttempt.objects.filter(entry=entry, exam_session=exam_session).exists():
        raise GradingError(f"An attempt in {exam_session} is already recorded for this subject.")
    _snapshot(entry).save()
    entry.attempt += 1
    entry.exam_session = exam_session
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.save()
    return entry, "new_attempt"


def keep_internal(student, subject, internal):
    """In a later attempt the regulation may keep the first attempt's internal mark."""
    if internal is not None:
        return internal
    rules = rules_for(student, subject)
    if rules is None or rules["regulation"].reattempt_internal != "keep":
        return None
    entry = (ResultEntry.objects.filter(result__student=student, subject=subject, internal_marks__isnull=False)
             .order_by("-attempt").first())
    return entry.internal_marks if entry else None


# ---------------------------------------------------------------- points, SGPA, CGPA
def entry_points(entry):
    """Grade points of one entry: the stored ones (regulation), else the old fixed table."""
    if entry.grade_points is not None:
        return float(entry.grade_points)
    return GRADE_POINTS.get((entry.grade or "").strip().upper())


def counts_for_credit(subject):
    cat = getattr(subject, "category", None)
    return not (cat is not None and not cat.carries_credit)


def semester_summary(student, published_only=True):
    """Everything the My credits and Results pages show, from one set of queries."""
    from core.academics.models import CreditRequirement, CourseCategory
    from core.academics.regulations import regulation_for_student
    reg = regulation_for_student(student)
    zero_arrears = bool(reg and reg.arrears_in_gpa == "zero")
    qs = SemesterResult.objects.filter(student=student)
    if published_only:
        qs = qs.filter(is_published=True)
    results = list(qs.prefetch_related("entries__subject__category", "entries__attempts").order_by("semester"))

    semesters, arrears = [], []
    all_points = all_credits = 0.0
    earned_total = 0.0
    earned_by_cat = {}
    problem = None
    ever_failed = False
    for res in results:
        rows, pts, cr, earned, sem_total, has_arrear = [], 0.0, 0.0, 0.0, 0.0, False
        for e in sorted(res.entries.all(), key=lambda x: (x.subject.code or "", x.subject.name)):
            s = e.subject
            credits = float(s.credits or 0)
            counted = counts_for_credit(s)
            points = entry_points(e)
            history = sorted(e.attempts.all(), key=lambda a: a.attempt)
            if history or (not e.is_pass and e.outcome != "excluded"):
                ever_failed = True
            in_gpa = False
            if counted and e.outcome != "excluded":
                if credits <= 0:
                    problem = problem or "no_credits"
                elif e.is_pass:
                    if points is None:
                        problem = problem or "bad_grade"
                    else:
                        in_gpa = True
                elif zero_arrears or (reg is None):      # the old behaviour counted a fail as 0 points
                    in_gpa = True
                    points = 0.0 if points is None else points
            if in_gpa:
                pts += points * credits
                cr += credits
            if counted:
                sem_total += credits
            if e.is_pass and counted:
                earned += credits
                cat = s.category_id
                earned_by_cat[cat] = earned_by_cat.get(cat, 0.0) + credits
            if not e.is_pass and e.outcome != "excluded":
                has_arrear = True
                arrears.append({
                    "subject_id": s.id, "code": s.code or "", "name": s.name, "semester": res.semester,
                    "credits": credits, "grade": e.grade, "attempt": e.attempt, "exam_session": e.exam_session,
                    "attempts": [{"attempt": a.attempt, "exam_session": a.exam_session, "grade": a.grade,
                                  "marks_obtained": a.marks_obtained, "end_marks": a.end_marks}
                                 for a in history] + [{"attempt": e.attempt, "exam_session": e.exam_session,
                                                       "grade": e.grade, "marks_obtained": e.marks_obtained,
                                                       "end_marks": e.end_marks}],
                })
            rows.append({
                "id": e.id, "subject_id": s.id, "code": s.code or "", "name": s.name, "credits": credits,
                "counts_for_credit": counted, "kind": s.kind,
                "internal_marks": e.internal_marks, "end_marks": e.end_marks,
                "marks_obtained": e.marks_obtained, "max_marks": e.max_marks,
                "grade": e.grade, "is_pass": e.is_pass, "outcome": e.outcome or ("pass" if e.is_pass else "fail"),
                "points": points if (e.is_pass or in_gpa) else None,
                "credit_points": round(points * credits, 2) if in_gpa else None,
                "in_gpa": in_gpa, "attempt": e.attempt, "exam_session": e.exam_session,
                "attempts": [{"attempt": a.attempt, "exam_session": a.exam_session, "grade": a.grade,
                              "internal_marks": a.internal_marks, "end_marks": a.end_marks,
                              "marks_obtained": a.marks_obtained} for a in history],
            })
        all_points += pts
        all_credits += cr
        earned_total += earned
        semesters.append({
            "semester": res.semester, "is_published": res.is_published,
            "sgpa": round(pts / cr, 2) if cr else None, "grade_points": round(pts, 2), "gpa_credits": cr,
            "credits_earned": earned, "credits_total": sem_total, "has_arrear": has_arrear, "entries": rows,
        })

    if results and not all_credits and not problem and any(x["entries"] for x in semesters):
        problem = "no_credits"
    cgpa = round(all_points / all_credits, 2) if all_credits and not problem else None
    required, categories = 0.0, []
    course = getattr(student, "course", None)
    if reg and course:
        req = {r.category_id: float(r.credits) for r in CreditRequirement.objects.filter(regulation=reg, course=course)}
        required = sum(req.values())
        for c in CourseCategory.objects.all():
            if not c.carries_credit or (not req.get(c.id) and not earned_by_cat.get(c.id)):
                continue
            categories.append({"code": c.code, "name": c.name, "required": req.get(c.id, 0.0),
                               "earned": earned_by_cat.get(c.id, 0.0)})
        if earned_by_cat.get(None):
            categories.append({"code": "—", "name": "No category set", "required": 0.0, "earned": earned_by_cat[None]})

    degree_class = None
    if reg and cgpa is not None:
        for dc in reg.classes.all():
            if cgpa >= float(dc.min_cgpa) and not (dc.first_attempt_only and ever_failed):
                degree_class = dc.name
                break

    return {
        "regulation": {"id": reg.id, "name": reg.name, "arrears_in_gpa": reg.arrears_in_gpa} if reg else None,
        "cgpa": cgpa, "cgpa_problem": problem,
        "credits_earned": earned_total, "credits_required": required,
        "categories": categories, "semesters": semesters, "arrears": arrears,
        "ever_failed": ever_failed, "degree_class": degree_class,
    }
