"""
ATTENDANCE CORRECTION (#43 Change 2)

Meeting point 6: subject teachers can't change past attendance any more
(Change 1). The CLASS TUTOR corrects it here — any subject, own class only,
current semester only, with a reason. The main admin can too. Every
correction is saved in AttendanceCorrection and can't be edited or deleted.

    GET  /api/attendance-corrections/day/?course=&year=&date=   periods of the class that day
    POST /api/attendance-corrections/   {attendance, new_status, reason}
    GET  /api/attendance-corrections/?course=&year=              the correction log
    POST /api/attendance-corrections/late-entry/                 #46 Part 3: enter a missed period
"""
import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.academics.models import YearTutor
from .models import Attendance, AttendanceCorrection, ODRequest

User = get_user_model()

MIN_REASON = 10                     # characters — a real reason, not "ok"
TUTOR_STATUSES = ("present", "absent")   # On duty comes only from an approved OD
MAIN_ADMIN_SUB_ROLES = ("", "super_admin")
STATUS_LABEL = {"present": "Present", "absent": "Absent", "duty_leave": "On duty"}
NOT_MARKED = "not_marked"   # old_status in the log for a period entered late (#46 Part 3)


def _name(u):
    return ((u.get_full_name() or "").strip() or u.username) if u else None


def _is_main_admin(user):
    if getattr(user, "is_superuser", False):
        return True
    return (getattr(user, "role", None) == "admin"
            and (getattr(user, "sub_role", None) or "") in MAIN_ADMIN_SUB_ROLES)


def _is_tutor_of(user, course_id, year_number):
    if getattr(user, "role", None) != "teacher":
        return False
    return YearTutor.objects.filter(
        teacher=user, course_id=course_id, year__year_number=year_number
    ).exists()


def _class_access(user, course_id, year_number):
    """'admin', 'class_tutor' or None."""
    if _is_main_admin(user):
        return "admin"
    if _is_tutor_of(user, course_id, year_number):
        return "class_tutor"
    return None


def _od_approved(student_id, day):
    return ODRequest.objects.filter(
        student_id=student_id,
        status=ODRequest.Status.APPROVED,
        from_date__lte=day,
        to_date__gte=day,
    ).exists()


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def correction_day(request):
    """Every marked period of one class on one date, with each student's status."""
    course_id = _int(request.query_params.get("course"))
    year_number = _int(request.query_params.get("year"))
    try:
        day = datetime.date.fromisoformat(str(request.query_params.get("date"))[:10])
    except ValueError:
        return Response({"detail": "Pick a valid date."}, status=400)
    if not (course_id and year_number):
        return Response({"detail": "course and year are required."}, status=400)

    if not _class_access(request.user, course_id, year_number):
        return Response({"detail": "Only the class in-charge can correct this class's attendance."}, status=403)

    if day > timezone.localdate():
        return Response({"periods": []})

    records = (
        Attendance.objects
        .filter(
            teaching_assignment__course_id=course_id,
            teaching_assignment__year__year_number=year_number,
            date=day,
        )
        .select_related("student", "teaching_assignment__subject", "teaching_assignment__teacher")
        .order_by("hour", "student__roll_number")
    )

    od_ids = set(ODRequest.objects.filter(
        status=ODRequest.Status.APPROVED, from_date__lte=day, to_date__gte=day,
    ).values_list("student_id", flat=True))

    periods = {}
    for a in records:
        ta = a.teaching_assignment
        if ta.subject.semester != a.student.semester:
            continue                       # current semester only
        key = (ta.id, a.hour)
        p = periods.setdefault(key, {
            "teaching_assignment": ta.id,
            "hour": a.hour,
            "subject": ta.subject.name,
            "subject_code": ta.subject.code or "",
            "teacher": _name(ta.teacher),
            "records": [],
        })
        p["records"].append({
            "attendance": a.id,
            "student": a.student_id,
            "student_name": a.student.username,
            "student_roll_no": a.student.roll_number,
            "status": a.status,
            "od_locked": a.status == "duty_leave" and a.student_id in od_ids,
        })

    for p in periods.values():
        p["marked"] = True

    # ── #46 Part 3: periods on the APPROVED timetable that were never marked ──
    # The tutor can enter these late (with a reason). Weekends/holidays have none.
    for p in _unmarked_periods(course_id, year_number, day, set(periods.keys()), od_ids):
        periods[(p["teaching_assignment"], p["hour"])] = p

    return Response({"periods": sorted(periods.values(), key=lambda p: (p["hour"], p["subject"]))})


