"""
WAVE 1 - STUDENT PLANNER: one place for a student's days.

  GET /api/planner/?start=YYYY-MM-DD&days=7          a student: their own planner
  GET /api/planner/?child=<id>&start=...&days=...    a parent: one of their children

For each day it lists the student's classes (from the APPROVED timetable,
only inside the active semester, not on holidays), and dated items:
  assignment  due date      (status: submitted / pending / overdue)
  quiz        due date      (status: attempted / pending / overdue)
  exam        exam schedule (FN / AN)
  live        live class with a scheduled time
  event       calendar events the student can see (holidays, exams, events)
  leave       the student's approved leave days

Every source module is optional: if a college has switched a module off,
its items are simply missing.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from django.apps import apps
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.academics.models import Enrollment, TeachingAssignment
from core.users.models import User

from .models import Holiday, Semester

MAX_DAYS = 42
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _student_for(request):
    """The student this planner is for, or (None, error response)."""
    user = request.user
    role = getattr(user, "role", None)
    if role == "student":
        return user, None
    if role == "parent":
        profile = getattr(user, "parent_profile", None)
        kids = profile.children.all() if profile else User.objects.none()
        child = request.query_params.get("child")
        if child:
            kid = kids.filter(id=child).first() if str(child).isdigit() else None
        else:
            kid = kids.first()
        if kid is None:
            return None, Response({"detail": "Child not found."}, status=404)
        return kid, None
    return None, Response({"detail": "The planner is for students and parents."}, status=403)


def _range(request):
    params = request.query_params
    try:
        start = date.fromisoformat(params["start"]) if params.get("start") else timezone.localdate()
        days = int(params.get("days", 7))
    except (ValueError, TypeError):
        return None, None, Response({"detail": "start must be YYYY-MM-DD and days a number."}, status=400)
    days = max(1, min(days, MAX_DAYS))
    return start, start + timedelta(days=days - 1), None


def _ta_ids(student):
    """The subject-classes this student sits in: enrolments, else their class."""
    ids = list(Enrollment.objects.filter(student=student).values_list("teaching_assignment_id", flat=True))
    if ids:
        return ids
    if student.course_id and student.year and student.semester:
        return list(TeachingAssignment.objects.filter(
            course_id=student.course_id, year__year_number=student.year,
            subject__semester=student.semester).values_list("id", flat=True))
    return []


def _timetable(student):
    """Approved weekly entries for the student, grouped by weekday (0 = Monday)."""
    from .views import TimetableListCreate
    view = TimetableListCreate()
    view.request = SimpleNamespace(user=student, query_params={})
    view.kwargs = {}
    week = {}
    for e in view.get_queryset():
        if e.assignment_id:
            subj = e.assignment.subject
            title, code = subj.name, getattr(subj, "code", "") or ""
            teacher = e.assignment.teacher
        elif e.class_activity_id:
            title, code = e.class_activity.activity.name, ""
            teacher = e.class_activity.teacher
        else:
            continue
        week.setdefault(e.day_of_week, []).append({
            "period": e.time_slot.period_no,
            "start": e.time_slot.start_time.strftime("%H:%M"),
            "end": e.time_slot.end_time.strftime("%H:%M"),
            "subject": title, "code": code, "kind": e.kind,
            "teacher": (teacher.get_full_name() or teacher.username) if teacher else "",
            "room": e.room.name if e.room_id else "",
        })
    for rows in week.values():
        rows.sort(key=lambda r: r["period"])
    return week


def _local(dt):
    return timezone.localtime(dt) if timezone.is_aware(dt) else dt


def _deadline_items(student, ta_ids, start, end, now):
    if not apps.is_installed("modules.learning"):
        return []
    from modules.learning.models import Assignment, Lecture, Quiz, QuizAttempt, Submission

    lo = timezone.make_aware(datetime.combine(start, datetime.min.time()))
    hi = timezone.make_aware(datetime.combine(end + timedelta(days=1), datetime.min.time()))
    items = []

    done = set(Submission.objects.filter(student=student).values_list("assignment_id", flat=True))
    for a in (Assignment.objects.filter(teaching_assignment_id__in=ta_ids, due_date__gte=lo, due_date__lt=hi)
              .select_related("teaching_assignment__subject")):
        due = _local(a.due_date)
        status = "submitted" if a.id in done else ("overdue" if a.due_date < now else "pending")
        items.append({"type": "assignment", "id": a.id, "date": due.date().isoformat(),
                      "time": due.strftime("%H:%M"), "title": a.title,
                      "subject": a.teaching_assignment.subject.name, "status": status})

    tried = set(QuizAttempt.objects.filter(student=student).values_list("quiz_id", flat=True))
    for q in (Quiz.objects.filter(teaching_assignment_id__in=ta_ids, due_date__gte=lo, due_date__lt=hi,
                                  is_published=True)          # WAVE 3 PART 3: no drafts
              .select_related("teaching_assignment__subject")):
        due = _local(q.due_date)
        status = "attempted" if q.id in tried else ("overdue" if q.due_date < now else "pending")
        items.append({"type": "quiz", "id": q.id, "date": due.date().isoformat(),
                      "time": due.strftime("%H:%M"), "title": q.title,
                      "subject": q.teaching_assignment.subject.name, "status": status})

    for lec in (Lecture.objects.filter(teaching_assignment_id__in=ta_ids, is_live=True,
                                       scheduled_time__gte=lo, scheduled_time__lt=hi)
                .select_related("teaching_assignment__subject")):
        at = _local(lec.scheduled_time)
        items.append({"type": "live", "id": lec.id, "date": at.date().isoformat(),
                      "time": at.strftime("%H:%M"), "title": lec.title,
                      "subject": lec.teaching_assignment.subject.name, "status": "",
                      "link": lec.meeting_link or ""})
    return items


def _exam_items(ta_ids, start, end):
    if not apps.is_installed("modules.exams"):
        return []
    from modules.exams.models import ExamSchedule
    subject_ids = TeachingAssignment.objects.filter(id__in=ta_ids).values_list("subject_id", flat=True)
    return [{"type": "exam", "id": x.id, "date": x.exam_date.isoformat(),
             "time": x.session, "title": f"{x.subject.name} exam",
             "subject": x.subject.name, "status": x.get_session_display()}
            for x in ExamSchedule.objects.filter(subject_id__in=list(subject_ids),
                                                 exam_date__range=(start, end)).select_related("subject")]


def _event_items(student, start, end):
    if not apps.is_installed("modules.events"):
        return []
    from modules.events.models import CalendarEvent
    from modules.events.views import get_student_year
    year = get_student_year(student) or student.year
    qs = CalendarEvent.objects.filter(
        Q(audience="everyone")
        | Q(audience="students", year_number__isnull=True)
        | Q(audience="students", year_number=year)
    ).filter(start_date__lte=end).filter(Q(end_date__gte=start) | Q(end_date__isnull=True, start_date__gte=start))
    out = []
    for ev in qs:
        first, last = max(ev.start_date, start), min(ev.end_date or ev.start_date, end)
        d = first
        while d <= last:                                   # one row per day it covers
            out.append({"type": "event", "id": ev.id, "date": d.isoformat(), "time": "",
                        "title": ev.title, "subject": "", "status": ev.get_event_type_display(),
                        "kind": ev.event_type})
            d += timedelta(days=1)
    return out


def _leave_days(student, start, end):
    if not apps.is_installed("modules.attendance"):
        return set()
    from modules.attendance.models import StudentLeaveRequest
    days = set()
    for lv in StudentLeaveRequest.objects.filter(
            student=student, status=StudentLeaveRequest.Status.APPROVED,
            from_date__lte=end, to_date__gte=start):
        d = max(lv.from_date, start)
        while d <= min(lv.to_date, end):
            days.add(d)
            d += timedelta(days=1)
    return days


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def planner(request):
    student, error = _student_for(request)
    if error:
        return error
    start, end, error = _range(request)
    if error:
        return error

    now = timezone.now()
    ta_ids = _ta_ids(student)
    week = _timetable(student)
    sem = Semester.objects.filter(is_active=True).order_by("-start_date").first()
    holidays = dict(Holiday.objects.filter(date__range=(start, end)).values_list("date", "name"))
    leave = _leave_days(student, start, end)

    items = (_deadline_items(student, ta_ids, start, end, now) + _exam_items(ta_ids, start, end)
             + _event_items(student, start, end))
    by_day = {}
    for it in items:
        by_day.setdefault(it["date"], []).append(it)

    days = []
    d = start
    while d <= end:
        in_term = sem is None or sem.start_date <= d <= sem.end_date
        off = holidays.get(d)
        classes = [] if (off or not in_term or d in leave) else week.get(d.weekday(), [])
        day_items = sorted(by_day.get(d.isoformat(), []), key=lambda x: (x["time"] or "", x["type"]))
        days.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()],
                     "holiday": off or "", "on_leave": d in leave,
                     "classes": classes, "items": day_items})
        d += timedelta(days=1)

    pending = [it for it in items if it["status"] in ("pending", "overdue")]
    return Response({
        "student": {"id": student.id, "name": student.get_full_name() or student.username},
        "start": start.isoformat(), "end": end.isoformat(), "today": timezone.localdate().isoformat(),
        "summary": {
            "classes": sum(len(x["classes"]) for x in days),
            "due": sum(1 for it in pending if it["status"] == "pending"),
            "overdue": sum(1 for it in pending if it["status"] == "overdue"),
            "exams": sum(1 for it in items if it["type"] == "exam"),
        },
        "days": days,
    })
