# backend/teachingplan/views.py
import json
import logging
import re
from django.conf import settings
from datetime import date, datetime, timedelta
from django.apps import apps
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.academics.holidays import holiday_dates, holiday_map

from .models import TeachingPlan, DEPARTMENT_MODEL
from .serializers import (
    TeachingPlanWriteSerializer,
    TeachingPlanReadSerializer,
    CourseOutcomeSerializer,
)
from config.module_registry import optional_model

# Several blocks below deliberately keep working when something inside them
# fails, because a half-built dropdown is better than a 500. That is a
# reasonable trade only while the failure is VISIBLE: swallowing it silently
# meant an empty response looked identical to a genuinely empty result, and
# the frontend quietly substituted demo data for it.
logger = logging.getLogger(__name__)


def hod_departments(user):
    """Departments where this user is the HOD right now (#50 ACTING HOD aware)."""
    from core.users.acting_hod import hod_departments as _hod_departments
    return _hod_departments(user)


def notify(user, title, message):
    """Best-effort notification using your courses.Notification model."""
    try:
        Notification = apps.get_model("notifications", "Notification")
        Notification.objects.create(
            recipient=user, title=title, message=message,
            notification_type="teachingplan",  # FIX #23
        )
    except Exception:
        # A failed notification must not break the approval that triggered it,
        # but it should not vanish either.
        logger.exception(
            "teachingplan.notify failed for user %s", getattr(user, "id", None)
        )


def year_label(year):
    """A human class label from a Year row: 'B.E EEE - Year 1' style.
    This project has no Section model; the class is identified by course + year.

    MUST stay byte-identical to teachingplan/serializers.year_label(). Plans are
    matched to students by comparing TeachingPlan.class_section against labels
    built here, so any drift between the two silently hides plans from students.
    """
    if not year:
        return ""
    try:
        return f"{year.course.name} - Year {year.year_number}"
    except Exception:
        return str(year)


def timetable_sessions(teacher, subject_id):
    """Every class session of this teacher's subject in the active semester, in order,
    plus holidays that fall on a class day. Returns (allotted_hours, days).
    Used by class_days and by Part B's "carry the topic forward"."""
    TA = apps.get_model("courses", "TeachingAssignment")
    TimetableEntry = optional_model("timetable", "timetable", "TimetableEntry")  # empty if timetable is off
    Semester = optional_model("timetable", "timetable", "Semester")  # empty if timetable is off

    assignment = TA.objects.filter(teacher=teacher, subject_id=subject_id).first()
    if not assignment:
        return 0, []

    entries = (TimetableEntry.objects
               .filter(assignment=assignment, time_slot__is_break=False)
               .select_related("time_slot"))

    # group this subject's periods by weekday - keep EACH period separate
    day_slots = {}
    for e in entries:
        day_slots.setdefault(e.day_of_week, []).append(e.time_slot)
    if not day_slots:
        return 0, []

    def fmt_time(t):
        h = t.hour % 12 or 12
        ampm = "am" if t.hour < 12 else "pm"
        return f"{h}:{t.minute:02d} {ampm}" if t.minute else f"{h} {ampm}"

    def dur_hours(slot):
        secs = (datetime.combine(date.min, slot.end_time)
                - datetime.combine(date.min, slot.start_time)).seconds
        return round(secs / 3600) or 1

    # for each weekday, keep the list of individual periods (sorted)
    day_periods = {}
    for wd, slots in day_slots.items():
        day_periods[wd] = sorted(slots, key=lambda s: s.period_no)

    sem = Semester.objects.filter(is_active=True).order_by("-start_date").first()

    holidays = holiday_map()
    WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    days, allotted = [], 0
    if sem:
        d, guard = sem.start_date, 0
        while d <= sem.end_date and guard < 1000:
            guard += 1
            wd = d.weekday()
            if wd in day_periods:
                if d in holidays:
                    # one greyed holiday row for the whole day is enough
                    days.append({"date": d.isoformat(), "weekday": WEEKDAYS[wd],
                                 "holiday": True, "holiday_name": holidays[d]})
                else:
                    # ONE ROW PER PERIOD - teacher can type a different topic in each
                    for slot in day_periods[wd]:
                        h = dur_hours(slot)
                        allotted += h
                        days.append({
                            "date": d.isoformat(),
                            "weekday": WEEKDAYS[wd],
                            "hours": h,
                            "period_no": slot.period_no,                  # stored on the unit
                            "period_label": f"Period {slot.period_no}",   # display only
                            "time_label": f"{fmt_time(slot.start_time)}-{fmt_time(slot.end_time)}",
                        })
            d += timedelta(days=1)
    return allotted, days


# ============================================================
# COURSE PLAN (Part B): who may see / record delivery, who may edit outcomes
# ============================================================
def is_plan_hod(user, plan):
    depts = hod_departments(user)
    return bool((plan.department_id and depts.filter(id=plan.department_id).exists())
                or (plan.department_id is None and depts.exists()))


def can_view_delivery(user, plan):
    from core.permissions import is_college_admin
    return plan.teacher_id == user.id or is_college_admin(user) or is_plan_hod(user, plan)


def can_edit_outcomes(user, subject_id):
    """The subject's teachers, the HOD of a department that teaches it, or an admin."""
    from core.permissions import is_college_admin
    if is_college_admin(user):
        return True
    TA = apps.get_model("courses", "TeachingAssignment")
    tas = TA.objects.filter(subject_id=subject_id)
    if tas.filter(teacher=user).exists():
        return True
    depts = hod_departments(user)
    return depts.exists() and tas.filter(teacher__department__in=depts).exists()


