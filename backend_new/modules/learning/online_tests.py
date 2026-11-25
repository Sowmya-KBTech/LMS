"""WAVE 3 PART 3 - online tests: the quiz, upgraded. Logic and APIs in one file.

A subject has a QUESTION BANK (BankQuestion), shared by all its teachers.
A test (the Quiz model) has SECTIONS: questions picked at random from the bank
by rules, or questions the teacher chose. Each student gets their own PAPER
when they start (QuizAttempt.paper), shuffled if the test says so. Answers
autosave; the clock runs from the start; when time is up the test is
submitted with what was saved. MCQ / true-false are marked straight away;
short and long answers wait for the teacher (marking: Part 3b).

Teacher (and admin):
  GET/POST       online-tests/bank/?subject=        list (filters) / add one or many
  PATCH/DELETE   online-tests/bank/<id>/            delete archives a question already used
  GET            online-tests/bank/meta/?subject=   units, course outcomes, counts
  POST           online-tests/bank/generate/        AI draft from notes (not saved)
  GET/POST       online-tests/tests/?teaching_assignment=
  GET/PUT/DELETE online-tests/tests/<id>/
  POST           online-tests/tests/check/          pool sizes + marks by CO / Bloom for a draft paper
  POST           online-tests/tests/<id>/publish/   and /unpublish/
  GET            online-tests/tests/<id>/attempts/  who started / submitted, scores so far
  GET            online-tests/tests/<id>/attempts/<aid>/   one student's answers (Part 3b)
  GET            online-tests/tests/<id>/marking/          written questions + how many are marked
  GET/POST       online-tests/tests/<id>/marking/<qid>/    every answer to one question / mark one
  GET            online-tests/tests/<id>/results/          results, by CO, hardest questions
  POST           online-tests/tests/<id>/release/          and /withdraw/ - students see results
Student:
  GET            online-tests/tests/?teaching_assignment=
  POST           online-tests/tests/<id>/start/
  GET            online-tests/attempts/<id>/
  POST           online-tests/attempts/<id>/save/   {answers, flagged, left}
  POST           online-tests/attempts/<id>/submit/
  GET            online-tests/attempts/<id>/review/ (when the teacher allows it)
"""
import datetime
import random
from collections import Counter, defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.academics.helpers import get_enrolled_ta_ids
from core.academics.models import Subject, TeachingAssignment
from core.notifications.models import Notification

from .models import BankQuestion, Quiz, QuizAttempt, QuizSection

KINDS = ("mcq", "multi", "tf", "short", "long")
OBJECTIVE = ("mcq", "multi", "tf")
WRITTEN = ("short", "long")
DIFFICULTIES = ("easy", "medium", "hard")
BLOOMS = ("remember", "understand", "apply", "analyse", "evaluate", "create")
GRACE = datetime.timedelta(seconds=60)          # a save that left just before the bell still counts
MAX_OPTIONS = 8
KIND_LABEL = dict(BankQuestion.KIND_CHOICES)


class Refuse(Exception):
    """A plain-language 400 (or another status)."""
    def __init__(self, msg, status=400, extra=None):
        super().__init__(msg)
        self.msg, self.status, self.extra = msg, status, extra or {}


def _resp(e):
    return Response({"detail": e.msg, **e.extra}, status=e.status)


def api(methods):
    """api_view + IsAuthenticated + Refuse -> response."""
    def wrap(fn):
        def inner(request, *a, **kw):
            try:
                return fn(request, *a, **kw)
            except Refuse as e:
                return _resp(e)
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return api_view(methods)(permission_classes([IsAuthenticated])(inner))
    return wrap


# ================================================================ who may do what
def _is_admin(user):
    return getattr(user, "role", None) == "admin" or getattr(user, "is_superuser", False)


def teaches_subject(user, subject_id):
    return _is_admin(user) or TeachingAssignment.objects.filter(teacher=user, subject_id=subject_id).exists()


def _subject_for(user, subject_id):
    s = Subject.objects.filter(pk=subject_id).first() if subject_id else None
    if s is None:
        raise Refuse("Pick a subject.")
    if not teaches_subject(user, s.id):
        raise Refuse("Only the subject's teachers can use its question bank.", 403)
    return s


def _ta_for_teacher(user, ta_id):
    ta = TeachingAssignment.objects.select_related("subject").filter(pk=ta_id).first() if ta_id else None
    if ta is None:
        raise Refuse("Pick a class and subject.")
    if not (_is_admin(user) or ta.teacher_id == user.id):
        raise Refuse("You can only manage tests of your own classes.", 403)
    return ta


def _test_for_teacher(user, pk):
    q = Quiz.objects.select_related("teaching_assignment__subject").filter(pk=pk).first()
    if q is None:
        raise Refuse("Test not found.", 404)
    if not (_is_admin(user) or q.teaching_assignment.teacher_id == user.id):
        raise Refuse("You can only manage tests of your own classes.", 403)
    return q


# ================================================================ the bank
def _num(v, label, lo=None, hi=None, default=None, cast=int):
    if v in (None, ""):
        if default is None:
            raise Refuse(f"{label} is needed.")
        return default
    try:
        n = cast(v)
    except (TypeError, ValueError, ArithmeticError):
        raise Refuse(f"{label} must be a number.")
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise Refuse(f"{label} must be between {lo} and {hi}.")
    return n


