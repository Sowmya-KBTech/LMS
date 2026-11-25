"""
WAVE 1 - MENTORING RECORDS (mentoring & guidance by category).

  GET  /api/mentoring/records/?student=<id>[&category=]   records of one student
  POST /api/mentoring/records/                            add a record
  PATCH / DELETE /api/mentoring/records/<id>/             the author (or the HOD) only
  GET  /api/mentoring/student/records/                    a student's own history
  GET  /api/mentoring/hod/records/summary/                HOD: counts by category and
                                                          mentor, students not met lately

Who may do what
  add      the student's ACTIVE mentor this academic year, or the HOD of the
           student's department
  read     the student's current mentor, any mentor who wrote a record for them,
           and the HOD; the student reads their own (without private notes)
  private  a record's private_note is shown ONLY to its author and the HOD -
           never to the student, a parent, another teacher or an admin
"""
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users.models import User

from .models import MentorAllocation, MentoringRecord
from .serializers import person_name
from .utils import current_academic_year, hod_departments

CATEGORIES = dict(MentoringRecord.CATEGORY_CHOICES)
MODES = dict(MentoringRecord.MODE_CHOICES)
NOT_MET_DAYS = 30


# ---------------------------------------------------------------- who is who
def _is_hod_of(user, department_id):
    return department_id is not None and hod_departments(user).filter(id=department_id).exists()


def _active_mentor(student, ay):
    alloc = (MentorAllocation.objects
             .filter(student=student, academic_year=ay, is_active=True)
             .select_related("mentor").first())
    return alloc.mentor if alloc else None


def _can_read_student(user, student, ay):
    if _is_hod_of(user, student.department_id):
        return True
    if getattr(user, "role", None) != "teacher":
        return False
    mentor = _active_mentor(student, ay)
    if mentor and mentor.id == user.id:
        return True
    return MentoringRecord.objects.filter(student=student, mentor=user).exists()


def _can_add(user, student, ay):
    if _is_hod_of(user, student.department_id):
        return True
    mentor = _active_mentor(student, ay)
    return mentor is not None and mentor.id == user.id


def _sees_private(user, rec):
    return rec.mentor_id == user.id or _is_hod_of(user, rec.department_id)


def _record_json(rec, user, for_student=False):
    row = {
        "id": rec.id,
        "date": rec.date,
        "category": rec.category,
        "category_label": CATEGORIES.get(rec.category, rec.category),
        "mode": rec.mode,
        "mode_label": MODES.get(rec.mode, rec.mode),
        "summary": rec.summary,
        "action_points": rec.action_points,
        "follow_up_date": rec.follow_up_date,
        "mentor_name": person_name(rec.mentor),
        "academic_year": rec.academic_year,
    }
    if not for_student:
        row["mentor_id"] = rec.mentor_id
        row["can_edit"] = rec.mentor_id == user.id or _is_hod_of(user, rec.department_id)
        if _sees_private(user, rec):
            row["private_note"] = rec.private_note
    return row


def _clean(data, partial=False):
    """Validate the editable fields. Returns (values, error)."""
    out = {}
    if "category" in data or not partial:
        cat = (data.get("category") or "").strip()
        if cat not in CATEGORIES:
            return None, "Choose a category: " + ", ".join(CATEGORIES.values()) + "."
        out["category"] = cat
    if "mode" in data:
        mode = (data.get("mode") or "one_to_one").strip()
        if mode not in MODES:
            return None, "Choose how the session happened."
        out["mode"] = mode
    if "summary" in data or not partial:
        summary = (data.get("summary") or "").strip()
        if not summary:
            return None, "Write a short summary of the session."
        out["summary"] = summary[:5000]
    for key in ("action_points", "private_note"):
        if key in data:
            out[key] = (data.get(key) or "").strip()[:5000]
    for key in ("date", "follow_up_date"):
        if key in data:
            raw = data.get(key)
            if raw in (None, ""):
                if key == "date":
                    return None, "Give the date of the session."
                out[key] = None
                continue
            value = parse_date(str(raw))
            if value is None:
                return None, f"{'Date' if key == 'date' else 'Follow-up date'} must look like 2026-11-18."
            out[key] = value
    if out.get("date") and out["date"] > timezone.localdate():
        return None, "The session date can't be in the future."
    if out.get("follow_up_date") and out["follow_up_date"] < out.get("date", timezone.localdate()):
        return None, "The follow-up date must be on or after the session date."
    return out, None


def _notify_student(rec):
    if not rec.action_points and not rec.follow_up_date:
        return
    from .views import notify
    when = f" Follow-up on {rec.follow_up_date:%d %b %Y}." if rec.follow_up_date else ""
    notify([rec.student], "Mentoring session recorded",
           f"{person_name(rec.mentor)} recorded a {CATEGORIES[rec.category].lower()} "
           f"guidance session on {rec.date:%d %b %Y}.{when}",
           link="/my-mentor?tab=guidance")


