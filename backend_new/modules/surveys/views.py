"""
WAVE 2 - SURVEYS API (all under /api/surveys/).

Building and results (managers)
  GET    manage/                  surveys I can manage, with response counts
  POST   manage/                  create a draft (with its questions)
  GET    manage/<id>/             one survey with questions
  PUT    manage/<id>/             replace a DRAFT (title, audience, dates, questions)
  DELETE manage/<id>/             delete a DRAFT
  POST   manage/<id>/publish/     draft -> open (tells everyone who should answer)
  POST   manage/<id>/close/       open -> closed
  GET    manage/<id>/results/     response rate + per-question summary
  GET    options/                 departments / courses I may target
  GET    templates/               ready-made surveys

Answering (students and teaching staff)
  GET    my/                      surveys meant for me (open ones, plus ones I answered)
  GET    my/<id>/                 the questions
  POST   my/<id>/submit/          {"answers": {"<question id>": value}}

Who manages
  college-wide : main admin, IQAC admin, academic admin, the Principal
  department   : the HOD (current, Acting HOD included) - their department only
"""
from collections import Counter, defaultdict

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as R

from core.academics.models import Enrollment
from core.notifications.services import notify
from core.users.models import Department, User

from .models import Answer, Participation, Question, Response, Survey
from .templates import TEMPLATES

COLLEGE_SUB_ROLES = ("iqac_admin", "academic_admin")
MAX_QUESTIONS = 50
MAX_OPTIONS = 20
MAX_TEXT_ANSWER = 2000
TEXT_ANSWERS_SHOWN = 300


# ---------------------------------------------------------------- who
def _college_manager(user):
    from core.users.acting_hod import is_main_admin
    from core.users.principal import is_principal
    if is_main_admin(user):
        return True
    if getattr(user, "role", "") == "admin" and (user.sub_role or "") in COLLEGE_SUB_ROLES:
        return True
    return is_principal(user)


def _hod_depts(user):
    if getattr(user, "role", "") != "teacher":
        return set()
    from core.users.acting_hod import hod_department_ids
    return set(hod_department_ids(user))


def _manageable(user):
    if _college_manager(user):
        return Survey.objects.all()
    depts = _hod_depts(user)
    return Survey.objects.filter(department_id__in=depts) if depts else Survey.objects.none()


def _can_create(user):
    return _college_manager(user) or bool(_hod_depts(user))


# ---------------------------------------------------------------- audience
def eligible_users(s):
    if s.teaching_assignment_id:              # CO-PO PART C: course exit survey = the subject's students
        return User.objects.filter(role="student", is_active=True,
                                   enrollment__teaching_assignment_id=s.teaching_assignment_id).distinct()
    if s.audience == Survey.Audience.STAFF:
        qs = User.objects.filter(role="teacher", is_active=True)
    else:
        qs = User.objects.filter(role="student", is_active=True)
        if s.course_id:
            qs = qs.filter(course_id=s.course_id)
        if s.year:
            qs = qs.filter(year=s.year)
        if s.semester:
            qs = qs.filter(semester=s.semester)
    if s.department_id:
        qs = qs.filter(department_id=s.department_id)
    return qs


def _surveys_for(user):
    """Q() for surveys aimed at this user (ignores status and dates)."""
    role = getattr(user, "role", "")
    dept = Q(department__isnull=True) | Q(department_id=user.department_id)
    if role == "teacher":
        return Q(audience=Survey.Audience.STAFF) & dept
    if role == "student":
        class_survey = (Q(audience=Survey.Audience.STUDENTS) & dept & Q(teaching_assignment__isnull=True)
                        & (Q(course__isnull=True) | Q(course_id=user.course_id))
                        & (Q(year__isnull=True) | Q(year=user.year))
                        & (Q(semester__isnull=True) | Q(semester=user.semester)))
        # CO-PO PART C: course exit surveys of subjects the student is enrolled in
        subject_ids = Enrollment.objects.filter(student=user).values_list("teaching_assignment_id", flat=True)
        return class_survey | Q(teaching_assignment_id__in=subject_ids)
    return None


