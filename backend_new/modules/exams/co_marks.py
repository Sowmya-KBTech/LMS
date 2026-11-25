"""
CO-PO PART B - IA question paper, marks by question, and CO attainment (rules + API).

  GET  /api/ia-papers/?teaching_assignment=&number=        the IA's question paper and the subject's COs
  PUT  /api/ia-papers/?teaching_assignment=&number=        {questions: [{id?, label, max_marks, outcome, bloom}]}
  GET  /api/ia-question-marks/?teaching_assignment=&number= every student's marks, question by question
  POST /api/ia-question-marks/                             {teaching_assignment, number, records: [{student, absent, marks: {qid: v}}]}
  GET  /api/co-attainment/<teaching_assignment>/           each CO's internal, end-semester, direct and final level
  PUT  /api/co-attainment/<teaching_assignment>/plan/      {outcome, text}   the action plan for a CO (blank text removes it)

Rules
  * the paper decides the IA's maximum (the sum of its questions, at most 100)
  * a question that already has marks can't be removed, and its maximum can't go
    below the highest mark given
  * marks by question are checked all together; one bad mark means nothing is saved
  * the student's IA total (IAMark) is saved with them, as the sum, so IA reports,
    the IA tab for students and results are unchanged
  * once an IA has a paper, totals can't be typed directly any more (the total
    screen and the Excel import refuse)
  * a locked (declared) IA can't change
  * CO attainment uses the rules on the Outcomes page (the subject's department,
    else the college); the course exit survey joins in Part C
"""
import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import COActionPlan, IAMark, IAQuestion, IAQuestionMark, InternalAssessment, ResultEntry
from .views import is_exam_admin

MAX_PAPER = Decimal(100)
BLOOMS = {k for k, _ in IAQuestion.BLOOM}