# ---------------------------------------------------------------- staff / HOD
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def records(request):
    ay = request.query_params.get("academic_year") or request.data.get("academic_year") \
        or current_academic_year()
    student_id = request.query_params.get("student") or request.data.get("student")
    student = User.objects.filter(id=student_id, role="student").first() if student_id else None
    if student is None:
        return Response({"detail": "Choose a student."}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "GET":
        if not _can_read_student(request.user, student, ay):
            return Response({"detail": "You are not this student's mentor or HOD."},
                            status=status.HTTP_403_FORBIDDEN)
        qs = MentoringRecord.objects.filter(student=student).select_related("mentor")
        category = request.query_params.get("category")
        if category in CATEGORIES:
            qs = qs.filter(category=category)
        rows = [_record_json(r, request.user) for r in qs]
        counts = dict(MentoringRecord.objects.filter(student=student)
                      .values_list("category").annotate(n=Count("id")))
        return Response({
            "student": {"id": student.id, "name": person_name(student)},
            "can_add": _can_add(request.user, student, ay),
            "categories": [{"key": k, "label": v, "count": counts.get(k, 0)}
                           for k, v in CATEGORIES.items()],
            "modes": [{"key": k, "label": v} for k, v in MODES.items()],
            "records": rows,
        })

    # POST
    if not _can_add(request.user, student, ay):
        return Response({"detail": "Only the student's current mentor or HOD can add a record."},
                        status=status.HTTP_403_FORBIDDEN)
    values, error = _clean(request.data)
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    if student.department_id is None:
        return Response({"detail": "This student has no department."}, status=status.HTTP_400_BAD_REQUEST)
    rec = MentoringRecord.objects.create(
        student=student, mentor=request.user, department_id=student.department_id,
        academic_year=ay, **values)
    _notify_student(rec)
    return Response(_record_json(rec, request.user), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def record_detail(request, record_id):
    rec = MentoringRecord.objects.filter(id=record_id).select_related("mentor", "student").first()
    if rec is None or not _can_read_student(request.user, rec.student, rec.academic_year):
        return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
    if not (rec.mentor_id == request.user.id or _is_hod_of(request.user, rec.department_id)):
        return Response({"detail": "Only the mentor who wrote it, or the HOD, can change it."},
                        status=status.HTTP_403_FORBIDDEN)
    if request.method == "DELETE":
        rec.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    values, error = _clean(request.data, partial=True)
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    for key, value in values.items():
        setattr(rec, key, value)
    rec.save()
    return Response(_record_json(rec, request.user))


# ---------------------------------------------------------------- student
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_records(request):
    if getattr(request.user, "role", None) != "student":
        return Response({"detail": "Only students have a guidance history."},
                        status=status.HTTP_403_FORBIDDEN)
    qs = MentoringRecord.objects.filter(student=request.user).select_related("mentor")
    return Response({
        "categories": [{"key": k, "label": v} for k, v in CATEGORIES.items()],
        "records": [_record_json(r, request.user, for_student=True) for r in qs],
    })


# ---------------------------------------------------------------- HOD summary
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_records_summary(request):
    depts = hod_departments(request.user)
    if not depts.exists():
        return Response({"detail": "You are not the HOD of any department."},
                        status=status.HTTP_403_FORBIDDEN)
    dept_id = request.query_params.get("department")
    dept = depts.filter(id=dept_id).first() if dept_id else depts.first()
    if dept is None:
        return Response({"detail": "That department is not yours."}, status=status.HTTP_403_FORBIDDEN)
    ay = request.query_params.get("academic_year") or current_academic_year()

    recs = MentoringRecord.objects.filter(department=dept, academic_year=ay)
    by_cat = dict(recs.values_list("category").annotate(n=Count("id")))

    allocs = (MentorAllocation.objects
              .filter(department=dept, academic_year=ay, is_active=True)
              .select_related("student", "mentor"))
    last_met = dict(recs.values_list("student").annotate(d=Max("date")))
    cutoff = timezone.localdate() - timedelta(days=NOT_MET_DAYS)

    mentors = {}
    not_met = []
    for a in allocs:
        m = mentors.setdefault(a.mentor_id, {"mentor_id": a.mentor_id, "mentor_name": person_name(a.mentor),
                                             "mentees": 0, "records": 0, "not_met": 0})
        m["mentees"] += 1
        last = last_met.get(a.student_id)
        if last is None or last < cutoff:
            m["not_met"] += 1
            not_met.append({"student_id": a.student_id, "student_name": person_name(a.student),
                            "roll_number": getattr(a.student, "roll_number", "") or "",
                            "mentor_name": person_name(a.mentor), "last_met": last})
    for mentor_id, n in recs.values_list("mentor").annotate(n=Count("id")):
        if mentor_id in mentors:
            mentors[mentor_id]["records"] = n

    not_met.sort(key=lambda r: (r["last_met"] is not None, r["last_met"] or timezone.localdate()))
    return Response({
        "department": {"id": dept.id, "name": dept.name},
        "academic_year": ay,
        "total": recs.count(),
        "by_category": [{"key": k, "label": v, "count": by_cat.get(k, 0)} for k, v in CATEGORIES.items()],
        "mentors": sorted(mentors.values(), key=lambda m: m["mentor_name"].lower()),
        "not_met_days": NOT_MET_DAYS,
        "not_met": not_met,
    })