def _group_of(u, audience):
    if audience == Survey.Audience.STAFF:
        return u.department.name if u.department_id else "No department"
    course = u.course.name if u.course_id else "No course"
    return f"{course} · Year {u.year}" if u.year else course


# ---------------------------------------------------------------- shapes
def _audience_text(s):
    if s.teaching_assignment_id:              # CO-PO PART C
        ta = s.teaching_assignment
        return f"Students of {ta.subject.code or ta.subject.name} · {ta.course.name} Year {ta.year.year_number}"
    who = "Teaching staff" if s.audience == Survey.Audience.STAFF else "Students"
    parts = [s.department.name if s.department_id else "all departments"]
    if s.audience == Survey.Audience.STUDENTS:
        if s.course_id:
            parts.append(s.course.name)
        if s.year:
            parts.append(f"Year {s.year}")
        if s.semester:
            parts.append(f"Sem {s.semester}")
    return f"{who} · " + " · ".join(parts)


def _survey(s, with_questions=False, extra=None):
    today = timezone.localdate()
    data = {
        "id": s.id, "title": s.title, "description": s.description, "audience": s.audience,
        "audience_text": _audience_text(s),
        "department": s.department_id, "course": s.course_id, "year": s.year, "semester": s.semester,
        "anonymous": s.anonymous, "status": s.status, "start_date": s.start_date, "end_date": s.end_date,
        "template": s.template, "accepting": s.is_accepting(today),
        "ended": bool(s.end_date and s.end_date < today),
        "created_by": (s.created_by.get_full_name() or s.created_by.username) if s.created_by_id else "",
        "created_at": s.created_at, "published_at": s.published_at,
    }
    if with_questions:
        data["questions"] = [{"id": q.id, "order": q.order, "kind": q.kind, "text": q.text,
                              "required": q.required, "options": q.options} for q in s.questions.all()]
    if extra:
        data.update(extra)
    return data


# ---------------------------------------------------------------- validation of the builder form
class Invalid(Exception):
    pass


def _int_or_none(value, lo, hi, label):
    if value in (None, "", "null"):
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise Invalid(f"{label} must be a number.")
    if not lo <= v <= hi:
        raise Invalid(f"{label} must be between {lo} and {hi}.")
    return v


