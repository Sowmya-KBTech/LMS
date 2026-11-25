"""WAVE 3 PART 2 - exam session APIs.

Exam admin:
  GET/POST            exam-sessions/
  GET/PATCH/DELETE    exam-sessions/<id>/
  POST                exam-sessions/<id>/make-current/
  GET                 exam-sessions/<id>/progress/
  GET                 exam-sessions/<id>/registrations/?course=&year=&semester=
  GET                 exam-sessions/<id>/timetable-check/
  POST                exam-sessions/<id>/publish-timetable/   (refused while there are clashes)
  POST                exam-sessions/<id>/unpublish-timetable/
  POST                exam-sessions/<id>/release-hall-tickets/
  POST                exam-sessions/<id>/withdraw-hall-tickets/
Student:
  GET/POST            exam-registration/me/
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import exam_sessions as svc
from .models import ExamSession


def _admin(request):
    from .views import is_exam_admin
    return is_exam_admin(request.user)


def _forbidden():
    return Response({"detail": "Only the exam admin can manage exam sessions."}, status=403)


def _date(value, label, errors):
    if value in (None, ""):
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    errors[label] = "Use a date like 30-11-2026."
    return None


def _money(value, label, errors):
    if value in (None, ""):
        return Decimal("0")
    try:
        v = Decimal(str(value))
    except InvalidOperation:
        errors[label] = "Enter an amount in rupees."
        return None
    if v < 0:
        errors[label] = "The amount can't be negative."
        return None
    return v


DATE_FIELDS = ("exam_start", "exam_end", "reg_opens", "reg_closes", "late_until")
MONEY_FIELDS = ("regular_fee", "arrear_fee", "late_fee")
BOOL_FIELDS = ("registration_required", "registration_closed", "students_pick_arrears", "fee_required")


def _apply(session, data):
    """Copy the posted fields onto the session, checking them. Returns errors."""
    errors = {}
    if "name" in data or session.pk is None:
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = "Give the session a name, like Nov/Dec 2026."
        elif len(name) > 30:
            errors["name"] = "Keep the name to 30 characters."
        elif ExamSession.objects.filter(name__iexact=name).exclude(pk=session.pk).exists():
            errors["name"] = "Another exam session already has this name."
        session.name = name
    if "kind" in data:
        if data["kind"] not in ("regular", "supplementary"):
            errors["kind"] = "Choose regular or supplementary."
        else:
            session.kind = data["kind"]
    for f in DATE_FIELDS:
        if f in data:
            setattr(session, f, _date(data[f], f, errors))
    for f in MONEY_FIELDS:
        if f in data:
            v = _money(data[f], f, errors)
            if v is not None:
                setattr(session, f, v)
    for f in BOOL_FIELDS:
        if f in data:
            setattr(session, f, bool(data[f]))
    if "semesters" in data:
        sems = data["semesters"] or []
        try:
            sems = sorted({int(x) for x in sems})
        except (TypeError, ValueError):
            sems = None
        if sems is None or any(x < 1 or x > 8 for x in sems):
            errors["semesters"] = "Semesters must be numbers from 1 to 8."
        else:
            session.semesters = sems
    s = session
    if s.exam_start and s.exam_end and s.exam_end < s.exam_start:
        errors.setdefault("exam_end", "The last exam date is before the first.")
    if s.reg_opens and s.reg_closes and s.reg_closes < s.reg_opens:
        errors.setdefault("reg_closes", "Registration closes before it opens.")
    if s.late_until and s.reg_closes and s.late_until < s.reg_closes:
        errors.setdefault("late_until", "Late registration must end on or after the closing date.")
    if s.registration_required and not s.reg_opens:
        errors.setdefault("reg_opens", "Set the date registration opens.")
    return errors


def _with_counts(s):
    out = svc.session_payload(s)
    out["registrations"] = s.registrations.filter(status="submitted").count()
    out["timetable_rows"] = s.schedules.count()
    return out


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def sessions(request):
    if not _admin(request):
        return _forbidden()
    if request.method == "GET":
        return Response([_with_counts(s) for s in ExamSession.objects.all()])
    s = ExamSession()
    errors = _apply(s, request.data)
    if errors:
        return Response({"detail": "Please fix the highlighted fields.", "errors": errors}, status=400)
    with transaction.atomic():
        first = not ExamSession.objects.exists()
        s.is_current = first or bool(request.data.get("is_current"))
        if s.is_current:
            ExamSession.objects.filter(is_current=True).update(is_current=False)
        s.save()
    return Response(_with_counts(s), status=201)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def session_detail(request, pk):
    if not _admin(request):
        return _forbidden()
    s = ExamSession.objects.filter(pk=pk).first()
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    if request.method == "GET":
        return Response(_with_counts(s))
    if request.method == "DELETE":
        if s.registrations.exists() or s.schedules.exists():
            return Response({"detail": "This session already has registrations or exam dates, so it can't be deleted."},
                            status=400)
        s.delete()
        return Response(status=204)
    errors = _apply(s, request.data)
    if errors:
        return Response({"detail": "Please fix the highlighted fields.", "errors": errors}, status=400)
    s.save()
    return Response(_with_counts(s))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def make_current(request, pk):
    if not _admin(request):
        return _forbidden()
    s = ExamSession.objects.filter(pk=pk).first()
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    with transaction.atomic():
        ExamSession.objects.filter(is_current=True).exclude(pk=s.pk).update(is_current=False)
        s.is_current = True
        s.save(update_fields=["is_current"])
    return Response(_with_counts(s))


def _get(pk):
    return ExamSession.objects.filter(pk=pk).first()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_progress(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    return Response(svc.progress(s))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_registrations(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    p = request.query_params
    if not (p.get("course") and p.get("year") and p.get("semester")):
        return Response({"detail": "course, year and semester are required."}, status=400)
    return Response(svc.class_registrations(s, p["course"], p["year"], p["semester"]))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def timetable_check(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    return Response(svc.timetable_check(s))


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 'es' if word.endswith('sh') else 's'}"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def publish_timetable(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    check = svc.timetable_check(s)
    n_clash, n_open = len(check["clashes"]), len(check["unscheduled"])
    if not check["days"]:
        return Response({"detail": "There are no exam dates in this session yet."}, status=400)
    if n_clash or n_open:
        parts = []
        if n_clash:
            parts.append(_plural(n_clash, "clash"))
        if n_open:
            parts.append(f"{_plural(n_open, 'paper')} without a date")
        return Response({"detail": f"Fix {' and '.join(parts)} before publishing.", "check": check}, status=400)
    s.timetable_published = True
    s.save(update_fields=["timetable_published"])
    return Response(_with_counts(s))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unpublish_timetable(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    s.timetable_published = False
    s.hall_tickets_released = False
    s.save(update_fields=["timetable_published", "hall_tickets_released"])
    return Response(_with_counts(s))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def release_hall_tickets(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    if not s.timetable_published:
        return Response({"detail": "Publish the timetable before releasing hall tickets."}, status=400)
    s.hall_tickets_released = True
    s.save(update_fields=["hall_tickets_released"])
    return Response(_with_counts(s))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw_hall_tickets(request, pk):
    if not _admin(request):
        return _forbidden()
    s = _get(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    s.hall_tickets_released = False
    s.save(update_fields=["hall_tickets_released"])
    return Response(_with_counts(s))


# ------------------------------------------------------------------ student
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def my_registration(request):
    user = request.user
    if user.role != "student":
        return Response({"detail": "Students only."}, status=403)
    s = svc.current_session()
    if s is None or not s.registration_required:
        return Response({"session": None, "detail": "There is no exam registration open right now."})
    if request.method == "POST":
        try:
            svc.save_registration(s, user, request.data.get("arrear_subjects") or [], bool(request.data.get("submit")))
        except svc.RegistrationError as e:
            return Response({"detail": str(e.args[0])}, status=400)
    return Response(svc.registration_view(s, user))
