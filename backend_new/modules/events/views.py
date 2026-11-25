from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import CalendarEvent, Announcement
from .serializers import CalendarEventSerializer, AnnouncementSerializer

# cross-app imports from courses
from core.academics.models import Enrollment
from core.notifications.models import Notification
from core.academics.helpers import get_parent_children

User = get_user_model()


# ===================== CALENDAR HELPERS =====================
def get_student_year(user):
    en = Enrollment.objects.filter(student=user).first()
    if en:
        return en.teaching_assignment.year.year_number
    return None


def get_parent_child_years(user):
    years = []
    for child in get_parent_children(user):
        y = get_student_year(child)
        if y is not None:
            years.append(y)
    return years


def notify_calendar_audience(event):
    date_text = event.start_date.strftime("%d %b %Y")
    title = f"{event.get_event_type_display()}: {event.title}"
    message = f"{event.title} on {date_text}"

    if event.audience == 'everyone':
        recipients = User.objects.all()
    elif event.audience == 'teachers':
        recipients = User.objects.filter(role='teacher')
    elif event.audience == 'students':
        recipients = User.objects.filter(role='student')
        if event.year_number:
            ids = [s.id for s in recipients if get_student_year(s) == event.year_number]
            recipients = User.objects.filter(id__in=ids)
    elif event.audience == 'parents':
        recipients = User.objects.filter(role='parent')
        if event.year_number:
            ids = [p.id for p in recipients if event.year_number in get_parent_child_years(p)]
            recipients = User.objects.filter(id__in=ids)
    else:
        recipients = User.objects.none()

    for u in recipients:
        Notification.objects.create(
            recipient=u, title=title, message=message,
            notification_type='announcement',
        )