def attendance_by_session(plan, start, end):
    """{(date, period): (present, total)} from the attendance register for this plan's class."""
    from django.db.models import Count, Q
    Attendance = optional_model("attendance", "attendance", "Attendance")
    TA = apps.get_model("courses", "TeachingAssignment")
    tas = [a.id for a in TA.objects.filter(teacher=plan.teacher, subject=plan.subject)
           .select_related("year", "year__course") if year_label(a.year) == plan.class_section]
    if not tas or start is None:
        return {}
    rows = (Attendance.objects.filter(teaching_assignment_id__in=tas, date__gte=start, date__lte=end)
            .values("date", "hour")
            .annotate(total=Count("id"), present=Count("id", filter=Q(status__in=["present", "duty_leave"]))))
    return {(r["date"], r["hour"]): (r["present"], r["total"]) for r in rows}


def delivery_report(plan, user, today=None):
    """Planned vs delivered for one plan: sessions up to today, counts, unit progress."""
    from .models import DELIVERY_STATUSES, HELD_STATUSES
    today = today or date.today()
    units = list(plan.units.all().prefetch_related("outcomes"))
    recs = {(d.date, d.period_no): d for d in plan.deliveries.all()}
    past = [u for u in units if u.complete_by and u.complete_by <= today]
    keys = {(u.complete_by, u.period_no) for u in past}
    # a record whose session later left the plan is still shown
    stray = [k for k in recs if k not in keys and k[0] <= today]
    first = min([u.complete_by for u in past] + [k[0] for k in stray], default=None)
    att = attendance_by_session(plan, first, today)
    label = dict(DELIVERY_STATUSES)

    def pack(d, period, topic, unit_no, codes):
        r = recs.get((d, period))
        a = att.get((d, period))
        return {
            "date": d.isoformat(), "period_no": period, "topic": topic, "unit_no": unit_no,
            "outcome_codes": codes, "today": d == today,
            "delivery": None if not r else {
                "status": r.status, "status_label": label.get(r.status, r.status), "covered": r.covered,
                "remarks": r.remarks, "carried_to": r.carried_to.isoformat() if r.carried_to else None},
            "attendance": None if not a else {"present": a[0], "total": a[1]},
        }

    sessions = [pack(u.complete_by, u.period_no, u.topic, u.unit_no, [o.code for o in u.outcomes.all()])
                for u in past]
    sessions += [pack(k[0], k[1], "", None, []) for k in stray]
    sessions.sort(key=lambda x: (x["date"], x["period_no"] or 0))

    statuses = [x["delivery"]["status"] if x["delivery"] else None for x in sessions]
    counts = {
        "past_sessions": len(sessions),
        "held": sum(1 for st in statuses if st in HELD_STATUSES),
        "as_planned": statuses.count("as_planned"),
        "changed": statuses.count("partly") + statuses.count("different"),
        "not_held": statuses.count("not_held"),
        "not_recorded": sum(1 for x in sessions if not x["delivery"] and x["date"] < today.isoformat()),
    }
    progress = {}
    for u in units:
        if not u.unit_no:
            continue
        p = progress.setdefault(u.unit_no, {"unit_no": u.unit_no, "planned": 0, "done": 0})
        p["planned"] += 1
        r = recs.get((u.complete_by, u.period_no))
        if r and r.status in ("as_planned", "partly"):
            p["done"] += 1
    return {
        "plan": plan.id, "today": today.isoformat(),
        "can_record": plan.teacher_id == user.id,
        "statuses": [{"value": v, "label": lbl} for v, lbl in DELIVERY_STATUSES],
        "counts": counts,
        "units": [progress[k] for k in sorted(progress)],
        "sessions": sessions,
    }