def _unmarked_periods(course_id, year_number, day, marked_keys, od_ids):
    from .attendance_rules import is_working_day
    if not is_working_day(day):
        return []
    try:
        from modules.timetable.models import TimetableEntry, TimetableApproval
    except Exception:
        return []                                    # timetable module off
    approved = set(TimetableApproval.objects.filter(
        status=TimetableApproval.Status.APPROVED,
        year__course_id=course_id, year__year_number=year_number,
    ).values_list("year_id", "semester"))
    if not approved:
        return []
    from core.academics.models import Enrollment
    out = []
    entries = (TimetableEntry.objects
               .filter(assignment__course_id=course_id,
                       assignment__year__year_number=year_number,
                       day_of_week=day.weekday())
               .select_related("assignment__subject", "assignment__teacher", "time_slot"))
    for e in entries:
        ta = e.assignment
        if (ta.year_id, ta.subject.semester) not in approved:
            continue
        key = (ta.id, e.time_slot.period_no)
        if key in marked_keys:
            continue
        students = [
            {"student": en.student_id,
             "student_name": en.student.username,
             "student_roll_no": en.student.roll_number,
             "od_locked": en.student_id in od_ids}
            for en in (Enrollment.objects.filter(teaching_assignment=ta)
                       .select_related("student").order_by("student__roll_number"))
            if en.student.semester == ta.subject.semester
        ]
        if not students:
            continue
        out.append({
            "teaching_assignment": ta.id,
            "hour": e.time_slot.period_no,
            "subject": ta.subject.name,
            "subject_code": ta.subject.code or "",
            "teacher": _name(ta.teacher),
            "records": [],
            "students": students,
            "marked": False,
        })
    return out