class Refuse(Exception):
    def __init__(self, message, code=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code


def _error(exc):
    return Response({"detail": str(exc)}, status=exc.code)


def _name(user):
    return (user.get_full_name() or "").strip() or user.username


def _num(d):
    if d is None:
        return None
    d = Decimal(d)
    return int(d) if d == d.to_integral() else float(d)


# ============================================================ who ===
def _ta(ta_id):
    TA = apps.get_model("courses", "TeachingAssignment")
    ta = TA.objects.select_related("subject", "teacher").filter(pk=ta_id if str(ta_id or "").isdigit() else 0).first()
    if ta is None:
        raise Refuse("Teaching assignment not found.", status.HTTP_404_NOT_FOUND)
    return ta


def can_enter(user, ta):
    """The subject's teacher for this class, or the exam admin (same as the IA marks screen)."""
    return ta.teacher_id == user.id or is_exam_admin(user)


def can_view(user, ta):
    if can_enter(user, ta):
        return True
    from core.users.acting_hod import hod_department_ids
    depts = hod_department_ids(user)
    return bool(depts) and (ta.subject.department_id in depts
                            or getattr(ta.teacher, "department_id", None) in depts)


def _number(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise Refuse("Choose IA 1, 2 or 3.")
    if n not in dict(InternalAssessment.IA_CHOICES):
        raise Refuse("Choose IA 1, 2 or 3.")
    return n


def subject_cos(ta):
    CO = apps.get_model("teachingplan", "CourseOutcome")
    return list(CO.objects.filter(subject_id=ta.subject_id).order_by("order", "id"))


def has_paper(slot):
    return slot is not None and slot.questions.exists()


# ============================================================ paper ===
def paper_view(ta, number, user):
    slot = InternalAssessment.objects.filter(teaching_assignment=ta, number=number).first()
    questions = list(slot.questions.select_related("outcome")) if slot else []
    marked = set(IAQuestionMark.objects.filter(question__in=questions).values_list("question_id", flat=True))
    totals = (IAMark.objects.filter(assessment=slot, marks_obtained__isnull=False).count() if slot else 0)
    return {
        "number": number, "locked": bool(slot and slot.is_locked),
        "max_marks": slot.max_marks if slot else None,
        "questions": [{"id": q.id, "label": q.label, "max_marks": _num(q.max_marks), "outcome": q.outcome_id,
                       "outcome_code": q.outcome.code if q.outcome_id else "", "bloom": q.bloom,
                       "has_marks": q.id in marked} for q in questions],
        "cos": [{"id": c.id, "code": c.code, "text": c.text} for c in subject_cos(ta)],
        "totals_entered": totals,
        "can_edit": can_enter(user, ta) and not (slot and slot.is_locked),
    }


@transaction.atomic
def save_paper(ta, number, rows):
    if not isinstance(rows, list):
        raise Refuse("Send the list of questions.")
    slot = InternalAssessment.objects.select_for_update().filter(teaching_assignment=ta, number=number).first()
    if slot and slot.is_locked:
        raise Refuse("This IA is locked and can no longer be edited.")
    cos = {c.id for c in subject_cos(ta)}
    existing = {q.id: q for q in (slot.questions.all() if slot else [])}
    top = defaultdict(lambda: Decimal(0))          # highest mark given per question
    for qid, m in IAQuestionMark.objects.filter(question_id__in=list(existing)).values_list("question_id", "marks"):
        top[qid] = max(top[qid], m)

    clean, labels, keep = [], set(), set()
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            raise Refuse("Each question needs a label and marks.")
        label = str(r.get("label") or "").strip()
        if not label or len(label) > 10:
            raise Refuse(f"Question {i}: give it a short label such as Q{i} (at most 10 characters).")
        if label.lower() in labels:
            raise Refuse(f"{label} is used twice.")
        labels.add(label.lower())
        try:
            mx = Decimal(str(r.get("max_marks")))
        except (InvalidOperation, ValueError):
            raise Refuse(f"{label}: marks must be a number.")
        if mx <= 0 or mx * 2 != (mx * 2).to_integral():
            raise Refuse(f"{label}: marks must be above 0, in steps of 0.5.")
        outcome = r.get("outcome")
        outcome = int(outcome) if str(outcome or "").isdigit() else None
        if outcome is not None and outcome not in cos:
            raise Refuse(f"{label}: that CO is not one of this subject's.")
        bloom = r.get("bloom") or ""
        if bloom not in BLOOMS:
            raise Refuse(f"{label}: unknown level.")
        qid = r.get("id")
        qid = int(qid) if str(qid or "").isdigit() and int(qid) in existing else None
        if qid and mx < top[qid]:
            raise Refuse(f"{label}: a student already has {_num(top[qid])}; the maximum can't be lower.")
        if qid:
            keep.add(qid)
        clean.append((qid, label, mx, outcome, bloom, i))

    total = sum((c[2] for c in clean), Decimal(0))
    if total > MAX_PAPER:
        raise Refuse(f"The questions add up to {_num(total)}; an IA can be at most {_num(MAX_PAPER)}.")
    gone = [q for qid, q in existing.items() if qid not in keep]
    with_marks = [q.label for q in gone if q.id in top]
    if with_marks:
        raise Refuse(f"{', '.join(with_marks)} already have marks and can't be removed.")
    if not clean:
        IAQuestion.objects.filter(id__in=[q.id for q in gone]).delete()
        return slot
    if slot is None:
        slot = InternalAssessment.objects.create(teaching_assignment=ta, number=number, max_marks=int(total))
    IAQuestion.objects.filter(id__in=[q.id for q in gone]).delete()
    # labels must stay unique while they change: park the kept ones first
    for q in IAQuestion.objects.filter(id__in=list(keep)):
        q.label = f"~{q.id}"
        q.save(update_fields=["label"])
    for qid, label, mx, outcome, bloom, order in clean:
        if qid:
            IAQuestion.objects.filter(pk=qid).update(label=label, max_marks=mx, outcome_id=outcome, bloom=bloom,
                                                     order=order)
        else:
            IAQuestion.objects.create(assessment=slot, label=label, max_marks=mx, outcome_id=outcome, bloom=bloom,
                                      order=order)
    # the IA's maximum is the paper's total (a whole number keeps IA reports simple)
    whole = int(total) if total == total.to_integral() else int(total) + 1
    if slot.max_marks != whole:
        slot.max_marks = whole
        slot.save(update_fields=["max_marks"])
    return slot


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def ia_paper(request):
    try:
        ta = _ta(request.query_params.get("teaching_assignment"))
        number = _number(request.query_params.get("number"))
        if not can_view(request.user, ta):
            raise Refuse("You can't see this subject's IA.", status.HTTP_403_FORBIDDEN)
        if request.method == "PUT":
            if not can_enter(request.user, ta):
                raise Refuse("Only this subject's teacher or the exam admin sets the question paper.",
                             status.HTTP_403_FORBIDDEN)
            save_paper(ta, number, request.data.get("questions"))
    except Refuse as exc:
        return _error(exc)
    return Response(paper_view(ta, number, request.user))


# ============================================================ marks by question ===
def _enrolled(ta):
    Enrollment = apps.get_model("courses", "Enrollment")
    return list(Enrollment.objects.filter(teaching_assignment=ta).select_related("student")
                .order_by("student__roll_number", "student__username"))


def marks_view(ta, number, user):
    slot = InternalAssessment.objects.filter(teaching_assignment=ta, number=number).first()
    questions = list(slot.questions.all()) if slot else []
    qm = defaultdict(dict)
    for sid, qid, m in IAQuestionMark.objects.filter(question__in=questions).values_list("student_id", "question_id",
                                                                                          "marks"):
        qm[sid][str(qid)] = _num(m)
    totals = {m.student_id: m for m in IAMark.objects.filter(assessment=slot)} if slot else {}
    rows = []
    for e in _enrolled(ta):
        st, t = e.student, totals.get(e.student_id)
        rows.append({"student": st.id, "name": _name(st), "roll_number": st.roll_number or "",
                     "absent": bool(t and t.is_absent), "marks": qm.get(st.id, {}),
                     "total": t.marks_obtained if t else None})
    return {"number": number, "locked": bool(slot and slot.is_locked), "max_marks": slot.max_marks if slot else None,
            "questions": [{"id": q.id, "label": q.label, "max_marks": _num(q.max_marks), "outcome": q.outcome_id}
                          for q in questions],
            "rows": rows, "can_edit": can_enter(user, ta) and not (slot and slot.is_locked)}


@transaction.atomic
def save_question_marks(ta, number, records):
    slot = InternalAssessment.objects.select_for_update().filter(teaching_assignment=ta, number=number).first()
    if not has_paper(slot):
        raise Refuse("Set the question paper first.")
    if slot.is_locked:
        raise Refuse("This IA is locked and can no longer be edited.")
    if not isinstance(records, list):
        raise Refuse("records must be a list.")
    questions = {q.id: q for q in slot.questions.all()}
    enrolled = {e.student_id: e.student for e in _enrolled(ta)}
    errors, clean = [], []
    for r in records:
        sid = r.get("student") if isinstance(r, dict) else None
        if not str(sid or "").isdigit() or int(sid) not in enrolled:
            errors.append(f"Student {sid} is not enrolled in this subject.")
            continue
        st = enrolled[int(sid)]
        absent = r.get("absent") in (True, "true", 1, "1")
        given = {}
        for key, raw in (r.get("marks") or {}).items():
            if not str(key).isdigit() or int(key) not in questions:
                errors.append(f"{_name(st)}: unknown question.")
                continue
            if absent or raw in (None, ""):
                continue
            q = questions[int(key)]
            try:
                v = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                errors.append(f"{_name(st)} {q.label}: '{raw}' is not a number.")
                continue
            if v < 0 or v > q.max_marks or v * 2 != (v * 2).to_integral():
                errors.append(f"{_name(st)} {q.label}: {raw} must be 0 to {_num(q.max_marks)}, in steps of 0.5.")
                continue
            given[q.id] = v
        clean.append((st.id, absent, given))
    if errors:
        raise Refuse("Marks not saved. Please correct: " + " ".join(errors))

    for sid, absent, given in clean:
        IAQuestionMark.objects.filter(question__in=list(questions), student_id=sid).exclude(
            question_id__in=list(given)).delete()
        for qid, v in given.items():
            IAQuestionMark.objects.update_or_create(question_id=qid, student_id=sid, defaults={"marks": v})
        total = float(sum(given.values())) if given else None
        IAMark.objects.update_or_create(assessment=slot, student_id=sid,
                                        defaults={"marks_obtained": None if absent else total, "is_absent": absent})
    return slot


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ia_question_marks(request):
    data = request.query_params if request.method == "GET" else request.data
    try:
        ta = _ta(data.get("teaching_assignment"))
        number = _number(data.get("number"))
        if request.method == "GET":
            if not can_view(request.user, ta):
                raise Refuse("You can't see this subject's IA.", status.HTTP_403_FORBIDDEN)
        else:
            if not can_enter(request.user, ta):
                raise Refuse("Not your teaching assignment.", status.HTTP_403_FORBIDDEN)
            save_question_marks(ta, number, request.data.get("records"))
    except Refuse as exc:
        return _error(exc)
    return Response(marks_view(ta, number, request.user))


# ============================================================ CO attainment ===
def level_of(pct, rule):
    if pct is None:
        return None
    if pct >= rule.level3_pct:
        return 3
    if pct >= rule.level2_pct:
        return 2
    if pct >= rule.level1_pct:
        return 1
    return 0


def rule_for_ta(ta):
    from modules.teachingplan.outcomes import rule_for
    dept = ta.subject.department_id or getattr(ta.teacher, "department_id", None)
    return rule_for(dept)[0]


def internal_marks(ta, cos, rule):
    """
    {co_id: {student_id: [got, max]}} from the IA papers and the online tests,
    plus the list of sources with how many marks each gave to each CO.
    An IA counts for a student once they have marks (or are marked absent) in it.
    """
    co_ids = {c.id for c in cos}
    per = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    sources = []
    enrolled = {e.student_id for e in _enrolled(ta)}
    if rule.use_ia:
        for slot in InternalAssessment.objects.filter(teaching_assignment=ta).prefetch_related("questions"):
            qs = [q for q in slot.questions.all() if q.outcome_id in co_ids]
            if not qs:
                continue
            got = defaultdict(float)
            for sid, qid, m in IAQuestionMark.objects.filter(question__in=qs).values_list("student_id", "question_id",
                                                                                          "marks"):
                got[(sid, qid)] = float(m)
            took = set(IAMark.objects.filter(assessment=slot).filter(
                is_absent=True).values_list("student_id", flat=True))
            took |= {sid for sid, _ in got}
            took &= enrolled
            if not took:
                continue
            by_co = defaultdict(float)
            for q in qs:
                by_co[q.outcome_id] += float(q.max_marks)
                for sid in took:
                    cell = per[q.outcome_id][sid]
                    cell[0] += got.get((sid, q.id), 0.0)
                    cell[1] += float(q.max_marks)
            sources.append({"kind": "ia", "name": f"IA {slot.number}", "by_co": {str(k): v for k, v in by_co.items()}})
    if rule.use_online_tests:
        Quiz = apps.get_model("learning", "Quiz")
        Attempt = apps.get_model("learning", "QuizAttempt")
        Bank = apps.get_model("learning", "BankQuestion")
        for quiz in Quiz.objects.filter(teaching_assignment=ta, is_published=True):
            atts = list(Attempt.objects.filter(quiz=quiz, status="submitted", written_pending=False,
                                               student_id__in=enrolled))
            if not atts:
                continue
            bank = {b.id: b.outcome_id for b in Bank.objects.filter(
                id__in={p["q"] for a in atts for p in (a.paper or [])})}
            by_co = defaultdict(float)
            for a in atts:
                for p in a.paper or []:
                    co = bank.get(p["q"])
                    got = (a.awarded or {}).get(str(p["q"]))
                    if co not in co_ids or got is None:
                        continue
                    cell = per[co][a.student_id]
                    cell[0] += max(float(got), 0.0)
                    cell[1] += float(p["m"])
            for p in atts[0].paper or []:
                co = bank.get(p["q"])
                if co in co_ids:
                    by_co[co] += float(p["m"])
            if by_co:
                sources.append({"kind": "online", "name": f"Online test: {quiz.title}",
                                "by_co": {str(k): v for k, v in by_co.items()}})
    return per, sources


def end_semester(ta, rule):
    """% of the class whose end-semester mark reached the target (latest attempt each). None when not published."""
    latest = {}
    for e in (ResultEntry.objects.filter(subject_id=ta.subject_id, result__is_published=True,
                                         result__student_id__in=[x.student_id for x in _enrolled(ta)],
                                         marks_obtained__isnull=False, max_marks__gt=0)
              .exclude(outcome="excluded").select_related("result").order_by("id")):
        latest[e.result.student_id] = e
    if not latest:
        return None
    reached = sum(1 for e in latest.values() if e.marks_obtained * 100 / e.max_marks >= rule.student_target_pct)
    return {"students": len(latest), "reached": reached, "pct": round(reached * 100 / len(latest), 1)}


def attainment(ta):
    rule = rule_for_ta(ta)
    cos = subject_cos(ta)
    per, sources = internal_marks(ta, cos, rule)
    end = end_semester(ta, rule)
    end_level = level_of(end["pct"], rule) if end else None
    share = rule.internal_share / 100
    plans = {p.outcome_id: p for p in COActionPlan.objects.filter(teaching_assignment=ta)}
    survey = exit_survey_result(ta, rule)                       # CO-PO PART C
    dshare = rule.direct_share / 100
    rows = []
    for c in cos:
        students = per.get(c.id, {})
        counted = [(g, m) for g, m in students.values() if m > 0]
        internal = None
        if counted:
            reached = sum(1 for g, m in counted if g * 100 / m >= rule.student_target_pct)
            pct = round(reached * 100 / len(counted), 1)
            internal = {"students": len(counted), "reached": reached, "pct": pct, "level": level_of(pct, rule)}
        if internal and end_level is not None:
            direct = round(internal["level"] * share + end_level * (1 - share), 2)
        elif internal:
            direct = float(internal["level"])
        elif end_level is not None:
            direct = float(end_level)
        else:
            direct = None
        level = survey["levels"].get(c.id) if survey and survey["counted"] else None
        if direct is not None and level is not None:           # CO-PO PART C: + the course exit survey
            final = round(direct * dshare + level * (1 - dshare), 2)
        else:
            final = direct
        plan = plans.get(c.id)
        rows.append({
            "id": c.id, "code": c.code, "text": c.text, "internal": internal,
            "end": ({**end, "level": end_level} if end else None), "direct": direct,
            "survey": (survey["levels"].get(c.id) if survey else None),
            "final": final, "attained": None if final is None else final >= float(rule.co_target),
            "plan": plan.text if plan else "", "plan_updated_at": plan.updated_at if plan else None,
        })
    return {
        "rule": {"student_target_pct": rule.student_target_pct, "level3_pct": rule.level3_pct,
                 "level2_pct": rule.level2_pct, "level1_pct": rule.level1_pct,
                 "internal_share": rule.internal_share, "direct_share": rule.direct_share,
                 "co_target": float(rule.co_target), "survey_min_pct": rule.survey_min_pct},
        "cos": rows, "sources": sources, "end_published": end is not None,
        "survey": ({k: v for k, v in survey.items() if k != "levels"} if survey else None),
        "students": len(_enrolled(ta)),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def co_attainment(request, ta_id):
    try:
        ta = _ta(ta_id)
        if not can_view(request.user, ta):
            raise Refuse("You can't see this subject's attainment.", status.HTTP_403_FORBIDDEN)
    except Refuse as exc:
        return _error(exc)
    data = attainment(ta)
    data["subject"] = {"id": ta.subject_id, "code": ta.subject.code or "", "name": ta.subject.name}
    data["can_edit"] = can_enter(request.user, ta)
    return Response(data)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def co_action_plan(request, ta_id):
    try:
        ta = _ta(ta_id)
        if not can_enter(request.user, ta):
            raise Refuse("Only this subject's teacher writes the action plan.", status.HTTP_403_FORBIDDEN)
        co = request.data.get("outcome")
        if not str(co or "").isdigit() or int(co) not in {c.id for c in subject_cos(ta)}:
            raise Refuse("Choose one of this subject's COs.")
    except Refuse as exc:
        return _error(exc)
    text = (request.data.get("text") or "").strip()
    if text:
        COActionPlan.objects.update_or_create(teaching_assignment=ta, outcome_id=int(co),
                                              defaults={"text": text[:2000], "updated_by": request.user})
    else:
        COActionPlan.objects.filter(teaching_assignment=ta, outcome_id=int(co)).delete()
    return Response({"outcome": int(co), "text": text[:2000]})


# ======================================================================
# CO-PO PART C - course exit survey, PO / PSO attainment, NBA Excel
#   POST /api/co-attainment/<ta>/survey/          make and open the course exit survey (once per class)
#   GET  /api/po-attainment/?course=&batch=       PO / PSO attainment of a course (and batch)
#   GET  /api/po-attainment/export/?course=&batch=  the NBA tables as an Excel file
# ======================================================================
EXIT_TEMPLATE = "co_exit"
EXIT_DAYS = 14


def exit_survey(ta):
    Survey = apps.get_model("surveys", "Survey")
    return Survey.objects.filter(teaching_assignment=ta, template=EXIT_TEMPLATE).first()


def exit_survey_result(ta, rule):
    """
    The class's course exit survey: per CO the average rating (1-5) turned into a
    level out of 3. It counts only when enough of the class answered
    (rule.survey_min_pct). None when there is no survey.
    """
    s = exit_survey(ta)
    if s is None:
        return None
    Answer = apps.get_model("surveys", "Answer")
    from modules.surveys.views import eligible_users
    students = eligible_users(s).count()
    responses = s.participations.count()
    rate = round(responses * 100 / students, 1) if students else 0.0
    levels = {}
    rows = (Answer.objects.filter(question__survey=s, question__outcome__isnull=False, rating__isnull=False)
            .values_list("question__outcome_id", "rating"))
    sums = defaultdict(list)
    for co, r in rows:
        sums[co].append(r)
    for co, vals in sums.items():
        levels[co] = round(sum(vals) / len(vals) * 3 / 5, 2)
    return {"id": s.id, "status": s.status, "end_date": s.end_date, "responses": responses, "students": students,
            "rate": rate, "counted": bool(responses) and rate >= rule.survey_min_pct, "levels": levels}


@transaction.atomic
def open_exit_survey(ta, by):
    Survey = apps.get_model("surveys", "Survey")
    Question = apps.get_model("surveys", "Question")
    if exit_survey(ta) is not None:
        raise Refuse("This class already has a course exit survey.")
    cos = subject_cos(ta)
    if not cos:
        raise Refuse("Add the subject's course outcomes first.")
    from django.utils import timezone
    from core.notifications.services import notify
    from modules.surveys.views import eligible_users
    today = timezone.localdate()
    name = f"{ta.subject.code} {ta.subject.name}".strip() if ta.subject.code else ta.subject.name
    s = Survey.objects.create(
        title=f"Course exit survey: {name}"[:200],
        description="How well can you now do each of these? 1 = not at all, 5 = very well. Your answers are anonymous.",
        audience="students", department_id=ta.subject.department_id, teaching_assignment=ta, anonymous=True,
        status="open", start_date=today, end_date=today + datetime.timedelta(days=EXIT_DAYS),
        template=EXIT_TEMPLATE, created_by=by, published_at=timezone.now())
    Question.objects.bulk_create(
        [Question(survey=s, order=i, kind="rating", text=f"{c.code}: {c.text}"[:500], outcome=c)
         for i, c in enumerate(cos, start=1)]
        + [Question(survey=s, order=len(cos) + 1, kind="text", required=False,
                    text="Anything about this subject you want to tell your teacher?")])
    people = list(eligible_users(s))
    notify(people, s.title, f"Please answer by {s.end_date:%d-%m-%Y}. It takes a minute and is anonymous.",
           "announcement", link=f"/surveys/{s.id}")
    return s


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def co_exit_survey(request, ta_id):
    try:
        ta = _ta(ta_id)
        if not can_enter(request.user, ta):
            raise Refuse("Only this subject's teacher sends the course exit survey.", status.HTTP_403_FORBIDDEN)
        s = open_exit_survey(ta, request.user)
    except Refuse as exc:
        return _error(exc)
    return Response({"id": s.id, "status": s.status, "end_date": s.end_date}, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------ PO attainment
def _course_tas(course_id, batch):
    TA = apps.get_model("courses", "TeachingAssignment")
    qs = TA.objects.filter(course_id=course_id).select_related("subject", "teacher", "year")
    if batch:
        qs = qs.filter(enrollments__student__batch_year=batch).distinct()
    return list(qs.order_by("subject__semester", "subject__code", "id"))


def po_attainment(course_id, batch=None):
    """
    For each subject: each CO's final level (averaged over the subject's classes),
    then for each PO the CO levels weighted by their mapping strength. The
    programme's PO value is the average over the subjects mapped to it.
    """
    from modules.teachingplan.models import COPOMap
    from modules.teachingplan.outcomes import outcomes_for_course, rule_for
    pos, psos = outcomes_for_course(course_id)
    columns = pos + psos
    by_subject = defaultdict(list)
    for ta in _course_tas(course_id, batch):
        by_subject[ta.subject_id].append(ta)
    links = defaultdict(list)                          # subject -> [(co, po, strength)]
    for co_id, po_id, strength, sub_id in COPOMap.objects.filter(
            outcome__subject_id__in=list(by_subject), program_outcome__in=columns
    ).values_list("outcome_id", "program_outcome_id", "strength", "outcome__subject_id"):
        links[sub_id].append((co_id, po_id, strength))

    subjects, left_out = [], []
    below = planned = total_cos = 0
    for sub_id, tas in by_subject.items():
        subject = tas[0].subject
        finals = defaultdict(list)
        plans = set()
        for ta in tas:
            data = attainment(ta)
            for c in data["cos"]:
                if c["final"] is not None:
                    finals[c["id"]].append(c["final"])
                if c["plan"]:
                    plans.add(c["id"])
        co_final = {co: round(sum(v) / len(v), 2) for co, v in finals.items()}
        label = f"{subject.code} {subject.name}".strip() if subject.code else subject.name
        if not links.get(sub_id):
            left_out.append({"subject": label, "why": "No CO–PO mapping"})
            continue
        if not co_final:
            left_out.append({"subject": label, "why": "No marks by CO yet"})
            continue
        target = float(rule_for(subject.department_id)[0].co_target)
        for co, v in co_final.items():
            total_cos += 1
            if v < target:
                below += 1
                planned += co in plans
        values = {}
        for po in columns:
            pairs = [(co_final[co], st) for co, p, st in links[sub_id] if p == po.id and co in co_final]
            weight = sum(st for _, st in pairs)
            values[po.id] = round(sum(v * st for v, st in pairs) / weight, 2) if weight else None
        met = sum(1 for v in co_final.values() if v >= target)
        subjects.append({"id": sub_id, "subject": label, "semester": subject.semester, "values": values,
                         "cos_met": met, "cos_total": len(co_final), "co_final": co_final})

    from modules.teachingplan.outcomes import college_rule
    po_target = float(college_rule().po_target)
    overall = []
    for po in columns:
        vals = [s["values"][po.id] for s in subjects if s["values"].get(po.id) is not None]
        v = round(sum(vals) / len(vals), 2) if vals else None
        overall.append({"id": po.id, "code": po.code, "text": po.text, "kind": po.kind, "value": v,
                        "subjects": len(vals), "attained": None if v is None else v >= po_target})
    return {"columns": [{"id": p.id, "code": p.code, "text": p.text, "kind": p.kind} for p in columns],
            "overall": overall, "subjects": subjects, "left_out": left_out, "po_target": po_target,
            "cos_below": below, "cos_below_planned": planned, "cos_total": total_cos}


def _po_args(request):
    if not (is_exam_admin(request.user) or getattr(request.user, "role", "") in ("teacher", "admin")):
        raise Refuse("Only staff.", status.HTTP_403_FORBIDDEN)
    course = request.query_params.get("course")
    if not str(course or "").isdigit():
        raise Refuse("Choose a course.")
    batch = request.query_params.get("batch")
    return int(course), (int(batch) if str(batch or "").isdigit() else None)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def po_attainment_view(request):
    try:
        course, batch = _po_args(request)
    except Refuse as exc:
        return _error(exc)
    data = po_attainment(course, batch)
    for s in data["subjects"]:
        s.pop("co_final", None)
        s["values"] = {str(k): v for k, v in s["values"].items()}
    User = apps.get_model("users", "User")
    data["batches"] = sorted({b for b in User.objects.filter(role="student", course_id=course)
                             .values_list("batch_year", flat=True) if b}, reverse=True)
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def po_attainment_export(request):
    """The NBA tables: CO attainment, CO-PO mapping and PO attainment, one sheet each."""
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from modules.teachingplan.models import COPOMap
    try:
        course, batch = _po_args(request)
    except Refuse as exc:
        return _error(exc)
    data = po_attainment(course, batch)
    cols = data["columns"]
    wb = Workbook()
    bold = Font(bold=True)

    ws = wb.active
    ws.title = "CO attainment"
    ws.append(["Subject", "Class", "Teacher", "CO", "Course outcome", "Internal level", "Internal %",
               "End-sem level", "End-sem %", "Direct", "Survey", "Final", "Attained", "Action plan"])
    for ta in _course_tas(course, batch):
        d = attainment(ta)
        for c in d["cos"]:
            ws.append([f"{ta.subject.code} {ta.subject.name}".strip(), f"{ta.course.name} Year {ta.year.year_number}",
                       _name(ta.teacher), c["code"], c["text"],
                       c["internal"]["level"] if c["internal"] else None, c["internal"]["pct"] if c["internal"] else None,
                       c["end"]["level"] if c["end"] else None, c["end"]["pct"] if c["end"] else None,
                       c["direct"], c["survey"], c["final"],
                       None if c["attained"] is None else ("Yes" if c["attained"] else "No"), c["plan"]])

    ws = wb.create_sheet("CO-PO mapping")
    ws.append(["Subject", "CO"] + [c["code"] for c in cols])
    CO = apps.get_model("teachingplan", "CourseOutcome")
    cells = {(co, po): st for co, po, st in COPOMap.objects.filter(
        outcome__subject__year__course_id=course).values_list("outcome_id", "program_outcome_id", "strength")}
    for co in CO.objects.filter(subject__year__course_id=course).select_related("subject").order_by(
            "subject__semester", "subject__code", "order"):
        ws.append([f"{co.subject.code} {co.subject.name}".strip(), co.code]
                  + [cells.get((co.id, c["id"])) for c in cols])

    ws = wb.create_sheet("PO attainment")
    ws.append(["Subject", "Semester"] + [c["code"] for c in cols] + ["COs met"])
    for s in data["subjects"]:
        ws.append([s["subject"], s["semester"]] + [s["values"].get(c["id"]) for c in cols]
                  + [f"{s['cos_met']} / {s['cos_total']}"])
    ws.append(["Programme", ""] + [o["value"] for o in data["overall"]] + [""])
    ws.append([f"Target {data['po_target']}", ""] + [None if o["attained"] is None else ("Yes" if o["attained"] else "No")
                                                     for o in data["overall"]] + [""])
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = bold
    resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = 'attachment; filename="co-po-attainment.xlsx"'
    wb.save(resp)
    return resp