class TeachingPlanViewSet(viewsets.ModelViewSet):
    """
    Routes (registered under /api/teaching-plans/):
      GET    /teaching-plans/options/          -> subjects/classes/semesters for the teacher
      GET    /teaching-plans/subject_status/   -> teacher's subjects, each with its plan status
      GET    /teaching-plans/class_days/       -> ordered class days for one subject
      GET    /teaching-plans/my_timetable/     -> teacher's weekly grid (View timetable popup)
      GET    /teaching-plans/field_options/    -> units, teaching modes, methods, activities (course plan)
      GET    /teaching-plans/<id>/delivery/    -> planned vs delivered (teacher, HOD, admin)
      POST   /teaching-plans/<id>/delivery/    -> record one session  (the plan's teacher)
      GET    /teaching-plans/copy_sources/     -> plans of the same subject this teacher may copy
      POST   /teaching-plans/copy/             -> copy one into my plan  {subject, source, replace}
      GET    /teaching-plans/my/               -> the teacher's own plans
      POST   /teaching-plans/                  -> create (draft or submitted)
      POST   /teaching-plans/suggest_topics/   -> AI-generated topics for the day-by-day plan
      GET    /teaching-plans/department/       -> all plans in the HOD's department
      GET    /teaching-plans/student/          -> approved plans for the student's class
      GET    /teaching-plans/student_topic/    -> topic for one date + period (timetable click)
      GET    /teaching-plans/<id>/             -> one plan (detail)
      POST   /teaching-plans/<id>/approve/     -> approve  { comment? }
      POST   /teaching-plans/<id>/reject/      -> reject   { comment }  (comment required)
    """
    permission_classes = [IsAuthenticated]
    queryset = TeachingPlan.objects.all().prefetch_related("units")

    # PHASE 5 PART 3: the plain list / detail show only what this user may see.
    # (Screens use my/, student/ and department/, which keep their own rules.)
    def get_queryset(self):
        qs = super().get_queryset()
        if self.action not in ("list", "retrieve"):
            return qs
        from core.permissions import is_college_admin
        from django.db.models import Q
        user = self.request.user
        if is_college_admin(user):
            return qs
        if user.role == "teacher":
            depts = list(hod_departments(user).values_list("id", flat=True))
            return qs.filter(Q(teacher=user) | Q(department_id__in=depts))
        return qs.none()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return TeachingPlanWriteSerializer
        return TeachingPlanReadSerializer

    # PHASE 5: only a teacher writes a plan, and only their OWN plan may be
    # edited or deleted (an admin may too). HODs act through approve / reject.
    def perform_create(self, serializer):
        from core.permissions import is_college_admin
        if self.request.user.role != "teacher" and not is_college_admin(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only a teacher can write a teaching plan.")
        serializer.save()

    def _require_owner(self, plan):
        from core.permissions import is_college_admin
        user = self.request.user
        if plan.teacher_id != user.id and not is_college_admin(user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only change your own teaching plan.")

    def perform_update(self, serializer):
        self._require_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_owner(instance)
        instance.delete()

    # ---------- TEACHER: dropdown options ----------
    @action(detail=False, methods=["get"])
    def options(self, request):
        """
        Returns the subjects this teacher is assigned to, plus the class labels
        and semesters, derived from TeachingAssignment (course + year + subject).
        This project has no Section model; classes come from the assignment's year.
        """
        subjects, classes, semesters = [], [], []
        try:
            TA = apps.get_model("courses", "TeachingAssignment")
            assignments = (TA.objects.filter(teacher=request.user)
                           .select_related("subject", "year", "year__course", "course"))
            seen_subj, seen_cls, seen_sem = set(), set(), set()
            for a in assignments:
                subj = a.subject
                if subj.id not in seen_subj:
                    seen_subj.add(subj.id)
                    label = f"{subj.name} - {subj.code}" if subj.code else subj.name
                    subjects.append({"id": subj.id, "label": label})
                    sem_lbl = f"Semester {subj.semester}"
                    if sem_lbl not in seen_sem:
                        seen_sem.add(sem_lbl); semesters.append(sem_lbl)
                # class label = course + year (no sections in this project)
                cls = year_label(a.year)
                if cls and cls not in seen_cls:
                    seen_cls.add(cls); classes.append(cls)
        except Exception:
            # An empty response here makes the frontend fall back to DEMO
            # options, so the teacher picks from data that is not theirs and
            # has no way to tell. Whatever was built before the failure is
            # still returned, but the failure itself is now on the record.
            logger.exception(
                "teachingplan options build failed for user %s", request.user.id
            )

        return Response({
            "subjects": subjects,
            "classes": classes,
            "semesters": semesters,
        })

    # ---------- TEACHER: my subjects + each one's plan status (for the overview panel) ----------
    @action(detail=False, methods=["get"])
    def subject_status(self, request):
        """
        GET /teaching-plans/subject_status/
        Returns the teacher's subjects, each with its current plan status
        (not_started / draft / submitted / approved / rejected), a class label,
        and hour progress. Powers the "My subjects" panel at the top of the page.

        class_label is authoritative: the teacher's form shows it read-only and
        sends it back as class_section, and the serializer re-derives it anyway.
        Response: { "subjects": [
            {subject_id, subject, label, class_label, semester_label,
             status, planned_hours, allotted_hours}
        ] }
        """
        out = []
        try:
            TA = apps.get_model("courses", "TeachingAssignment")

            assignments = (TA.objects.filter(teacher=request.user)
                           .select_related("subject", "year", "year__course", "course"))

            # existing plans for this teacher, keyed by subject id.
            # If duplicates exist, keep the MOST RECENT one (latest created overwrites).
            plans = {}
            for p in (TeachingPlan.objects.filter(teacher=request.user)
                      .order_by("created_at").prefetch_related("units")):
                plans[p.subject_id] = p

            seen = set()
            for a in assignments:
                subj = a.subject
                if subj.id in seen:
                    continue
                seen.add(subj.id)

                class_label = year_label(a.year)
                label = f"{subj.name} - {subj.code}" if getattr(subj, "code", "") else subj.name
                semester_label = f"Semester {subj.semester}"

                plan = plans.get(subj.id)
                if plan:
                    status_val = plan.status
                    planned = sum(u.hours for u in plan.units.all())
                    allotted = plan.allotted_hours or 0
                else:
                    status_val = "not_started"
                    planned = 0
                    allotted = 0

                out.append({
                    "subject_id": subj.id,
                    "subject": subj.name,
                    "label": label,
                    "class_label": class_label,
                    "semester_label": semester_label,
                    "status": status_val,
                    "planned_hours": planned,
                    "allotted_hours": allotted,
                })
        except Exception:
            # Returns a PARTIAL list - whatever was built before the failure.
            # A subject missing from it looks to the teacher exactly like one
            # they were never assigned, which is why this cannot stay silent.
            logger.exception(
                "teachingplan subject_status failed for user %s (returning %d of an "
                "unknown total)", request.user.id, len(out)
            )

        return Response({"subjects": out})

    # ---------- TEACHER: auto-fill "complete by" dates from the timetable ----------
    @action(detail=False, methods=["post"])
    def auto_dates(self, request):
        """
        Body: { "subject": <subject_id>, "hours": [6, 8, 10], "start": "2026-07-01"? }
        Walks this subject's weekly timetable slots, skipping holidays, and returns
        the finish date for each topic in order (each topic starts the day after the
        previous one ends).
        Response: { "dates": ["2026-07-10", "2026-07-22", ...] }
        """
        subject_id = request.data.get("subject")
        hours_list = request.data.get("hours", []) or []

        TA = apps.get_model("courses", "TeachingAssignment")
        TimetableEntry = optional_model("timetable", "timetable", "TimetableEntry")  # empty if timetable is off
        Semester = optional_model("timetable", "timetable", "Semester")  # empty if timetable is off

        # the teacher's assignment for this subject (carries course/year/subject)
        assignment = TA.objects.filter(teacher=request.user, subject_id=subject_id).first()
        if not assignment:
            return Response({"allotted": 0, "dates": [], "detail": "No timetable assignment for this subject."})

        # weekly meeting pattern -> { weekday: teaching_hours_that_day }
        entries = (TimetableEntry.objects
                   .filter(assignment=assignment, time_slot__is_break=False)
                   .select_related("time_slot"))
        day_hours = {}
        for e in entries:
            ts = e.time_slot
            secs = (datetime.combine(date.min, ts.end_time)
                    - datetime.combine(date.min, ts.start_time)).seconds
            dur = round(secs / 3600) or 1     # period length in hours (defaults to 1)
            day_hours[e.day_of_week] = day_hours.get(e.day_of_week, 0) + dur
        if not day_hours:
            return Response({"allotted": 0, "dates": [], "detail": "No timetable periods for this subject yet."})

        periods_per_week = sum(day_hours.values())   # total class hours this subject meets per week

        # the active semester defines the term window (start .. end)
        sem = Semester.objects.filter(is_active=True).order_by("-start_date").first()
        holidays = holiday_dates()

        # ----- ALLOTTED HOURS: every class hour available across the whole semester -----
        allotted = 0
        if sem:
            d, guard = sem.start_date, 0
            while d <= sem.end_date and guard < 1000:
                guard += 1
                if d.weekday() in day_hours and d not in holidays:
                    allotted += day_hours[d.weekday()]
                d += timedelta(days=1)

        # ----- per-topic "complete by" dates (chained, holidays skipped) -----
        start_str = request.data.get("start")
        if start_str:
            cursor = parse_date(start_str)
        else:
            cursor = sem.start_date if sem else date.today()

        dates = []
        for h in hours_list:
            needed = float(h or 0)
            if needed <= 0:
                dates.append(None)
                continue
            acc, finish, guard = 0, cursor, 0
            while guard < 800:                     # safety stop (~2 years of days)
                guard += 1
                wd = cursor.weekday()              # Mon=0 .. Sun=6 (matches your day_of_week)
                if wd in day_hours and cursor not in holidays:
                    acc += day_hours[wd]
                    if acc >= needed:
                        finish = cursor
                        break
                cursor += timedelta(days=1)
            dates.append(finish.isoformat())
            cursor = finish + timedelta(days=1)    # next topic starts the day after

        return Response({
            "allotted": allotted,
            "periods_per_week": periods_per_week,
            "dates": dates,
        })

    # ---------- TEACHER: ordered list of class days (for the day-by-day form) ----------
    @action(detail=False, methods=["get"])
    def class_days(self, request):
        """
        GET /teaching-plans/class_days/?subject=<id>
        Returns every class day for this subject across the active semester, in order.
        Each class day carries its date, weekday, hours, period number and time label.
        Holidays that fall on a would-be class day are returned too, marked skipped.
        Response: { "allotted": 46, "days": [
            {date, weekday, hours, period_no, period_label, time_label},   # a class day
            {date, weekday, holiday: true, holiday_name},                  # a skipped holiday
        ] }
        """
        subject_id = request.query_params.get("subject")
        allotted, days = timetable_sessions(request.user, subject_id)
        return Response({"allotted": allotted, "days": days})

    # ---------- TEACHER: my assigned weekly timetable (for the View timetable popup) ----------
    @action(detail=False, methods=["get"])
    def my_timetable(self, request):
        """
        GET /teaching-plans/my_timetable/
        Returns this teacher's weekly grid: one row per period (by period number),
        each with a cell per weekday holding the assigned subject name (or null = free).
        Response: { "weekdays": [...], "rows": [ {label, is_break, cells:[...6]} ] }
        """
        TimetableEntry = optional_model("timetable", "timetable", "TimetableEntry")  # empty if timetable is off
        TimeSlot = optional_model("timetable", "timetable", "TimeSlot")  # empty if timetable is off

        slots = list(TimeSlot.objects.all().order_by("start_time", "period_no"))
        entries = (TimetableEntry.objects
                   .filter(assignment__teacher=request.user)
                   .select_related("assignment", "assignment__subject", "time_slot"))

        cell = {}  # (weekday, slot_id) -> {name, subject_id}
        for e in entries:
            subj = getattr(e.assignment, "subject", None) if e.assignment_id else None
            cell[(e.day_of_week, e.time_slot_id)] = {
                "name": getattr(subj, "name", "") if subj else "",
                "subject_id": getattr(subj, "id", None) if subj else None,
            }

        ORD = {1: "1st", 2: "2nd", 3: "3rd"}
        ordinal = lambda n: ORD.get(n, f"{n}th")

        rows = []
        for s in slots:
            if getattr(s, "is_break", False):
                rows.append({"label": s.label or "Break", "is_break": True, "cells": []})
                continue
            cells = [cell.get((d, s.id)) for d in range(6)]  # Mon..Sat, dict or None
            rows.append({"label": s.label or ordinal(s.period_no), "is_break": False, "cells": cells})

        return Response({"weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], "rows": rows})

    # ---------- COURSE PLAN: the choices for each session's columns ----------
    @action(detail=False, methods=["get"])
    def field_options(self, request):
        """GET /teaching-plans/field_options/ - one source for the dropdown lists."""
        from .models import BEYOND_ACTIVITIES, CLASS_ACTIVITIES, MAX_UNITS, TEACHING_METHODS, TEACHING_MODES

        def pack(pairs):
            return [{"value": v, "label": label} for v, label in pairs]
        return Response({
            "units": list(range(1, MAX_UNITS + 1)),
            "default_units": 5,                      # Anna University syllabi have 5 units
            "modes": pack(TEACHING_MODES),
            "methods": pack(TEACHING_METHODS),
            "class_activities": pack(CLASS_ACTIVITIES),
            "beyond_activities": pack(BEYOND_ACTIVITIES),
        })

    # ---------- TEACHER: my plans ----------
    # ---------- COURSE PLAN (Part B): planned vs delivered ----------
    @action(detail=True, methods=["get", "post"])
    def delivery(self, request, pk=None):
        """
        GET  /teaching-plans/<id>/delivery/   -> sessions up to today, counts, unit progress
        POST /teaching-plans/<id>/delivery/   {date, period_no, status, covered?, remarks?, carry_forward?}
             The plan's own teacher records what happened in one planned session.
             carry_forward puts an unfinished topic on the next free timetable session.
        """
        from .models import DELIVERY_STATUSES, PlanUnit, SessionDelivery
        plan = self.get_object()
        if not can_view_delivery(request.user, plan):
            return Response({"detail": "You can't see this plan."}, status=403)
        if request.method == "GET":
            return Response(delivery_report(plan, request.user))

        if plan.teacher_id != request.user.id:
            return Response({"detail": "Only the teacher of this plan records what was delivered."}, status=403)
        d = parse_date(str(request.data.get("date") or ""))
        period = request.data.get("period_no")
        period = int(period) if str(period or "").isdigit() else None
        st = request.data.get("status")
        covered = (request.data.get("covered") or "").strip()[:200]
        remarks = (request.data.get("remarks") or "").strip()
        if d is None:
            return Response({"detail": "Choose the session's date."}, status=400)
        if d > date.today():
            return Response({"detail": "A class can be recorded only on or after its day."}, status=400)
        if st not in dict(DELIVERY_STATUSES):
            return Response({"detail": "Choose what happened in the class."}, status=400)
        unit = plan.units.filter(complete_by=d, period_no=period).first()
        if unit is None:
            return Response({"detail": "This session is not in the plan."}, status=400)
        if st == "as_planned":
            covered = unit.topic
        elif st == "not_held":
            covered = ""
            if not remarks:
                return Response({"detail": "Give the reason the class was not held."}, status=400)
        elif not covered:
            return Response({"detail": "Write what was actually covered."}, status=400)

        rec = SessionDelivery.objects.filter(plan=plan, date=d, period_no=period).first()
        carried_to = rec.carried_to if rec else None
        message = "Saved."
        want_carry = str(request.data.get("carry_forward")).lower() in ("1", "true", "yes")
        if want_carry and st != "as_planned" and carried_to is None:
            _, days = timetable_sessions(plan.teacher, plan.subject_id)
            taken = set(plan.units.values_list("complete_by", "period_no"))
            free = next((x for x in days if not x.get("holiday")
                         and (parse_date(x["date"]), x["period_no"]) not in taken
                         and (parse_date(x["date"]), x["period_no"]) > (d, period or 0)), None)
            if free is None:
                message = "Saved. There is no free session left after this one, so add the topic to the plan yourself."
            else:
                when = parse_date(free["date"])
                topic = f"{unit.topic} (continued)" if st == "partly" else unit.topic
                last = plan.units.order_by("-sequence_no").first()
                moved = PlanUnit.objects.create(
                    plan=plan, topic=topic[:200], hours=free.get("hours") or unit.hours or 1,
                    complete_by=when, period_no=free["period_no"],
                    sequence_no=(last.sequence_no if last else 0) + 1,
                    unit_no=unit.unit_no, mode=unit.mode, method=unit.method,
                    notes=f"Carried from {d:%d-%m-%Y}")
                moved.outcomes.set(unit.outcomes.all())
                carried_to = when
                message = f"Saved. The topic is now planned for {when:%d-%m-%Y}, period {free['period_no']}."

        SessionDelivery.objects.update_or_create(
            plan=plan, date=d, period_no=period,
            defaults={"status": st, "covered": covered, "remarks": remarks,
                      "carried_to": carried_to, "recorded_by": request.user})
        # keep the older progress fields in step
        held = st in ("as_planned", "partly", "different")
        unit.is_completed = held
        unit.actual_completed_date = d if held else None
        unit.save(update_fields=["is_completed", "actual_completed_date"])
        data = delivery_report(plan, request.user)
        data["message"] = message
        return Response(data)

    # ---------- COURSE PLAN (Part C): copy another plan of the same subject ----------
    def _copy_target(self, request, subject_id):
        """(subject, target plan or None, error Response or None) for the copy actions."""
        from .importers import find_plan
        TA = apps.get_model("courses", "TeachingAssignment")
        Subject = apps.get_model("courses", "Subject")
        subject = Subject.objects.filter(id=subject_id).first() if str(subject_id or "").isdigit() else None
        if subject is None:
            return None, None, Response({"detail": "Choose a subject first."}, status=400)
        if not TA.objects.filter(teacher=request.user, subject=subject).exists():
            return None, None, Response({"detail": "This isn't your subject."}, status=403)
        return subject, find_plan(request.user, subject), None

    def _copyable(self, request, subject, target):
        """My other plans of this subject, and other teachers' APPROVED plans of it."""
        from django.db.models import Count, Q
        qs = (TeachingPlan.objects.filter(subject=subject)
              .filter(Q(teacher=request.user) | Q(status="approved"))
              .annotate(n=Count("units")).filter(n__gt=0).select_related("teacher"))
        if target is not None:
            qs = qs.exclude(id=target.id)
        return qs

    @action(detail=False, methods=["get"])
    def copy_sources(self, request):
        """GET /teaching-plans/copy_sources/?subject=<id> -> plans this teacher may copy from."""
        from .serializers import _teacher_name
        subject, target, err = self._copy_target(request, request.query_params.get("subject"))
        if err:
            return err
        rows = [{
            "id": p.id, "mine": p.teacher_id == request.user.id, "teacher": _teacher_name(p.teacher),
            "cls": p.class_section, "sem": p.semester, "status": p.get_status_display(),
            "sessions": p.n, "updated": p.updated_at.date().isoformat(),
        } for p in self._copyable(request, subject, target)]
        rows.sort(key=lambda r: (not r["mine"], r["teacher"], r["cls"]))
        return Response({"sources": rows,
                         "locked": bool(target and target.status in ("submitted", "approved"))})

    @action(detail=False, methods=["post"])
    def copy(self, request):
        """
        POST /teaching-plans/copy/ {subject, source, replace}
        Topics, units, modes, methods, activities and outcomes of the source plan
        fill THIS semester's timetable sessions in order (dates come from the
        timetable, never from the source). replace=false keeps every session
        already planned. What was delivered is never copied.
        """
        from django.db import transaction
        from .importers import create_plan
        from .models import PlanUnit
        subject, target, err = self._copy_target(request, request.data.get("subject"))
        if err:
            return err
        if target is not None and target.status in ("submitted", "approved"):
            return Response({"detail": "This plan is with the HOD or approved, so it can't be replaced."},
                            status=400)
        source = self._copyable(request, subject, target).filter(id=request.data.get("source")).first() \
            if str(request.data.get("source") or "").isdigit() else None
        if source is None:
            return Response({"detail": "Choose a plan to copy from."}, status=400)
        replace = str(request.data.get("replace")).lower() in ("1", "true", "yes")
        _, days = timetable_sessions(request.user, subject.id)
        sessions = [d for d in days if not d.get("holiday")]
        if not sessions:
            return Response({"detail": "Your timetable has no sessions for this subject yet."}, status=400)
        src = list(source.units.all().order_by("complete_by", "period_no", "sequence_no").prefetch_related("outcomes"))
        copied = kept = 0
        with transaction.atomic():
            plan = target or create_plan(request.user, subject)
            if replace:
                plan.units.all().delete()
            taken = set(plan.units.values_list("complete_by", "period_no"))
            for i, (d, u) in enumerate(zip(sessions, src)):
                when = parse_date(d["date"])
                if (when, d["period_no"]) in taken:
                    kept += 1
                    continue
                new = PlanUnit.objects.create(
                    plan=plan, topic=u.topic, hours=d.get("hours") or 1, complete_by=when,
                    period_no=d["period_no"], sequence_no=i + 1, unit_no=u.unit_no, notes=u.notes,
                    mode=u.mode, method=u.method, class_activity=u.class_activity,
                    beyond_activity=u.beyond_activity)
                new.outcomes.set(u.outcomes.all())
                copied += 1
        extra = max(0, len(src) - len(sessions))
        planned_now = set(plan.units.values_list("complete_by", "period_no"))
        empty = sum(1 for d in sessions if (parse_date(d["date"]), d["period_no"]) not in planned_now)
        parts = [f"Copied {copied} session{'s' if copied != 1 else ''}."]
        if kept:
            parts.append(f"{kept} already planned kept.")
        if extra:
            parts.append(f"{extra} topic{'s' if extra != 1 else ''} did not fit this semester's timetable.")
        if empty > 0:
            parts.append(f"{empty} session{'s' if empty != 1 else ''} still not planned.")
        parts.append("Review and save the draft.")
        return Response({"plan": plan.id, "copied": copied, "kept": kept, "extra": extra,
                         "unplanned": max(0, empty), "message": " ".join(parts)})

    @action(detail=False, methods=["get"])
    def my(self, request):
        qs = self.get_queryset().filter(teacher=request.user)
        return Response(TeachingPlanReadSerializer(qs, many=True).data)

    # ---------- TEACHER: AI-suggested topics for the day-by-day plan ----------
    @action(detail=False, methods=["post"])
    def suggest_topics(self, request):
        """
        POST /teaching-plans/suggest_topics/
        Body: { "subject": <id>, "count": <class days>, "syllabus": "<optional text>" }

        Asks Gemini for one topic per class day, in teaching order. If a syllabus
        is supplied, the topics are mapped onto it; otherwise they're generated
        from the subject name alone.
        Returns: { "topics": ["...", ...] }

        PRIVACY: only the subject name, a count, and the syllabus the teacher
        pasted are sent to Google. No student data, no names, no marks.
        """
        subject_id = request.data.get("subject")
        syllabus = (request.data.get("syllabus") or "").strip()
        try:
            count = int(request.data.get("count") or 0)
        except (TypeError, ValueError):
            count = 0

        if not subject_id or count < 1:
            return Response(
                {"detail": "subject and count are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # FIX #12: was min(count, 60), so a subject with 78 class days got 18
        # empty rows. 200 covers any real semester; the AI is asked in batches
        # (below) so one long answer never gets cut off.
        count = min(count, 200)
        syllabus = syllabus[:6000]      # keep the prompt (and the token bill) bounded

        # the teacher must actually be assigned to this subject
        TA = apps.get_model("courses", "TeachingAssignment")
        assignment = (TA.objects
                      .filter(teacher=request.user, subject_id=subject_id)
                      .select_related("subject", "year", "year__course")
                      .first())
        if not assignment:
            return Response(
                {"detail": "You are not assigned to this subject."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subject_name = assignment.subject.name
        course_name = ""
        year_number = ""
        try:
            course_name = assignment.year.course.name
            year_number = assignment.year.year_number
        except Exception:
            # Only affects the prompt's context line; the request still works
            # with blanks. Logged at warning rather than exception because the
            # traceback is not worth the noise for a cosmetic fallback.
            logger.warning(
                "teachingplan: could not read course/year for assignment %s",
                assignment.id,
            )

        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return Response(
                {"detail": "AI is not configured. Add GEMINI_API_KEY to the .env file."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-flash-lite-latest")
        except Exception as e:
            logger.exception("teachingplan: Gemini setup failed for subject %s", subject_id)
            return Response(
                {"detail": f"Could not reach the AI service: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # FIX #12: ask in batches of BATCH hours. Each batch knows where it sits
        # in the whole semester and what the previous batch ended with, so the
        # topics continue in order instead of starting again from Unit 1.
        BATCH = 40
        topics = []
        for start in range(0, count, BATCH):
            n = min(BATCH, count - start)
            first, last = start + 1, start + n
            previous = topics[-5:]
            prev_txt = (
                "The previous class hours ended with these topics:\n"
                + "\n".join(f"- {t}" for t in previous if t) + "\n\n"
            ) if any(previous) else ""

            if syllabus:
                source = (
                    f'Here is the official syllabus for this subject:\n'
                    f'"""\n{syllabus}\n"""\n\n'
                    f'The whole syllabus is spread across {count} class hours, in teaching order. '
                    f'Cover every unit across the {count} hours and give more hours to the larger '
                    f'units. Do not invent topics that are not in the syllabus.\n\n'
                )
            else:
                source = (
                    f'No syllabus was provided. Use the standard curriculum for this subject at an '
                    f'Indian engineering college, spread across {count} class hours in teaching '
                    f'order, starting with fundamentals and building up.\n\n'
                )

            if count > BATCH:
                part = (
                    f'This request is ONLY for class hours {first} to {last} of {count}. '
                    f'{prev_txt}'
                    f'Continue from there. '
                    + ("If these are the last hours, use some of them for revision and "
                       "previous-year question practice. " if last == count else "")
                    + "\n\n"
                )
            else:
                part = ""

            prompt = (
                f'You are helping an Indian engineering college lecturer plan their semester.\n\n'
                f'Subject: "{subject_name}"\n'
                f'Course: {course_name} (Year {year_number})\n'
                f'Total class hours in the semester: {count}\n\n'
                f'{source}'
                f'{part}'
                f'Each topic must be a short phrase under 90 characters describing what is taught '
                f'in that one hour (for example: "Unit 1: Nouns and pronouns" or '
                f'"Practice: error correction drills").\n\n'
                f'Respond with ONLY a JSON array of exactly {n} strings. No markdown, no code '
                f'fences, no explanation. Example: ["Topic one", "Topic two"]'
            )

            try:
                result = model.generate_content(prompt)
                raw = (result.text or "").strip()
            except Exception as e:
                logger.exception("teachingplan: Gemini call failed for subject %s", subject_id)
                return Response(
                    {"detail": f"Could not reach the AI service: {e}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # the model sometimes wraps JSON in ```json fences despite being told not to
            cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            try:
                chunk = json.loads(cleaned)
            except json.JSONDecodeError:
                logger.warning(
                    "teachingplan: Gemini returned unparseable JSON for subject %s", subject_id
                )
                return Response(
                    {"detail": "The AI returned an unexpected format. Please try again."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            if not isinstance(chunk, list):
                logger.warning(
                    "teachingplan: Gemini returned %s, not a list, for subject %s",
                    type(chunk).__name__, subject_id,
                )
                return Response(
                    {"detail": "The AI returned an unexpected format. Please try again."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # strings only, trimmed, truncated to PlanUnit.topic's max_length (200)
            chunk = [str(t).strip()[:200] for t in chunk if str(t).strip()]
            chunk = chunk[:n]
            while len(chunk) < n:
                chunk.append("")
            topics.extend(chunk)

        return Response({"topics": topics})

    # ---------- HOD: department plans ----------
    @action(detail=False, methods=["get"])
    def department(self, request):
        depts = hod_departments(request.user)
        if not depts.exists():
            return Response([], status=200)  # not an HOD -> empty
        # Exclude drafts; the HOD only sees submitted/approved/rejected plans.
        qs = (self.get_queryset()
              .filter(department__in=depts)
              .exclude(status="draft"))
        return Response(TeachingPlanReadSerializer(qs, many=True).data)

    # ---------- HOD: approve ----------
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        plan = self.get_object()
        depts = hod_departments(request.user)
        allowed = (plan.department_id and depts.filter(id=plan.department_id).exists()) \
                  or (plan.department_id is None and depts.exists())
        if not allowed:
            return Response({"detail": "Only the department HOD can approve."}, status=403)
        # FIX #32: only a plan that is waiting for review can be decided, so a
        # double-click (or a second tab) cannot approve it twice
        if plan.status != "submitted":
            return Response({"detail": f"This plan is already {plan.get_status_display().lower()}."},
                            status=status.HTTP_400_BAD_REQUEST)
        plan.status = "approved"
        plan.hod_comment = (request.data.get("comment") or "").strip()
        plan.reviewed_by = request.user
        plan.reviewed_at = timezone.now()
        plan.save()
        notify(plan.teacher, "Teaching plan approved",
               f"Your plan for {plan.subject} ({plan.class_section}) was approved.")
        return Response(TeachingPlanReadSerializer(plan).data)

    # ---------- HOD: reject ----------
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        plan = self.get_object()
        depts = hod_departments(request.user)
        allowed = (plan.department_id and depts.filter(id=plan.department_id).exists()) \
                  or (plan.department_id is None and depts.exists())
        if not allowed:
            return Response({"detail": "Only the department HOD can reject."}, status=403)
        # FIX #32: same guard as approve
        if plan.status != "submitted":
            return Response({"detail": f"This plan is already {plan.get_status_display().lower()}."},
                            status=status.HTTP_400_BAD_REQUEST)
        comment = (request.data.get("comment") or "").strip()
        if not comment:
            return Response({"detail": "A comment is required when rejecting."},
                            status=status.HTTP_400_BAD_REQUEST)
        plan.status = "rejected"
        plan.hod_comment = comment
        plan.reviewed_by = request.user
        plan.reviewed_at = timezone.now()
        plan.save()
        notify(plan.teacher, "Teaching plan sent back",
               f"Your plan for {plan.subject} needs revision: {comment}")
        return Response(TeachingPlanReadSerializer(plan).data)

    # ---------- STUDENT: approved plans published to my class ----------
    @action(detail=False, methods=["get"])
    def student(self, request):
        """
        GET /teaching-plans/student/
        Returns ONLY approved plans for the class this student belongs to.
        Pending/draft/rejected plans are never returned to students.

        This project has no Section model; a student's class is derived from the
        subjects they're enrolled in (Enrollment -> TeachingAssignment -> year).
        """
        my_labels = set()
        try:
            Enrollment = apps.get_model("courses", "Enrollment")
            enrolls = (Enrollment.objects.filter(student=request.user)
                       .select_related("teaching_assignment__year__course"))
            for en in enrolls:
                lbl = year_label(en.teaching_assignment.year)
                if lbl:
                    my_labels.add(lbl)
        except Exception:
            # my_labels stays empty, and the fallback below then shows EVERY
            # approved plan in the college rather than this student's class.
            # That is a wrong answer dressed up as a working page, so the
            # failure has to be findable.
            logger.exception(
                "teachingplan: class labels failed for student %s - falling back to "
                "all approved plans", request.user.id
            )

        qs = self.get_queryset().filter(status="approved")
        # PHASE 5 PART 3: only this student's class. No class found (not enrolled
        # yet, or not a student) = nothing, never every plan in the college.
        qs = qs.filter(class_section__in=my_labels)

        return Response(TeachingPlanReadSerializer(qs, many=True).data)

    # ---------- STUDENT: what is being taught in this class? ----------
    @action(detail=False, methods=["get"])
    def student_topic(self, request):
        """
        GET /teaching-plans/student_topic/?date=2026-07-14&period=1

        The student clicks a cell in their weekly timetable. That cell knows its
        DATE (the grid is week-based) and its PERIOD. It does not need to tell us
        the subject -- we derive that from the student's own enrolments, so the
        browser cannot ask about a class it isn't in.

        Answers one of:
          found=True             -> topic for that exact class hour
          reason="no_class"      -> free period
          reason="no_plan"       -> teacher hasn't written a plan yet
          reason="not_approved"  -> plan exists but the HOD hasn't approved it
          reason="no_topic"      -> approved plan, but nothing planned for this hour
        """
        date_str = request.query_params.get("date")
        period_no = request.query_params.get("period")

        if not date_str or not period_no:
            return Response({"detail": "date and period are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        the_date = parse_date(date_str)
        if not the_date:
            return Response({"detail": "date must be YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            period_no = int(period_no)
        except (TypeError, ValueError):
            return Response({"detail": "period must be a number."},
                            status=status.HTTP_400_BAD_REQUEST)

        Enrollment = apps.get_model("courses", "Enrollment")
        TimetableEntry = optional_model("timetable", "timetable", "TimetableEntry")  # empty if timetable is off

        # the assignments this student is actually enrolled in
        enrolls = (Enrollment.objects.filter(student=request.user)
                   .select_related("teaching_assignment__year__course"))
        assignment_ids = [en.teaching_assignment_id for en in enrolls]
        my_labels = {year_label(en.teaching_assignment.year) for en in enrolls}
        my_labels.discard("")

        if not assignment_ids:
            return Response({"found": False, "reason": "no_class"})

        # which of the student's classes falls on this weekday, in this period?
        weekday = the_date.weekday()          # Mon=0 .. Sun=6, matches day_of_week
        entry = (TimetableEntry.objects
                 .filter(assignment_id__in=assignment_ids,
                         day_of_week=weekday,
                         time_slot__period_no=period_no,
                         time_slot__is_break=False)
                 .select_related("assignment__subject", "assignment__teacher")
                 .first())
        if not entry:
            return Response({"found": False, "reason": "no_class"})

        subject = entry.assignment.subject
        teacher = entry.assignment.teacher
        teacher_name = (teacher.get_full_name() or teacher.username) if teacher else ""

        base = {
            "subject": getattr(subject, "name", str(subject)),
            "teacher": teacher_name,
            "date": the_date.isoformat(),
            "period_no": period_no,
            "is_today": the_date == date.today(),
        }

        plans = TeachingPlan.objects.filter(subject=subject)
        if my_labels:
            plans = plans.filter(class_section__in=my_labels)

        approved = plans.filter(status="approved").first()
        if not approved:
            # distinguish "nothing written" from "written but not signed off"
            reason = "not_approved" if plans.exists() else "no_plan"
            return Response({**base, "found": False, "reason": reason})

        # the exact class hour: this date, this period. Both are stored on the unit.
        # This pair is why PlanUnit.period_no exists -- complete_by alone cannot
        # identify a class when a subject meets twice on the same day.
        unit = approved.units.filter(complete_by=the_date, period_no=period_no).first()
        if not unit or not (unit.topic or "").strip():
            return Response({**base, "found": False, "reason": "no_topic"})

        return Response({**base, "found": True, "topic": unit.topic})

# ============================================================
# COURSE PLAN (Part B): course outcomes of a subject
# ============================================================
class CourseOutcomeViewSet(viewsets.ModelViewSet):
    """
    GET    /course-outcomes/?subject=<id>  -> the subject's outcomes, with planned-session counts
    POST   /course-outcomes/               {subject, text, level}   (code CO1, CO2 ... is given)
    PATCH  /course-outcomes/<id>/          {text?, level?}
    DELETE /course-outcomes/<id>/          (its session links go with it)
    Read: staff. Write: the subject's teachers, its HOD, an admin.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CourseOutcomeSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        from .models import CourseOutcome
        from core.permissions import is_college_admin
        user = self.request.user
        if user.role != "teacher" and not is_college_admin(user):
            return CourseOutcome.objects.none()
        qs = CourseOutcome.objects.all()
        subject = self.request.query_params.get("subject")
        if self.action == "list":
            if not str(subject or "").isdigit():
                return qs.none()
            qs = qs.filter(subject_id=subject)
        return qs

    def list(self, request, *args, **kwargs):
        from django.db.models import Count
        # explicit order: Meta.ordering is ignored once Count() adds a GROUP BY
        qs = list(self.get_queryset().annotate(n=Count("sessions")).order_by("order", "id"))
        data = CourseOutcomeSerializer(qs, many=True).data
        for row, obj in zip(data, qs):
            row["sessions"] = obj.n                 # planned sessions, all plans of the subject
        subject = request.query_params.get("subject")
        from .models import BLOOM_LEVELS, LOW_COVERAGE, MAX_OUTCOMES
        return Response({
            "outcomes": data,
            "can_edit": bool(str(subject or "").isdigit() and can_edit_outcomes(request.user, subject)),
            "levels": [{"value": v, "label": lbl} for v, lbl in BLOOM_LEVELS],
            "low_coverage": LOW_COVERAGE, "max": MAX_OUTCOMES,
        })

    def _check(self, subject_id):
        if not can_edit_outcomes(self.request.user, subject_id):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only this subject's teachers, its HOD or an admin can change its outcomes.")

    def perform_create(self, serializer):
        self._check(serializer.validated_data["subject"].id)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        self._check(serializer.instance.subject_id)
        serializer.save()

    def perform_destroy(self, instance):
        self._check(instance.subject_id)
        instance.delete()