def _clean(user, data):
    from datetime import date
    from core.academics.models import Course

    title = (data.get("title") or "").strip()
    if not title:
        raise Invalid("Give the survey a title.")
    audience = data.get("audience") or Survey.Audience.STUDENTS
    if audience not in Survey.Audience.values:
        raise Invalid("Audience must be students or staff.")

    dept_id = _int_or_none(data.get("department"), 1, 10**9, "Department")
    if not _college_manager(user):
        mine = _hod_depts(user)
        if dept_id is None and len(mine) == 1:
            dept_id = next(iter(mine))
        if dept_id not in mine:
            raise Invalid("As HOD you can only survey your own department.")
    dept = Department.objects.filter(id=dept_id).first() if dept_id else None
    if dept_id and dept is None:
        raise Invalid("That department does not exist.")

    course = year = semester = None
    if audience == Survey.Audience.STUDENTS:
        cid = _int_or_none(data.get("course"), 1, 10**9, "Course")
        course = Course.objects.filter(id=cid).first() if cid else None
        if cid and course is None:
            raise Invalid("That course does not exist.")
        year = _int_or_none(data.get("year"), 1, 4, "Year")
        semester = _int_or_none(data.get("semester"), 1, 10, "Semester")

    try:
        start = date.fromisoformat(str(data.get("start_date"))) if data.get("start_date") else timezone.localdate()
        end = date.fromisoformat(str(data.get("end_date"))) if data.get("end_date") else None
    except ValueError:
        raise Invalid("Dates must be YYYY-MM-DD.")
    if end and end < start:
        raise Invalid("The last day can't be before the first day.")

    questions = data.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise Invalid("Add at least one question.")
    if len(questions) > MAX_QUESTIONS:
        raise Invalid(f"A survey can have at most {MAX_QUESTIONS} questions.")
    clean_qs = []
    for i, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            raise Invalid(f"Question {i} is not valid.")
        text = (q.get("text") or "").strip()
        kind = q.get("kind") or Question.Kind.RATING
        if not text:
            raise Invalid(f"Question {i} has no text.")
        if kind not in Question.Kind.values:
            raise Invalid(f"Question {i} has an unknown type.")
        options = []
        if kind in (Question.Kind.CHOICE, Question.Kind.MULTI):
            seen = []
            for o in q.get("options") or []:
                o = str(o).strip()[:200]
                if o and o not in seen:
                    seen.append(o)
            if not 2 <= len(seen) <= MAX_OPTIONS:
                raise Invalid(f"Question {i} needs between 2 and {MAX_OPTIONS} different options.")
            options = seen
        clean_qs.append({"order": i, "kind": kind, "text": text[:500],
                         "required": bool(q.get("required", True)), "options": options})

    return {
        "title": title[:200], "description": (data.get("description") or "").strip()[:4000],
        "audience": audience, "department": dept, "course": course, "year": year, "semester": semester,
        "anonymous": bool(data.get("anonymous", True)), "start_date": start, "end_date": end,
        "template": str(data.get("template") or "")[:40],
    }, clean_qs


def _save(survey, fields, questions):
    for k, v in fields.items():
        setattr(survey, k, v)
    survey.save()
    survey.questions.all().delete()
    Question.objects.bulk_create([Question(survey=survey, **q) for q in questions])
    return survey


def _get_managed(user, pk):
    return (_manageable(user).select_related("department", "course", "created_by")
            .prefetch_related("questions").filter(pk=pk).first())