def _payload(c):
    return {
        "id": c.id,
        "student_name": c.student.username,
        "student_roll_no": c.student.roll_number,
        "subject": c.teaching_assignment.subject.name,
        "date": c.date,
        "hour": c.hour,
        "old_status": c.old_status,
        "new_status": c.new_status,
        "reason": c.reason,
        "corrected_by": _name(c.corrected_by),
        "corrected_as": c.corrected_as,
        "corrected_at": c.corrected_at,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def attendance_corrections(request):
    """GET: the correction log for one class. POST: correct one record."""
    if request.method == "GET":
        course_id = _int(request.query_params.get("course"))
        year_number = _int(request.query_params.get("year"))
        if not (course_id and year_number):
            return Response({"detail": "course and year are required."}, status=400)
        if not _class_access(request.user, course_id, year_number):
            return Response({"detail": "Only the class in-charge can see this class's corrections."}, status=403)
        qs = (AttendanceCorrection.objects
              .filter(teaching_assignment__course_id=course_id,
                      teaching_assignment__year__year_number=year_number)
              .select_related("student", "teaching_assignment__subject", "corrected_by"))
        return Response([_payload(c) for c in qs[:200]])

    # ---------- POST: correct one record ----------
    att = (Attendance.objects
           .select_related("student", "teaching_assignment__subject", "teaching_assignment__year")
           .filter(pk=_int(request.data.get("attendance"))).first())
    if not att:
        return Response({"detail": "Attendance record not found."}, status=404)

    ta = att.teaching_assignment
    role = _class_access(request.user, ta.course_id, ta.year.year_number)
    if not role:
        return Response({"detail": "Only the class in-charge can correct this class's attendance."}, status=403)

    if ta.subject.semester != att.student.semester:
        return Response({"detail": "Only this semester's attendance can be corrected."}, status=400)

    new_status = request.data.get("new_status")
    if new_status not in TUTOR_STATUSES:
        return Response({"detail": "New status must be Present or Absent."}, status=400)

    if att.status == "duty_leave" and _od_approved(att.student_id, att.date):
        return Response({"detail": "This is an approved on-duty record and can't be changed here."}, status=400)

    if new_status == att.status:
        return Response({"detail": f"The status is already {STATUS_LABEL.get(new_status, new_status)}."}, status=400)

    reason = (request.data.get("reason") or "").strip()
    if len(reason) < MIN_REASON:
        return Response({"detail": f"Please write the reason (at least {MIN_REASON} characters)."}, status=400)

    old_status = att.status
    att.status = new_status
    att.save(update_fields=["status"])

    c = AttendanceCorrection.objects.create(
        attendance=att,
        student=att.student,
        teaching_assignment=ta,
        date=att.date,
        hour=att.hour,
        old_status=old_status,
        new_status=new_status,
        reason=reason,
        corrected_by=request.user,
        corrected_as=role,
    )
    return Response(_payload(c), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def late_entry(request):
    """
    #46 Part 3: the class tutor enters a period that was never marked and
    whose late-entry deadline has passed (or any unmarked past period).
    Body: {teaching_assignment, date, hour, records:[{student, status}], reason}
    Each row is logged (Not marked -> status), and the period is locked so the
    subject teacher can't change it afterwards.
    """
    from core.academics.models import TeachingAssignment, Enrollment
    from .attendance_rules import is_working_day
    from .models import AttendanceLock

    ta = (TeachingAssignment.objects.select_related("subject", "year")
          .filter(pk=_int(request.data.get("teaching_assignment"))).first())
    if not ta:
        return Response({"detail": "Subject not found."}, status=404)
    role = _class_access(request.user, ta.course_id, ta.year.year_number)
    if not role:
        return Response({"detail": "Only the class in-charge can enter this class's attendance."}, status=403)

    try:
        day = datetime.date.fromisoformat(str(request.data.get("date"))[:10])
        hour = int(request.data.get("hour"))
    except (TypeError, ValueError):
        return Response({"detail": "date and hour are required."}, status=400)
    if day > timezone.localdate():
        return Response({"detail": "This date is in the future."}, status=400)
    if not is_working_day(day):
        return Response({"detail": "That day is a holiday or a weekend."}, status=400)
    if Attendance.objects.filter(teaching_assignment=ta, date=day, hour=hour).exists():
        return Response({"detail": "This period is already marked. Use Correct instead."}, status=400)

    reason = (request.data.get("reason") or "").strip()
    if len(reason) < MIN_REASON:
        return Response({"detail": f"Please write the reason (at least {MIN_REASON} characters)."}, status=400)

    enrolled = {
        en.student_id: en.student
        for en in Enrollment.objects.filter(teaching_assignment=ta).select_related("student")
        if en.student.semester == ta.subject.semester
    }
    rows = request.data.get("records") or []
    clean = []
    for r in rows:
        sid = _int(r.get("student"))
        st = r.get("status")
        if sid not in enrolled:
            continue
        if _od_approved(sid, day):
            st = "duty_leave"                      # approved OD always wins
        elif st not in TUTOR_STATUSES:
            return Response({"detail": "Each status must be Present or Absent."}, status=400)
        clean.append((sid, st))
    if not clean:
        return Response({"detail": "No enrolled students to mark."}, status=400)

    for sid, st in clean:
        att = Attendance.objects.create(
            teaching_assignment=ta, student_id=sid, date=day, hour=hour,
            status=st, marked_by=request.user,
        )
        AttendanceCorrection.objects.create(
            attendance=att, student_id=sid, teaching_assignment=ta,
            date=day, hour=hour, old_status=NOT_MARKED, new_status=st,
            reason=reason, corrected_by=request.user, corrected_as=role,
        )
    AttendanceLock.objects.get_or_create(
        teaching_assignment=ta, date=day, hour=hour,
        defaults={"kind": "tutor_late_entry", "locked_by": request.user},
    )
    return Response({"message": f"Attendance entered for {len(clean)} student(s)."}, status=201)