def clean_question(data, subject, existing=None):
    """Check one question. Returns a dict of model fields. Raises Refuse."""
    d = {}
    kind = data.get("kind", existing.kind if existing else "mcq")
    if kind not in KINDS:
        raise Refuse("Choose a question type.")
    d["kind"] = kind
    text = str(data.get("text", existing.text if existing else "") or "").strip()
    if not text:
        raise Refuse("The question has no text.")
    d["text"] = text

    if kind in ("mcq", "multi"):
        opts = data.get("options", existing.options if existing else [])
        if not isinstance(opts, list):
            raise Refuse("Options must be a list.")
        opts = [str(o or "").strip() for o in opts]
        if len(opts) < 2 or len(opts) > MAX_OPTIONS or any(not o for o in opts):
            raise Refuse(f"Give 2 to {MAX_OPTIONS} options, none of them empty.")
        if len(set(o.lower() for o in opts)) != len(opts):
            raise Refuse("Two options are the same.")
        ans = data.get("answer", existing.answer if existing else None)
        if isinstance(ans, int):
            ans = [ans]
        if not isinstance(ans, list) or not ans:
            raise Refuse("Tick the right answer." if kind == "mcq" else "Tick the right answers.")
        try:
            ans = sorted({int(a) for a in ans})
        except (TypeError, ValueError):
            raise Refuse("The answer must point at the options.")
        if any(a < 0 or a >= len(opts) for a in ans):
            raise Refuse("The answer must point at one of the options.")
        if kind == "mcq" and len(ans) != 1:
            raise Refuse("An MCQ with one answer needs exactly one right option.")
        d["options"], d["answer"] = opts, ans
    elif kind == "tf":
        ans = data.get("answer", existing.answer if existing else None)
        if isinstance(ans, str):
            ans = {"true": True, "false": False}.get(ans.strip().lower())
        if not isinstance(ans, bool):
            raise Refuse("Say whether the statement is true or false.")
        d["options"], d["answer"] = ["True", "False"], ans
    else:
        d["options"], d["answer"] = [], None
        d["model_answer"] = str(data.get("model_answer", existing.model_answer if existing else "") or "").strip()

    d["marks"] = _num(data.get("marks", existing.marks if existing else 1), "Marks", 1, 100)
    d["negative_marks"] = _num(data.get("negative_marks", existing.negative_marks if existing else 0),
                               "Negative marks", 0, 100, default=Decimal("0"), cast=Decimal)
    if kind in WRITTEN:
        d["negative_marks"] = Decimal("0")
    unit = data.get("unit", existing.unit if existing else None)
    d["unit"] = None if unit in (None, "") else _num(unit, "Unit", 1, 20)
    oc = data.get("outcome", existing.outcome_id if existing else None)
    if oc in (None, ""):
        d["outcome_id"] = None
    else:
        from modules.teachingplan.models import CourseOutcome
        if not CourseOutcome.objects.filter(pk=oc, subject=subject).exists():
            raise Refuse("That course outcome isn't one of this subject's.")
        d["outcome_id"] = int(oc)
    bloom = data.get("bloom", existing.bloom if existing else "") or ""
    if bloom and bloom not in BLOOMS:
        raise Refuse("Choose a Bloom level.")
    d["bloom"] = bloom
    diff = data.get("difficulty", existing.difficulty if existing else "medium") or "medium"
    if diff not in DIFFICULTIES:
        raise Refuse("Difficulty is easy, medium or hard.")
    d["difficulty"] = diff
    d["explanation"] = str(data.get("explanation", existing.explanation if existing else "") or "").strip()
    return d


def question_payload(b, with_answer=True, usage=None):
    out = {"id": b.id, "kind": b.kind, "kind_label": KIND_LABEL[b.kind], "text": b.text, "options": b.options,
           "marks": b.marks, "negative_marks": float(b.negative_marks), "unit": b.unit,
           "outcome": b.outcome_id, "outcome_code": b.outcome.code if b.outcome_id else "",
           "bloom": b.bloom, "difficulty": b.difficulty, "is_active": b.is_active}
    if with_answer:
        out.update({"answer": b.answer, "model_answer": b.model_answer, "explanation": b.explanation})
    if usage is not None:
        out["used_in"] = usage.get(b.id, 0)
    return out


def _usage(subject_id):
    """{bank id: how many tests use it} (chosen questions + papers already handed out)."""
    used = defaultdict(set)
    for sec in QuizSection.objects.filter(quiz__teaching_assignment__subject_id=subject_id, pick="fixed"):
        for qid in sec.question_ids:
            used[qid].add(sec.quiz_id)
    for a in QuizAttempt.objects.filter(quiz__teaching_assignment__subject_id=subject_id).exclude(paper=[]) \
            .values("quiz_id", "paper"):
        for p in a["paper"]:
            used[p["q"]].add(a["quiz_id"])
    return {k: len(v) for k, v in used.items()}