# ---------------------------------------------------------------- manager endpoints
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def manage_list(request):
    user = request.user
    if not _can_create(user):
        return R({"detail": "Surveys are built by HODs, the Principal and admins."}, status=403)
    if request.method == "POST":
        try:
            fields, questions = _clean(user, request.data)
        except Invalid as e:
            return R({"detail": str(e)}, status=400)
        with transaction.atomic():
            s = _save(Survey(created_by=user, status=Survey.Status.DRAFT), fields, questions)
        return R(_survey(_get_managed(user, s.id), with_questions=True), status=201)

    qs = (_manageable(user).select_related("department", "course", "created_by")
          .annotate(answered=Count("participations", distinct=True),
                    n_questions=Count("questions", distinct=True)))
    return R([_survey(s, extra={"answered": s.answered, "questions_count": s.n_questions,
                                "eligible": eligible_users(s).count()}) for s in qs])


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def manage_detail(request, pk):
    user = request.user
    s = _get_managed(user, pk)
    if s is None:
        return R({"detail": "Survey not found."}, status=404)
    if request.method == "GET":
        return R(_survey(s, with_questions=True))
    if s.status != Survey.Status.DRAFT:
        return R({"detail": "Only drafts can be changed or deleted. Close the survey instead."}, status=400)
    if request.method == "DELETE":
        s.delete()
        return R(status=204)
    try:
        fields, questions = _clean(user, request.data)
    except Invalid as e:
        return R({"detail": str(e)}, status=400)
    with transaction.atomic():
        _save(s, fields, questions)
    return R(_survey(_get_managed(user, s.id), with_questions=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manage_publish(request, pk):
    s = _get_managed(request.user, pk)
    if s is None:
        return R({"detail": "Survey not found."}, status=404)
    if s.status != Survey.Status.DRAFT:
        return R({"detail": "This survey is already published."}, status=400)
    today = timezone.localdate()
    if s.end_date and s.end_date < today:
        return R({"detail": "The last day to answer has already passed. Change the dates first."}, status=400)
    if not s.questions.exists():
        return R({"detail": "Add at least one question."}, status=400)
    people = list(eligible_users(s))
    if not people:
        return R({"detail": "Nobody matches this audience. Check the department, course, year and semester."},
                 status=400)
    s.status = Survey.Status.OPEN
    s.published_at = timezone.now()
    s.save(update_fields=["status", "published_at"])
    when = (f"from {s.start_date:%d-%m-%Y}" if s.start_date > today else "now")
    until = f" until {s.end_date:%d-%m-%Y}" if s.end_date else ""
    notify(people, f"Survey: {s.title}", f"Please answer this survey ({when}{until})."
           + (" Your answers are anonymous." if s.anonymous else ""), "announcement", link=f"/surveys/{s.id}")
    return R(_survey(s, extra={"notified": len(people)}))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manage_close(request, pk):
    s = _get_managed(request.user, pk)
    if s is None:
        return R({"detail": "Survey not found."}, status=404)
    if s.status != Survey.Status.OPEN:
        return R({"detail": "Only open surveys can be closed."}, status=400)
    s.status = Survey.Status.CLOSED
    s.closed_at = timezone.now()
    s.save(update_fields=["status", "closed_at"])
    return R(_survey(s))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def manage_results(request, pk):
    s = _get_managed(request.user, pk)
    if s is None:
        return R({"detail": "Survey not found."}, status=404)

    # response rate, overall and by class / department (from WHO answered, never from the answers)
    eligible = list(eligible_users(s).select_related("course", "department"))
    answered_ids = set(Participation.objects.filter(survey=s).values_list("user_id", flat=True))
    groups = defaultdict(lambda: [0, 0])
    for u in eligible:
        g = groups[_group_of(u, s.audience)]
        g[0] += 1
        if u.id in answered_ids:
            g[1] += 1
    answered = sum(1 for u in eligible if u.id in answered_ids)
    by_group = [{"group": k, "eligible": v[0], "answered": v[1],
                 "rate": round(v[1] * 100.0 / v[0], 1) if v[0] else None}
                for k, v in sorted(groups.items())]

    answers = defaultdict(list)
    for a in Answer.objects.filter(response__survey=s).select_related("response__respondent").order_by("-id"):
        answers[a.question_id].append(a)

    out = []
    for q in s.questions.all():
        rows = answers.get(q.id, [])
        item = {"id": q.id, "order": q.order, "kind": q.kind, "text": q.text, "required": q.required,
                "options": q.options}
        if q.kind == Question.Kind.RATING:
            ratings = [a.rating for a in rows if a.rating]
            dist = Counter(ratings)
            item.update(count=len(ratings),
                        average=round(sum(ratings) / len(ratings), 2) if ratings else None,
                        distribution={str(n): dist.get(n, 0) for n in range(1, 6)})
        elif q.kind in (Question.Kind.CHOICE, Question.Kind.MULTI):
            counts = Counter(c for a in rows for c in (a.choices or []))
            item.update(count=sum(1 for a in rows if a.choices),
                        counts=[{"option": o, "count": counts.get(o, 0)} for o in q.options])
        else:
            texts = [a for a in rows if a.text.strip()]
            item.update(count=len(texts), answers=[
                {"text": a.text, "by": "" if s.anonymous or not a.response.respondent_id
                 else (a.response.respondent.get_full_name() or a.response.respondent.username)}
                for a in texts[:TEXT_ANSWERS_SHOWN]])
        out.append(item)

    return R(_survey(s, extra={
        "eligible": len(eligible), "answered": answered,
        "rate": round(answered * 100.0 / len(eligible), 1) if eligible else None,
        "by_group": by_group, "questions": out,
    }))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def options(request):
    from core.academics.models import Course
    user = request.user
    if not _can_create(user):
        return R({"detail": "Surveys are built by HODs, the Principal and admins."}, status=403)
    college = _college_manager(user)
    depts = Department.objects.order_by("name")
    if not college:
        depts = depts.filter(id__in=_hod_depts(user))
    return R({
        "college_wide": college,
        "departments": [{"id": d.id, "name": d.name} for d in depts],
        "courses": [{"id": c.id, "name": c.name} for c in Course.objects.order_by("name")],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def templates(request):
    if not _can_create(request.user):
        return R({"detail": "Surveys are built by HODs, the Principal and admins."}, status=403)
    return R(TEMPLATES)


# ---------------------------------------------------------------- answering
def _mine(user):
    q = _surveys_for(user)
    if q is None:
        return Survey.objects.none()
    return Survey.objects.filter(q).exclude(status=Survey.Status.DRAFT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_list(request):
    user = request.user
    done = set(Participation.objects.filter(user=user).values_list("survey_id", flat=True))
    today = timezone.localdate()
    out = []
    for s in _mine(user).select_related("department", "course", "created_by"):
        if s.id not in done and not s.is_accepting(today):
            continue                       # missed / not started yet: not shown
        out.append(_survey(s, extra={"answered": s.id in done,
                                     "questions_count": s.questions.count()}))
    out.sort(key=lambda r: (r["answered"], str(r["end_date"] or "9999")))
    return R(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_detail(request, pk):
    s = _mine(request.user).select_related("department", "course", "created_by").filter(pk=pk).first()
    if s is None:
        return R({"detail": "Survey not found."}, status=404)
    answered = Participation.objects.filter(survey=s, user=request.user).exists()
    return R(_survey(s, with_questions=True, extra={"answered": answered}))


def _check_answer(q, value):
    """Return (rating, choices, text) or raise Invalid. None/'' = not answered."""
    empty = value in (None, "", [])
    if empty:
        if q.required:
            raise Invalid(f"Answer: {q.text}")
        return None
    if q.kind == Question.Kind.RATING:
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise Invalid(f"Choose 1 to 5 for: {q.text}")
        if not 1 <= v <= 5:
            raise Invalid(f"Choose 1 to 5 for: {q.text}")
        return v, [], ""
    if q.kind == Question.Kind.CHOICE:
        if value not in q.options:
            raise Invalid(f"Choose one of the options for: {q.text}")
        return None, [value], ""
    if q.kind == Question.Kind.MULTI:
        if not isinstance(value, list) or any(v not in q.options for v in value):
            raise Invalid(f"Choose from the options for: {q.text}")
        return None, list(dict.fromkeys(value)), ""
    text = str(value).strip()
    if not text:
        if q.required:
            raise Invalid(f"Answer: {q.text}")
        return None
    return None, [], text[:MAX_TEXT_ANSWER]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_submit(request, pk):
    user = request.user
    s = _mine(user).filter(pk=pk).first()
    if s is None:
        return R({"detail": "Survey not found."}, status=404)
    if not s.is_accepting():
        return R({"detail": "This survey is not taking answers now."}, status=400)
    given = request.data.get("answers") or {}
    if not isinstance(given, dict):
        return R({"detail": "answers must be an object of question id -> answer."}, status=400)
    rows = []
    try:
        for q in s.questions.all():
            checked = _check_answer(q, given.get(str(q.id), given.get(q.id)))
            if checked:
                rows.append((q, checked))
    except Invalid as e:
        return R({"detail": str(e)}, status=400)
    if not rows:
        return R({"detail": "Answer at least one question."}, status=400)
    try:
        with transaction.atomic():
            Participation.objects.create(survey=s, user=user)
            resp = Response.objects.create(survey=s, respondent=None if s.anonymous else user)
            Answer.objects.bulk_create([Answer(response=resp, question=q, rating=r, choices=c, text=t)
                                        for q, (r, c, t) in rows])
    except IntegrityError:
        return R({"detail": "You have already answered this survey."}, status=400)
    return R({"detail": "Thank you - your answers were saved.", "answered": True}, status=201)