# ===================== CALENDAR EVENT =====================
class CalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return CalendarEvent.objects.all().order_by('start_date')

        qs = CalendarEvent.objects.filter(audience='everyone')

        if user.role == 'teacher':
            qs = qs | CalendarEvent.objects.filter(audience='teachers')
        elif user.role == 'student':
            se = CalendarEvent.objects.filter(audience='students').filter(
                models.Q(year_number__isnull=True) | models.Q(year_number=get_student_year(user))
            )
            qs = qs | se
        elif user.role == 'parent':
            pe = CalendarEvent.objects.filter(audience='parents').filter(
                models.Q(year_number__isnull=True) | models.Q(year_number__in=get_parent_child_years(user))
            )
            qs = qs | pe

        return qs.distinct().order_by('start_date')

    def perform_create(self, serializer):
        if self.request.user.role != 'admin':
            raise ValidationError("Only admin can add calendar events.")
        event = serializer.save(created_by=self.request.user)
        notify_calendar_audience(event)

    def perform_update(self, serializer):
        if self.request.user.role != 'admin':
            raise ValidationError("Only admin can edit calendar events.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.role != 'admin':
            raise ValidationError("Only admin can delete calendar events.")
        instance.delete()


# ===================== CALENDAR FEED (events + collapsed exam markers) =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def calendar_feed(request):
    user = request.user
    month = request.query_params.get("month")
    year = request.query_params.get("year")
    if not (month and year):
        return Response({"detail": "month and year are required."}, status=400)

    items = []

    # ---- admin events, audience-filtered ----
    if user.role == 'admin':
        events = CalendarEvent.objects.all()
    else:
        events = CalendarEvent.objects.filter(audience='everyone')
        if user.role == 'teacher':
            events = events | CalendarEvent.objects.filter(audience='teachers')
        elif user.role == 'student':
            se = CalendarEvent.objects.filter(audience='students').filter(
                models.Q(year_number__isnull=True) | models.Q(year_number=get_student_year(user))
            )
            events = events | se
        elif user.role == 'parent':
            pe = CalendarEvent.objects.filter(audience='parents').filter(
                models.Q(year_number__isnull=True) | models.Q(year_number__in=get_parent_child_years(user))
            )
            events = events | pe
        events = events.distinct()

    events = events.filter(start_date__month=month, start_date__year=year)

    for e in events:
        items.append({
            "id": f"event-{e.id}", "title": e.title, "type": e.event_type,
            "audience": e.audience, "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "description": e.description,
        })

    # ---- exam dates: collapse to "Semester Exams Start / End" per semester ----
    ExamSchedule = optional_model("exams", "exams", "ExamSchedule")  # no exam dates if exams is off
    from django.db.models import Min, Max

    exam_qs = ExamSchedule.objects.all()
    # WAVE 3 PART 2: only the current exam session's dates
    if module_enabled("exams"):
        from modules.exams.exam_sessions import current_session
        _cur = current_session()
        exam_qs = exam_qs.filter(exam_session=_cur) if _cur else exam_qs.filter(exam_session__isnull=True)
    # students see only their own semester's exams
    if user.role == 'student' and user.semester:
        exam_qs = exam_qs.filter(semester=user.semester)

    # group by semester, find first & last exam date
    spans = (
        exam_qs.values("semester")
        .annotate(first=Min("exam_date"), last=Max("exam_date"))
    )

    for sp in spans:
        sem = sp["semester"]
        first = sp["first"]
        last = sp["last"]

        # show the start marker only if it falls in the requested month
        if first and first.month == int(month) and first.year == int(year):
            items.append({
                "id": f"examstart-{sem}",
                "title": f"Semester {sem} Exams Start",
                "type": "exam",
                "audience": "students",
                "start_date": first.isoformat(),
                "end_date": None,
                "description": f"Semester {sem} examinations begin",
            })

        # show the end marker only if it falls in the requested month
        if last and last.month == int(month) and last.year == int(year):
            items.append({
                "id": f"examend-{sem}",
                "title": f"Semester {sem} Exams End",
                "type": "exam",
                "audience": "students",
                "start_date": last.isoformat(),
                "end_date": None,
                "description": f"Semester {sem} examinations end",
            })

    # ---- group events: the audience is the group's own student query, so a
    # ---- Civil event cannot reach a Mechanical student the way a
    # ---- CalendarEvent row would (it filters on year_number alone)
    # no group events if class groups is off
    ClassEvent = optional_model("classgroups", "classgroups", "ClassEvent")
    ClassGroup = optional_model("classgroups", "classgroups", "ClassGroup")

    my_group_ids = [
        g.id for g in ClassGroup.objects.filter(is_archived=False)
        if g.students().filter(id=user.id).exists() or g.owner() == user
    ]
    if my_group_ids:
        for ev in (ClassEvent.objects
                   .filter(message__group_id__in=my_group_ids,
                           message__is_deleted=False,
                           starts_at__month=int(month), starts_at__year=int(year))
                   .select_related("message", "message__group")):
            items.append({
                "id": f"groupevent-{ev.message_id}",
                "title": ev.message.title,
                "type": "event",
                "audience": "students",
                # FIX #7: convert to local (IST) time before taking the date / clock
                "start_date": timezone.localtime(ev.starts_at).date().isoformat(),
                "end_date": timezone.localtime(ev.ends_at).date().isoformat() if ev.ends_at else None,
                "description": (
                    f"{ev.message.group.display_name} · "
                    f"{timezone.localtime(ev.starts_at):%I:%M %p}"
                    + (f" · {ev.location}" if ev.location else "")
                ),
            })

    items.sort(key=lambda x: x["start_date"])
    return Response(items)


# ===================== ANNOUNCEMENT =====================
class AnnouncementViewSet(viewsets.ModelViewSet):
    """
    Admin and sub-admins (accounts/exam/academic) post/edit/delete announcements.
    Each announcement targets an audience; users see and are notified
    only for announcements meant for their group (+ 'everyone').
    """

    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    # roles allowed to post announcements
    ADMIN_ROLES = ('admin', 'accounts_admin', 'exam_admin', 'academic_admin')

    def get_queryset(self):
        user = self.request.user

        # admins + sub-admins see all
        if user.role in self.ADMIN_ROLES:
            return Announcement.objects.all()

        # everyone else: 'everyone' announcements + their own group
        role_aud = {
            'teacher': 'teachers',
            'student': 'students',
            'parent': 'parents',
        }.get(user.role)

        return Announcement.objects.filter(
            models.Q(audience='everyone') | models.Q(audience=role_aud)
        )

    def perform_create(self, serializer):
        if self.request.user.role not in self.ADMIN_ROLES:
            raise ValidationError("You are not allowed to post announcements.")
        ann = serializer.save(posted_by=self.request.user)

        # notify only the chosen audience
        if ann.audience == 'everyone':
            recipients = User.objects.exclude(id=self.request.user.id)
        elif ann.audience == 'students':
            recipients = User.objects.filter(role='student')
        elif ann.audience == 'teachers':
            recipients = User.objects.filter(role='teacher')
        elif ann.audience == 'parents':
            recipients = User.objects.filter(role='parent')
        else:
            recipients = User.objects.none()

        for u in recipients:
            Notification.objects.create(
                recipient=u,
                title=f"Announcement: {ann.title}",
                message=ann.message[:120],
                notification_type='announcement',
            )

    def perform_update(self, serializer):
        if self.request.user.role not in self.ADMIN_ROLES:
            raise ValidationError("You are not allowed to edit announcements.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.role not in self.ADMIN_ROLES:
            raise ValidationError("You are not allowed to delete announcements.")
        instance.delete()


# ===================== GOOGLE HOLIDAY SYNC =====================
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from django.conf import settings
from config.module_registry import optional_model, module_enabled

INDIA_HOLIDAY_CALENDAR_ID = "en.indian#holiday@group.v.calendar.google.com"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_holidays(request):
    """
    Admin-only. Fetches India's national holidays from Google for a year
    and stores them as CalendarEvent holiday rows (source='google').
    Re-running replaces previous Google holidays without touching manual ones.
    Optional body: {"year": 2026}. Defaults to the current year.
    """
    user = request.user
    is_admin = user.is_staff or getattr(user, "role", "") in ("admin", "principal", "iqac")
    if not is_admin:
        return Response({"detail": "Admins only."}, status=403)

    api_key = getattr(settings, "GOOGLE_CALENDAR_API_KEY", "")
    if not api_key:
        return Response({"detail": "Google API key is not configured."}, status=500)

    try:
        year = int(request.data.get("year") or datetime.now().year)
    except (TypeError, ValueError):
        return Response({"detail": "Invalid year."}, status=400)

    time_min = f"{year}-01-01T00:00:00Z"
    time_max = f"{year}-12-31T23:59:59Z"

    calendar_id = urllib.parse.quote(INDIA_HOLIDAY_CALENDAR_ID)
    params = urllib.parse.urlencode({
        "key": api_key,
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
    })
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return Response(
            {"detail": f"Google API error ({e.code}). Check the key and that Calendar API is enabled.",
             "google_response": body[:400]},
            status=502,
        )
    except Exception as e:
        return Response({"detail": f"Could not reach Google: {e}"}, status=502)

    items = data.get("items", [])

    CalendarEvent.objects.filter(
        source="google",
        event_type="holiday",
        start_date__year=year,
    ).delete()

    created = 0
    for item in items:
        title = (item.get("summary") or "").strip()
        start = item.get("start", {}).get("date")
        if not title or not start:
            continue
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
        except ValueError:
            continue

        CalendarEvent.objects.create(
            title=title,
            event_type="holiday",
            audience="everyone",
            source="google",
            start_date=start_date,
            description=(item.get("description", "") or "")[:500],
            created_by=request.user,
        )
        created += 1

    return Response({
        "detail": f"Synced {created} holidays for {year}.",
        "year": year,
        "created": created,
    })