@api(["GET", "POST"])
def bank(request):
    """List the bank (with filters) or add questions (one, or {questions: [...]})."""
    if request.method == "GET":
        p = request.query_params
        subject = _subject_for(request.user, p.get("subject"))
        qs = BankQuestion.objects.filter(subject=subject).select_related("outcome")
        if p.get("archived") != "1":
            qs = qs.filter(is_active=True)
        if p.get("unit"):
            qs = qs.filter(unit=p["unit"])
        if p.get("outcome"):
            qs = qs.filter(outcome_id=p["outcome"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("difficulty"):
            qs = qs.filter(difficulty=p["difficulty"])
        if p.get("q"):
            qs = qs.filter(text__icontains=p["q"].strip())
        usage = _usage(subject.id)
        return Response([question_payload(b, usage=usage) for b in qs.order_by("unit", "id")[:500]])

    subject = _subject_for(request.user, request.data.get("subject"))
    rows = request.data.get("questions")
    if rows is None:
        rows = [request.data]
    if not isinstance(rows, list) or not rows:
        raise Refuse("Send at least one question.")
    cleaned, errors = [], []
    for i, row in enumerate(rows, start=1):
        try:
            cleaned.append(clean_question(row if isinstance(row, dict) else {}, subject))
        except Refuse as e:
            errors.append(f"Question {i}: {e.msg}" if len(rows) > 1 else e.msg)
    if errors:
        raise Refuse("No questions were saved. " + (errors[0] if len(errors) == 1 else "Fix these first:"),
                     extra={"errors": errors})
    made = [BankQuestion.objects.create(subject=subject, created_by=request.user, **d) for d in cleaned]
    return Response({"created": len(made), "questions": [question_payload(b) for b in made]}, status=201)


@api(["PATCH", "DELETE"])
def bank_detail(request, pk):
    b = BankQuestion.objects.select_related("subject").filter(pk=pk).first()
    if b is None:
        raise Refuse("Question not found.", 404)
    if not teaches_subject(request.user, b.subject_id):
        raise Refuse("Only the subject's teachers can change its question bank.", 403)
    used = _usage(b.subject_id).get(b.id, 0)
    if request.method == "DELETE":
        if used:
            b.is_active = False
            b.save(update_fields=["is_active"])
            return Response({"archived": True, "detail": "This question is used in a test, so it was archived, not deleted."})
        b.delete()
        return Response(status=204)
    if "is_active" in request.data and len(request.data) == 1:
        b.is_active = bool(request.data["is_active"])
        b.save(update_fields=["is_active"])
        return Response(question_payload(b))
    d = clean_question(request.data, b.subject, existing=b)
    if used and (d["kind"] != b.kind or d.get("options") != b.options or d.get("answer") != b.answer):
        raise Refuse("This question is already in a test, so its type, options and answer can't change. "
                     "Add a new question instead.")
    for k, v in d.items():
        setattr(b, k, v)
    b.save()
    return Response(question_payload(b, usage={b.id: used}))


@api(["GET"])
def bank_meta(request):
    subject = _subject_for(request.user, request.query_params.get("subject"))
    from modules.teachingplan.models import CourseOutcome
    qs = BankQuestion.objects.filter(subject=subject, is_active=True)
    units = sorted({u for u in qs.values_list("unit", flat=True) if u})
    return Response({
        "subject": {"id": subject.id, "code": subject.code or "", "name": subject.name},
        "outcomes": [{"id": o.id, "code": o.code, "text": o.text}
                     for o in CourseOutcome.objects.filter(subject=subject).order_by("order", "id")],
        "units": units,
        "count": qs.count(),
        "by_kind": dict(Counter(qs.values_list("kind", flat=True))),
        "by_difficulty": dict(Counter(qs.values_list("difficulty", flat=True))),
        "by_outcome": {k or "none": v for k, v in Counter(qs.values_list("outcome__code", flat=True)).items()},
    })


@api(["POST"])
def bank_generate(request):
    """AI draft of MCQs from pasted notes. Nothing is saved: the teacher reviews
    the draft and saves it through bank POST."""
    subject = _subject_for(request.user, request.data.get("subject"))
    notes = (request.data.get("notes") or "").strip()
    if not notes:
        raise Refuse("Paste the notes to make questions from.")
    count = _num(request.data.get("count"), "How many", 1, 30, default=10)
    from .views import _clean_draft_row, _quiz_ai_generate
    try:
        raw = _quiz_ai_generate(subject.name, notes, count)
    except Exception as e:                       # surface it, never an empty draft
        raise Refuse(f"Could not make questions: {e}", 502)
    draft = []
    for r in raw:
        c = _clean_draft_row(r)
        if c:
            draft.append({"kind": "mcq", "text": c["text"],
                          "options": [c["option1"], c["option2"], c["option3"], c["option4"]],
                          "answer": [c["correct_answer"] - 1], "marks": 1, "difficulty": "medium"})
    return Response({"draft": draft, "requested": count,
                     "note": None if len(draft) >= count else f"{len(draft)} usable questions out of {count}."})


# ================================================================ tests
def _dt(v, label):
    if v in (None, ""):
        return None
    d = parse_datetime(str(v))
    if d is None:
        raise Refuse(f"{label}: use a date and time.")
    if timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def _bool(v):
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def clean_sections(rows, subject):
    """Check the paper's sections. Returns [dict] for QuizSection."""
    if not isinstance(rows, list) or not rows:
        raise Refuse("Add at least one section with questions.")
    out = []
    valid_ids = set(BankQuestion.objects.filter(subject=subject).values_list("id", flat=True))
    seen = set()
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            raise Refuse(f"Section {i} is not valid.")
        pick = r.get("pick", "fixed")
        if pick not in ("random", "fixed"):
            raise Refuse(f"Section {i}: choose random or chosen questions.")
        sec = {"order": i, "title": str(r.get("title") or f"Section {chr(64 + i)}")[:100], "pick": pick,
               "marks_each": _num(r.get("marks_each"), f"Section {i} marks each", 0, 100, default=0)}
        if pick == "fixed":
            ids = r.get("question_ids") or []
            try:
                ids = [int(x) for x in ids]
            except (TypeError, ValueError):
                raise Refuse(f"Section {i}: questions must be from the bank.")
            if not ids:
                raise Refuse(f"Section {i}: choose at least one question.")
            if any(x not in valid_ids for x in ids):
                raise Refuse(f"Section {i}: a question isn't in this subject's bank.")
            if seen & set(ids) or len(set(ids)) != len(ids):
                raise Refuse(f"Section {i}: a question appears twice in the paper.")
            seen |= set(ids)
            sec.update(question_ids=ids, count=len(ids), units=[], kinds=[], easy=0, medium=0, hard=0)
        else:
            units = r.get("units") or []
            kinds = r.get("kinds") or []
            try:
                units = sorted({int(u) for u in units})
            except (TypeError, ValueError):
                raise Refuse(f"Section {i}: units must be numbers.")
            if any(k not in KINDS for k in kinds):
                raise Refuse(f"Section {i}: unknown question type.")
            mix = {k: _num(r.get(k), k, 0, 200, default=0) for k in DIFFICULTIES}
            count = _num(r.get("count"), f"Section {i} how many", 1, 200, default=sum(mix.values()) or None)
            if any(mix.values()) and sum(mix.values()) != count:
                raise Refuse(f"Section {i}: easy + medium + hard must add up to {count}.")
            if not sec["marks_each"]:
                raise Refuse(f"Section {i}: set the marks for each question, so every student's paper has the same total.")
            sec.update(question_ids=[], count=count, units=units, kinds=sorted(set(kinds)), **mix)
        out.append(sec)
    return out


def _pool(subject_id, sec, exclude=()):
    qs = BankQuestion.objects.filter(subject_id=subject_id, is_active=True)
    if sec["units"]:
        qs = qs.filter(unit__in=sec["units"])
    if sec["kinds"]:
        qs = qs.filter(kind__in=sec["kinds"])
    if exclude:
        qs = qs.exclude(id__in=list(exclude))
    return qs


def paper_check(subject_id, sections):
    """Can each section be filled? And marks by CO / Bloom / type (expected for random sections)."""
    out, total, by_co, by_bloom, auto, hand = [], 0.0, Counter(), Counter(), 0.0, 0.0
    fixed_ids = {x for s in sections if s["pick"] == "fixed" for x in s["question_ids"]}
    bank = {b.id: b for b in BankQuestion.objects.filter(subject_id=subject_id).select_related("outcome")}
    for s in sections:
        if s["pick"] == "fixed":
            qs = [bank[x] for x in s["question_ids"] if x in bank]
            ok, have = True, len(qs)
            weight = 1.0
        else:
            pool = list(_pool(subject_id, s, exclude=fixed_ids).select_related("outcome"))
            have = len(pool)
            need = Counter({k: s[k] for k in DIFFICULTIES if s[k]})
            got = Counter(b.difficulty for b in pool)
            short = {k: need[k] - got[k] for k in need if got[k] < need[k]}
            ok = have >= s["count"] and not short
            qs = pool
            weight = (s["count"] / have) if have else 0
        marks_total = 0.0
        for b in qs:
            m = (s["marks_each"] or b.marks) * weight
            marks_total += m
            by_co[b.outcome.code if b.outcome_id else "No CO"] += m
            by_bloom[b.bloom or "not set"] += m
            if b.kind in OBJECTIVE:
                auto += m
            else:
                hand += m
        sec_marks = s["count"] * s["marks_each"] if s["pick"] == "random" else sum(
            (s["marks_each"] or b.marks) for b in qs)
        total += sec_marks
        row = {"title": s["title"], "pick": s["pick"], "count": s["count"], "available": have, "ok": ok,
               "marks": sec_marks}
        if s["pick"] == "random" and not ok:
            if have < s["count"]:
                row["problem"] = f"Only {have} questions match; {s['count']} needed."
            else:
                row["problem"] = "Not enough " + ", ".join(f"{k} ({v} short)" for k, v in short.items()) + " questions."
        out.append(row)
    r1 = lambda c: {k: round(v, 1) for k, v in sorted(c.items())}
    return {"sections": out, "total_marks": round(total, 1), "ok": all(x["ok"] for x in out),
            "by_outcome": r1(by_co), "by_bloom": r1(by_bloom),
            "auto_marks": round(auto, 1), "hand_marks": round(hand, 1)}


def test_state(q, now=None):
    now = now or timezone.now()
    if not q.is_published:
        return "draft"
    if q.opens_at and now < q.opens_at:
        return "upcoming"
    if q.due_date and now >= q.due_date:
        return "closed"
    return "open"


def _section_payload(s):
    return {"id": s.id, "order": s.order, "title": s.title, "pick": s.pick, "count": s.count, "units": s.units,
            "kinds": s.kinds, "easy": s.easy, "medium": s.medium, "hard": s.hard,
            "question_ids": s.question_ids, "marks_each": s.marks_each}


def test_payload(q, attempts=None):
    out = {"id": q.id, "title": q.title, "description": q.description or "", "teaching_assignment": q.teaching_assignment_id,
           "subject": q.teaching_assignment.subject_id, "duration": q.duration, "total_marks": q.total_marks,
           "opens_at": q.opens_at.isoformat() if q.opens_at else None,
           "closes_at": q.due_date.isoformat() if q.due_date else None,
           "is_published": q.is_published, "shuffle_questions": q.shuffle_questions,
           "shuffle_options": q.shuffle_options, "negative_marking": q.negative_marking,
           "show_answers": q.show_answers, "results_released": q.results_released,
           "state": test_state(q), "sections": [_section_payload(s) for s in q.sections.all()],
           "question_count": sum(s.count for s in q.sections.all())}
    if attempts is not None:
        out.update(attempts)
    return out


def _apply_test(q, data, subject):
    if "title" in data or q.pk is None:
        title = str(data.get("title") or "").strip()
        if not title:
            raise Refuse("Give the test a title.")
        q.title = title[:200]
    if "description" in data:
        q.description = str(data.get("description") or "")
    if "duration" in data or q.pk is None:
        q.duration = _num(data.get("duration"), "Time allowed (minutes)", 1, 600)
    if "opens_at" in data:
        q.opens_at = _dt(data.get("opens_at"), "Opens")
    if "closes_at" in data:
        q.due_date = _dt(data.get("closes_at"), "Closes")
    if q.opens_at and q.due_date and q.due_date <= q.opens_at:
        raise Refuse("The test must close after it opens.")
    for f in ("shuffle_questions", "shuffle_options", "negative_marking", "show_answers"):
        if f in data:
            setattr(q, f, _bool(data[f]))
    if "sections" in data or q.pk is None:
        return clean_sections(data.get("sections"), subject)
    return None


def _save_sections(q, sections):
    q.sections.all().delete()
    QuizSection.objects.bulk_create([QuizSection(quiz=q, **s) for s in sections])
    q.total_marks = int(round(paper_check(q.teaching_assignment.subject_id, sections)["total_marks"]))
    q.save(update_fields=["total_marks"])


def _attempt_counts(q):
    a = list(QuizAttempt.objects.filter(quiz=q).values("status", "written_pending", "score"))
    sub = [x for x in a if x["status"] == "submitted"]
    return {"started": len(a), "submitted": len(sub), "writing": len(a) - len(sub),
            "to_mark": sum(1 for x in sub if x["written_pending"]),
            "average": round(sum(x["score"] or 0 for x in sub) / len(sub), 1) if sub else None,
            "students": q.teaching_assignment.enrollments.count()}


def _student_view(q, user):
    a = QuizAttempt.objects.filter(quiz=q, student=user).first()
    mine = {"attempt": None}
    if a:
        _finalize_if_due(a)
        visible = a.status == "submitted" and (not a.written_pending or q.results_released)
        mine["attempt"] = {"id": a.id, "status": a.status,
                           "score": a.score if visible else None,
                           "being_marked": a.status == "submitted" and a.written_pending and not q.results_released,
                           "ends_at": a.ends_at.isoformat() if a.ends_at else None,
                           "can_review": bool(visible and q.show_answers and a.paper),
                           "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None}
    out = test_payload(q, mine)
    out.pop("sections")
    return out


@api(["GET", "POST"])
def tests(request):
    user = request.user
    if request.method == "GET":
        ta = request.query_params.get("teaching_assignment")
        qs = Quiz.objects.select_related("teaching_assignment__subject").prefetch_related("sections").order_by("-created_at")
        if ta:
            qs = qs.filter(teaching_assignment_id=ta)
        if user.role == "student":
            qs = qs.filter(teaching_assignment_id__in=list(get_enrolled_ta_ids(user)), is_published=True)
            return Response([_student_view(q, user) for q in qs])
        if not _is_admin(user):
            qs = qs.filter(teaching_assignment__teacher=user)
        return Response([test_payload(q, _attempt_counts(q)) for q in qs])

    ta = _ta_for_teacher(user, request.data.get("teaching_assignment"))
    q = Quiz(teaching_assignment=ta, created_by=user, is_published=False, results_released=False)
    with transaction.atomic():
        sections = _apply_test(q, request.data, ta.subject)
        q.save()
        _save_sections(q, sections)
    return Response(test_payload(q, _attempt_counts(q)), status=201)


@api(["GET", "PUT", "PATCH", "DELETE"])
def test_detail(request, pk):
    q = _test_for_teacher(request.user, pk)
    has_attempts = q.attempts.exists()
    if request.method == "GET":
        return Response(test_payload(q, _attempt_counts(q)))
    if request.method == "DELETE":
        if has_attempts:
            raise Refuse("Students have already written this test, so it can't be deleted.")
        q.delete()
        return Response(status=204)
    data = request.data
    if has_attempts:
        allowed = {"title", "description", "closes_at", "show_answers"}
        if set(data) - allowed:
            raise Refuse("Students have started this test, so only the title, the closing time "
                         "and showing answers can change.")
    with transaction.atomic():
        sections = _apply_test(q, data, q.teaching_assignment.subject)
        q.save()
        if sections is not None:
            _save_sections(q, sections)
    return Response(test_payload(q, _attempt_counts(q)))


@api(["POST"])
def test_check(request):
    """Live summary for the builder: can each section be filled, marks by CO / Bloom."""
    ta = _ta_for_teacher(request.user, request.data.get("teaching_assignment"))
    sections = clean_sections(request.data.get("sections"), ta.subject)
    return Response(paper_check(ta.subject_id, sections))


@api(["POST"])
def test_publish(request, pk):
    q = _test_for_teacher(request.user, pk)
    secs = [_section_payload(s) for s in q.sections.all()]
    if not secs:
        raise Refuse("Add questions to the paper first.")
    chk = paper_check(q.teaching_assignment.subject_id, secs)
    if not chk["ok"]:
        bad = next(s for s in chk["sections"] if not s["ok"])
        raise Refuse(f"{bad['title']}: {bad.get('problem', 'not enough questions')}", extra={"check": chk})
    if q.due_date and q.due_date <= timezone.now():
        raise Refuse("The closing time has already passed. Change it first.")
    first_time = not q.is_published
    q.is_published = True
    q.results_released = False if chk["hand_marks"] else True
    q.save(update_fields=["is_published", "results_released"])
    if first_time:
        when = (f"opens {timezone.localtime(q.opens_at):%d %b, %I:%M %p}" if q.opens_at and q.opens_at > timezone.now()
                else "is open now")
        Notification.objects.bulk_create([
            Notification(recipient=e.student, title="New online test",
                         message=f"{q.title} ({q.teaching_assignment.subject.name}) {when}"
                                 + (f" · closes {timezone.localtime(q.due_date):%d %b, %I:%M %p}" if q.due_date else ""),
                         notification_type="quiz", teaching_assignment=q.teaching_assignment)
            for e in q.teaching_assignment.enrollments.select_related("student")])
    return Response(test_payload(q, _attempt_counts(q)))


@api(["POST"])
def test_unpublish(request, pk):
    q = _test_for_teacher(request.user, pk)
    if q.attempts.exists():
        raise Refuse("Students have started this test, so it can't go back to a draft.")
    q.is_published = False
    q.save(update_fields=["is_published"])
    return Response(test_payload(q, _attempt_counts(q)))


@api(["GET"])
def test_attempts(request, pk):
    q = _test_for_teacher(request.user, pk)
    rows = []
    for a in QuizAttempt.objects.filter(quiz=q).select_related("student").order_by("student__roll_number"):
        _finalize_if_due(a)
        rows.append({"id": a.id, "student": a.student_id, "name": a.student.username,
                     "roll_number": a.student.roll_number or "", "status": a.status, "score": a.score,
                     "written_pending": a.written_pending, "tab_leaves": a.tab_leaves,
                     "answered": len([v for v in a.answers.values() if v not in (None, "", [])]),
                     "questions": len(a.paper),
                     "submitted_at": a.submitted_at.isoformat() if a.submitted_at and a.status == "submitted" else None})
    started = {r["student"] for r in rows}
    absent = [{"student": e.student_id, "name": e.student.username, "roll_number": e.student.roll_number or ""}
              for e in q.teaching_assignment.enrollments.select_related("student").order_by("student__roll_number")
              if e.student_id not in started]
    return Response({"test": test_payload(q, _attempt_counts(q)), "attempts": rows, "not_started": absent})


# ================================================================ writing a test (student)
def build_paper(q, rng=None):
    """A paper for one student: [{"q", "s", "m", "o"}]."""
    rng = rng or random.Random()
    secs = list(q.sections.all())
    fixed_ids = {x for s in secs if s.pick == "fixed" for x in s.question_ids}
    bank = {b.id: b for b in BankQuestion.objects.filter(subject_id=q.teaching_assignment.subject_id)}
    paper = []
    for si, s in enumerate(secs):
        if s.pick == "fixed":
            ids = [x for x in s.question_ids if x in bank]
            if q.shuffle_questions:
                rng.shuffle(ids)
        else:
            pool = list(_pool(q.teaching_assignment.subject_id, _section_payload(s), exclude=fixed_ids)
                        .values_list("id", "difficulty"))
            mix = {k: getattr(s, k) for k in DIFFICULTIES if getattr(s, k)}
            if mix:
                ids = []
                for k, n in mix.items():
                    cands = [i for i, d in pool if d == k]
                    ids += rng.sample(cands, min(n, len(cands)))
            else:
                ids = rng.sample([i for i, _d in pool], min(s.count, len(pool)))
            rng.shuffle(ids)
        for qid in ids:
            b = bank[qid]
            order = list(range(len(b.options)))
            if q.shuffle_options and b.kind in ("mcq", "multi"):
                rng.shuffle(order)
            paper.append({"q": qid, "s": si, "m": s.marks_each or b.marks, "o": order})
    return paper


def _paper_questions(a, with_answers=False):
    bank = {b.id: b for b in BankQuestion.objects.filter(id__in=[p["q"] for p in a.paper])}
    secs = list(a.quiz.sections.all())
    out = []
    for n, p in enumerate(a.paper, start=1):
        b = bank.get(p["q"])
        if b is None:
            continue
        row = {"n": n, "id": b.id, "kind": b.kind, "text": b.text, "marks": p["m"],
               "section": secs[p["s"]].title if p["s"] < len(secs) else "",
               "options": [{"i": i, "t": b.options[i]} for i in p["o"] if i < len(b.options)]}
        if with_answers:
            row.update({"answer": b.answer, "model_answer": b.model_answer, "explanation": b.explanation,
                        "awarded": a.awarded.get(str(b.id)), "given": a.answers.get(str(b.id)),
                        "comment": (a.feedback or {}).get(str(b.id), "")})
        out.append(row)
    return out


def _clean_answer(kind, v, n_options):
    """One answer as the student sent it -> what we store (None = blank)."""
    if v in (None, "", []):
        return None
    if kind == "mcq":
        try:
            i = int(v[0] if isinstance(v, list) else v)
        except (TypeError, ValueError, IndexError):
            return None
        return i if 0 <= i < n_options else None
    if kind == "multi":
        if not isinstance(v, list):
            v = [v]
        try:
            vals = sorted({int(x) for x in v})
        except (TypeError, ValueError):
            return None
        vals = [x for x in vals if 0 <= x < n_options]
        return vals or None
    if kind == "tf":
        if isinstance(v, str):
            v = {"true": True, "false": False}.get(v.strip().lower())
        return v if isinstance(v, bool) else None
    return str(v)[:20000]


def mark_objective(a):
    """Mark MCQ / multi / true-false. Written answers -> None (to mark).
    Returns (score so far, any written left?)."""
    bank = {b.id: b for b in BankQuestion.objects.filter(id__in=[p["q"] for p in a.paper])}
    neg_on = a.quiz.negative_marking
    awarded, score, pending = {}, 0.0, False
    for p in a.paper:
        b = bank.get(p["q"])
        if b is None:
            continue
        key = str(b.id)
        given = a.answers.get(key)
        if b.kind in WRITTEN:
            if given in (None, ""):
                awarded[key] = 0.0                    # nothing written: nothing to mark
            else:
                awarded[key] = None
                pending = True
            continue
        if given in (None, [], ""):
            awarded[key] = 0.0
            continue
        if b.kind == "mcq":
            right = [given] == list(b.answer or [])
        elif b.kind == "multi":
            right = sorted(given) == sorted(b.answer or [])
        else:
            right = given is b.answer
        if right:
            awarded[key] = float(p["m"])
        else:
            awarded[key] = -float(b.negative_marks) if neg_on else 0.0
        score += awarded[key]
    return awarded, round(score, 2), pending


def _submit(a, auto=False):
    a.awarded, a.score, a.written_pending = mark_objective(a)
    a.status = "submitted"
    a.submitted_at = timezone.now()
    a.save()          # one save: the parent notification signal fires once, on submit
    q = a.quiz
    Notification.objects.create(
        recipient=q.teaching_assignment.teacher, title="Online test submitted",
        message=f"{a.student.username} {'ran out of time on' if auto else 'submitted'} {q.title}",
        notification_type="quiz", teaching_assignment=q.teaching_assignment)


def _finalize_if_due(a):
    """Time is up and the student never pressed Submit: submit what was saved."""
    if a.status == "in_progress" and a.ends_at and timezone.now() > a.ends_at + GRACE:
        _submit(a, auto=True)
        return True
    return False


def _my_attempt(request, pk):
    a = QuizAttempt.objects.select_related("quiz__teaching_assignment__subject", "student").filter(pk=pk).first()
    if a is None or a.student_id != request.user.id:
        raise Refuse("Test not found.", 404)
    return a


def attempt_payload(a):
    q = a.quiz
    return {"id": a.id, "status": a.status, "test": {"id": q.id, "title": q.title, "subject": q.teaching_assignment.subject.name,
                                                     "total_marks": q.total_marks, "duration": q.duration},
            "now": timezone.now().isoformat(), "ends_at": a.ends_at.isoformat() if a.ends_at else None,
            "questions": _paper_questions(a) if a.status == "in_progress" else [],
            "answers": a.answers, "flagged": a.flagged, "tab_leaves": a.tab_leaves}


@api(["POST"])
def test_start(request, pk):
    user = request.user
    if user.role != "student":
        raise Refuse("Only students write tests. Use Preview to see it.", 403)
    q = Quiz.objects.select_related("teaching_assignment__subject").filter(pk=pk, is_published=True).first()
    if q is None or q.teaching_assignment_id not in set(get_enrolled_ta_ids(user)):
        raise Refuse("Test not found.", 404)
    existing = QuizAttempt.objects.filter(quiz=q, student=user).first()
    if existing:
        _finalize_if_due(existing)
        if existing.status == "submitted":
            raise Refuse("You have already written this test.")
        return Response(attempt_payload(existing))
    state = test_state(q)
    if state == "upcoming":
        raise Refuse(f"This test opens at {timezone.localtime(q.opens_at):%d %b, %I:%M %p}.")
    if state == "closed":
        raise Refuse("This test is closed.")
    paper = build_paper(q)
    now = timezone.now()
    with transaction.atomic():
        a, made = QuizAttempt.objects.get_or_create(
            quiz=q, student=user,
            defaults={"status": "in_progress", "started_at": now, "submitted_at": None,
                      "ends_at": now + datetime.timedelta(minutes=q.duration or 10), "paper": paper, "score": 0})
    return Response(attempt_payload(a), status=201 if made else 200)


@api(["GET"])
def attempt_detail(request, pk):
    a = _my_attempt(request, pk)
    _finalize_if_due(a)
    return Response(attempt_payload(a))


@api(["POST"])
def attempt_save(request, pk):
    """Autosave: merges answers; also records leaving the test tab (left: n)."""
    a = _my_attempt(request, pk)
    if _finalize_if_due(a):
        raise Refuse("Time is up. Your saved answers were submitted.", extra={"status": "submitted"})
    if a.status != "in_progress":
        raise Refuse("This test is already submitted.", extra={"status": a.status})
    kinds = {b.id: (b.kind, len(b.options)) for b in BankQuestion.objects.filter(id__in=[p["q"] for p in a.paper])}
    answers = dict(a.answers)
    for k, v in (request.data.get("answers") or {}).items():
        try:
            qid = int(k)
        except (TypeError, ValueError):
            continue
        if qid not in kinds:
            continue
        val = _clean_answer(kinds[qid][0], v, kinds[qid][1])
        if val is None:
            answers.pop(str(qid), None)
        else:
            answers[str(qid)] = val
    fields = {"answers": answers}
    if "flagged" in request.data:
        fields["flagged"] = [int(x) for x in (request.data.get("flagged") or []) if str(x).isdigit() and int(x) in kinds]
    left = request.data.get("left")
    with transaction.atomic():
        QuizAttempt.objects.filter(pk=a.pk).update(**fields)       # no signal: autosave is not a result
        if left:
            from django.db.models import F
            QuizAttempt.objects.filter(pk=a.pk).update(tab_leaves=F("tab_leaves") + max(0, min(int(left), 50)))
    a.refresh_from_db()
    return Response({"saved_at": timezone.now().isoformat(), "answered": len(a.answers), "tab_leaves": a.tab_leaves})


@api(["POST"])
def attempt_submit(request, pk):
    a = _my_attempt(request, pk)
    if a.status == "submitted":
        raise Refuse("This test is already submitted.")
    if a.ends_at and timezone.now() > a.ends_at + GRACE:
        _submit(a, auto=True)
    else:
        _merge_last(a, request.data)         # the last answers ride along with the submit
        _submit(a)
    q = a.quiz
    visible = not a.written_pending or q.results_released
    return Response({"status": "submitted", "score": a.score if visible else None, "total_marks": q.total_marks,
                     "being_marked": a.written_pending and not q.results_released})


def _merge_last(a, data):
    kinds = {b.id: (b.kind, len(b.options)) for b in BankQuestion.objects.filter(id__in=[p["q"] for p in a.paper])}
    for k, v in (data.get("answers") or {}).items():
        try:
            qid = int(k)
        except (TypeError, ValueError):
            continue
        if qid in kinds:
            val = _clean_answer(kinds[qid][0], v, kinds[qid][1])
            if val is None:
                a.answers.pop(str(qid), None)
            else:
                a.answers[str(qid)] = val


@api(["GET"])
def attempt_review(request, pk):
    a = _my_attempt(request, pk)
    q = a.quiz
    if a.status != "submitted" or not q.show_answers or (a.written_pending and not q.results_released):
        raise Refuse("Answers aren't shown for this test yet.", 403)
    # the model answer / marking points stay with the teachers
    qs = [{k: v for k, v in x.items() if k != "model_answer"} for x in _paper_questions(a, with_answers=True)]
    return Response({"test": {"id": q.id, "title": q.title, "total_marks": q.total_marks}, "score": a.score,
                     "questions": qs})


@api(["GET"])
def test_preview(request, pk):
    """The paper as a student would get it (a fresh random draw, nothing saved)."""
    q = _test_for_teacher(request.user, pk)
    a = QuizAttempt(quiz=q, paper=build_paper(q))
    return Response({"test": test_payload(q), "questions": _paper_questions(a, with_answers=True)})


# ================================================================ WAVE 3 PART 3b: marking + results
def rescore(a):
    """Total = every awarded mark so far; pending while any written answer is unmarked."""
    vals = list((a.awarded or {}).values())
    return round(sum(v for v in vals if v is not None), 2), any(v is None for v in vals)


def _test_attempts(q):
    rows = list(QuizAttempt.objects.filter(quiz=q).select_related("student").order_by("student__roll_number", "id"))
    for a in rows:
        _finalize_if_due(a)
    return rows


def _written_ids(attempts):
    ids = []
    for a in attempts:
        for p in a.paper:
            if p["q"] not in ids:
                ids.append(p["q"])
    bank = {b.id: b for b in BankQuestion.objects.filter(id__in=ids)}
    return [i for i in ids if i in bank and bank[i].is_written], bank


@api(["GET"])
def marking_overview(request, pk):
    q = _test_for_teacher(request.user, pk)
    atts = [a for a in _test_attempts(q) if a.status == "submitted"]
    ids, bank = _written_ids(atts)
    out = []
    for qid in ids:
        k = str(qid)
        given = [a for a in atts if k in a.awarded]
        written = [a for a in given if a.answers.get(k) not in (None, "")]
        out.append({"id": qid, "text": bank[qid].text, "kind": bank[qid].kind,
                    "marks": max((p["m"] for a in atts for p in a.paper if p["q"] == qid), default=bank[qid].marks),
                    "answers": len(written), "marked": sum(1 for a in written if a.awarded.get(k) is not None),
                    "outcome_code": bank[qid].outcome.code if bank[qid].outcome_id else "", "bloom": bank[qid].bloom})
    return Response({"test": test_payload(q, _attempt_counts(q)), "questions": out,
                     "left": sum(x["answers"] - x["marked"] for x in out)})


@api(["GET", "POST"])
def marking_question(request, pk, qid):
    """GET: every written answer to one question. POST {attempt, marks, comment}: mark one."""
    q = _test_for_teacher(request.user, pk)
    b = BankQuestion.objects.filter(pk=qid).first()
    if b is None or not b.is_written:
        raise Refuse("That isn't a written question of this test.", 404)
    k = str(b.id)
    if request.method == "POST":
        a = QuizAttempt.objects.filter(pk=request.data.get("attempt"), quiz=q, status="submitted").first()
        p = next((x for x in (a.paper if a else []) if x["q"] == b.id), None)
        if a is None or p is None:
            raise Refuse("That answer isn't in this test.", 404)
        if a.answers.get(k) in (None, ""):
            raise Refuse("Nothing was written for this question, so it stays at 0.")
        try:
            m = float(request.data.get("marks"))
        except (TypeError, ValueError):
            raise Refuse("Enter the marks.")
        if m < 0 or m > p["m"] or (m * 2) != int(m * 2):
            raise Refuse(f"Marks go from 0 to {p['m']}, in steps of 0.5.")
        awarded = dict(a.awarded)
        awarded[k] = m
        feedback = dict(a.feedback or {})
        comment = str(request.data.get("comment") or "").strip()[:1000]
        if comment:
            feedback[k] = comment
        else:
            feedback.pop(k, None)
        a.awarded, a.feedback = awarded, feedback
        a.score, a.written_pending = rescore(a)
        # update(), not save(): marking one answer is not a result - parents hear on release
        QuizAttempt.objects.filter(pk=a.pk).update(awarded=awarded, feedback=feedback, score=a.score,
                                                   written_pending=a.written_pending)
        return Response({"attempt": a.id, "marks": m, "comment": comment, "score": a.score,
                         "pending": a.written_pending})

    rows = []
    n = 0
    for a in _test_attempts(q):
        p = next((x for x in a.paper if x["q"] == b.id), None)
        if a.status != "submitted" or p is None:
            continue
        n += 1
        given = a.answers.get(k)
        rows.append({"attempt": a.id, "n": n, "name": a.student.username, "roll_number": a.student.roll_number or "",
                     "answer": given or "", "blank": given in (None, ""), "marks": a.awarded.get(k),
                     "max": p["m"], "comment": (a.feedback or {}).get(k, ""), "tab_leaves": a.tab_leaves})
    return Response({"question": {"id": b.id, "text": b.text, "kind": b.kind, "model_answer": b.model_answer,
                                  "outcome_code": b.outcome.code if b.outcome_id else "", "bloom": b.bloom},
                     "answers": rows})


@api(["GET"])
def test_results(request, pk):
    q = _test_for_teacher(request.user, pk)
    atts = _test_attempts(q)
    secs = list(q.sections.all())
    done = [a for a in atts if a.status == "submitted"]
    ids = list(dict.fromkeys(p["q"] for a in done for p in a.paper))
    bank = {b.id: b for b in BankQuestion.objects.filter(id__in=ids).select_related("outcome")}
    students = []
    co_got, co_max = Counter(), Counter()
    qstat = defaultdict(lambda: {"n": 0, "got": 0.0, "max": 0.0, "right": 0})
    for a in done:
        by_sec = defaultdict(float)
        for p in a.paper:
            got = a.awarded.get(str(p["q"]))
            if got is not None:
                by_sec[p["s"]] += got
            b = bank.get(p["q"])
            if b is None:
                continue
            code = b.outcome.code if b.outcome_id else "No CO"
            if got is not None:
                co_got[code] += max(got, 0)
                co_max[code] += p["m"]
                st = qstat[b.id]
                st["n"] += 1
                st["got"] += got
                st["max"] += p["m"]
                st["right"] += 1 if got >= p["m"] else 0
        students.append({"attempt": a.id, "student": a.student_id, "name": a.student.username,
                         "roll_number": a.student.roll_number or "", "score": a.score, "pending": a.written_pending,
                         "sections": [round(by_sec.get(i, 0), 2) for i in range(len(secs))],
                         "tab_leaves": a.tab_leaves})
    started = {a.student_id for a in atts}
    writing = [{"name": a.student.username, "roll_number": a.student.roll_number or ""} for a in atts if a.status != "submitted"]
    absent = [{"name": e.student.username, "roll_number": e.student.roll_number or ""}
              for e in q.teaching_assignment.enrollments.select_related("student").order_by("student__roll_number")
              if e.student_id not in started]
    scores = [x["score"] for x in students if not x["pending"]]
    hard = []
    for qid, st in qstat.items():
        b = bank[qid]
        hard.append({"id": qid, "text": b.text, "kind": b.kind, "answers": st["n"],
                     "average": round(st["got"] / st["n"], 2) if st["n"] else None,
                     "marks": round(st["max"] / st["n"], 2) if st["n"] else None,
                     "pct": round(st["got"] * 100 / st["max"], 1) if st["max"] else None,
                     "right_pct": round(st["right"] * 100 / st["n"], 1) if st["n"] else None})
    hard.sort(key=lambda x: (x["pct"] if x["pct"] is not None else 101))
    total = q.total_marks or 0
    return Response({
        "test": test_payload(q, _attempt_counts(q)),
        "sections": [{"title": s.title, "marks": (s.count * s.marks_each) if s.pick == "random" else None} for s in secs],
        "students": students, "writing": writing, "absent": absent,
        "summary": {"wrote": len(done), "absent": len(absent), "to_mark": sum(1 for x in students if x["pending"]),
                    "average": round(sum(scores) / len(scores), 2) if scores else None,
                    "highest": max(scores) if scores else None, "lowest": min(scores) if scores else None,
                    "under_half": sum(1 for x in scores if total and x * 2 < total),
                    "left_tab_3": sum(1 for x in students if x["tab_leaves"] >= 3)},
        "by_outcome": [{"code": k, "pct": round(co_got[k] * 100 / co_max[k], 1)} for k in sorted(co_max) if co_max[k]],
        "hardest": hard[:8],
    })


@api(["GET"])
def teacher_attempt(request, pk, aid):
    q = _test_for_teacher(request.user, pk)
    a = QuizAttempt.objects.select_related("student", "quiz").filter(pk=aid, quiz=q).first()
    if a is None:
        raise Refuse("Not found.", 404)
    _finalize_if_due(a)
    return Response({"student": {"name": a.student.username, "roll_number": a.student.roll_number or ""},
                     "status": a.status, "score": a.score, "pending": a.written_pending, "tab_leaves": a.tab_leaves,
                     "questions": _paper_questions(a, with_answers=True)})


@api(["POST"])
def test_release(request, pk):
    """Students (and parents) see the results. Every written answer must be marked."""
    q = _test_for_teacher(request.user, pk)
    atts = _test_attempts(q)
    if any(a.status != "submitted" for a in atts) and test_state(q) == "open":
        raise Refuse("Some students are still writing. Release the results after the test closes.")
    left = sum(1 for a in atts if a.status == "submitted" and a.written_pending)
    if left:
        raise Refuse(f"{left} student{'s have' if left != 1 else ' has'} answers still to mark.")
    first = not q.results_released
    q.results_released = True
    q.save(update_fields=["results_released"])
    if first:
        from core.notifications.services import notify_parents
        for a in atts:
            if a.status != "submitted":
                continue
            Notification.objects.create(recipient=a.student, title="Online test results",
                                        message=f"{q.title}: you scored {a.score} out of {q.total_marks}",
                                        notification_type="quiz", teaching_assignment=q.teaching_assignment)
            notify_parents(a.student, "Online test result",
                           f"Your child scored {a.score} out of {q.total_marks} in '{q.title}'",
                           "quiz", q.teaching_assignment)
    return Response(test_payload(q, _attempt_counts(q)))


@api(["POST"])
def test_withdraw(request, pk):
    q = _test_for_teacher(request.user, pk)
    q.results_released = False
    q.save(update_fields=["results_released"])
    return Response(test_payload(q, _attempt_counts(q)))
