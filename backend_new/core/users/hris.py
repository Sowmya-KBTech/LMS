"""
HRIS PART A - staff records: the rules and the API in one file.

  GET   /api/users/hris/staff/?department=&designation=&category=&status=&q=   directory + summary
  GET   /api/users/hris/staff/<id>/            one staff record (profile, service, documents, leave)
  PATCH /api/users/hris/staff/<id>/            job details (admin): designation, employment type, AICTE ID ...
  POST  /api/users/hris/staff/<id>/service/    add a service record entry (admin)
  DELETE /api/users/hris/service/<id>/         remove one (admin)
  POST  /api/users/hris/staff/<id>/documents/  upload a document (the staff member or admin)
  DELETE /api/users/hris/documents/<id>/       remove one (whoever uploaded it, or admin)
  GET   /api/users/hris/leave-rules/           days a year per leave type
  PUT   /api/users/hris/leave-rules/           change them (admin)
  GET   /api/users/hris/leave-balance/?year=&staff=   leave left this year (own; admin/HOD for others)
  POST  /api/users/hris/staff/<id>/leave-adjust/      +/- days with a reason (admin)
  GET   /api/users/hris/reports/<key>/         Excel: faculty-list | strength | leave-taken

Who sees a staff record: the person, the college admin, the Principal, and the HOD
of the person's department (not their ID proofs). Who changes job details,
service records, leave rules and adjustments: the college admin.

Designation is the account's sub-role (Assistant Professor, Lab Technician ...),
so it is the same everywhere in the app. A promotion entry with a new designation
changes it; a department change moves the account; relieving deactivates it.

Leave balance: allowance = the rule's days a year + adjustments for that year.
Used = approved (and recorded) leave starting that year; waiting = pending.
A new request is refused when it asks for more than allowance - used - waiting.
The approval route itself (HOD, or Principal for an HOD) is unchanged.
"""
import datetime
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import is_college_admin

from .models import (Department, FacultyProfile, LeaveAdjustment, LeaveRule, ServiceRecord, StaffDocument,
                     User)

STAFF_ROLES = ("teacher", "non_teaching")      # admin logins are system accounts, not staff records
# starting values; the admin changes them on the Leave rules tab (None = no limit)
DEFAULT_RULES = {"casual": Decimal(12), "earned": Decimal(15), "medical": Decimal(10),
                 "compensatory": Decimal(0), "on_duty": None, "other": None}
MAX_DOC_MB = 10
DOC_TYPES = (".pdf", ".jpg", ".jpeg", ".png")


class Refuse(Exception):
    def __init__(self, message, code=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code


def _error(exc):
    return Response({"detail": str(exc)}, status=exc.code)


def _name(u):
    return (u.get_full_name() or "").strip() or u.username


def _num(d):
    if d is None:
        return None
    d = Decimal(d)
    return int(d) if d == d.to_integral() else float(d)


# ============================================================ who ===
def _hod_depts(user):
    if getattr(user, "role", None) != "teacher":
        return set()
    from core.users.acting_hod import hod_department_ids
    return set(hod_department_ids(user))


def _is_principal(user):
    from core.users.principal import is_principal
    return is_principal(user)


def sees_everyone(user):
    return is_college_admin(user) or _is_principal(user)


def can_view(user, staff):
    return (user.id == staff.id or sees_everyone(user)
            or (staff.department_id is not None and staff.department_id in _hod_depts(user)))


def can_see_private(user, staff):
    return user.id == staff.id or is_college_admin(user)


def _staff(pk):
    s = User.objects.select_related("department").filter(pk=pk, role__in=STAFF_ROLES).first()
    if s is None:
        raise Refuse("Staff member not found.", status.HTTP_404_NOT_FOUND)
    return s


def _profile(staff):
    return FacultyProfile.objects.get_or_create(user=staff)[0]


# ============================================================ leave balance ===
def leave_types():
    from modules.attendance.models import StaffLeaveRequest
    return list(StaffLeaveRequest.LeaveType.choices)


def rules():
    """{leave_type: days a year or None}. The starting values are created the first time."""
    have = {r.leave_type: r for r in LeaveRule.objects.all()}
    missing = [LeaveRule(leave_type=t, days_per_year=DEFAULT_RULES.get(t)) for t, _ in leave_types() if t not in have]
    if missing:
        LeaveRule.objects.bulk_create(missing, ignore_conflicts=True)
        have = {r.leave_type: r for r in LeaveRule.objects.all()}
    return {t: have[t].days_per_year if t in have else None for t, _ in leave_types()}


def balance(staff, year=None, exclude_id=None):
    """One row per leave type: allowed / used / waiting / left (None where there is no limit)."""
    from modules.attendance.models import StaffLeaveRequest as L
    year = year or timezone.localdate().year
    limits = rules()
    adj = {r["leave_type"]: r["t"] for r in LeaveAdjustment.objects.filter(staff=staff, year=year)
           .values("leave_type").annotate(t=Sum("days"))}
    taken = L.objects.filter(teacher=staff, from_date__year=year).exclude(pk=exclude_id)
    used = {r["leave_type"]: r["t"] for r in taken.filter(status__in=[L.Status.APPROVED, L.Status.RECORDED])
            .values("leave_type").annotate(t=Sum("days"))}
    waiting = {r["leave_type"]: r["t"] for r in taken.filter(status=L.Status.PENDING)
               .values("leave_type").annotate(t=Sum("days"))}
    rows = []
    for t, label in leave_types():
        u, w = used.get(t) or Decimal(0), waiting.get(t) or Decimal(0)
        limit = limits.get(t)
        allowed = None if limit is None else limit + (adj.get(t) or Decimal(0))
        rows.append({"leave_type": t, "label": label, "limited": allowed is not None,
                     "allowed": _num(allowed), "used": _num(u), "waiting": _num(w),
                     "left": None if allowed is None else _num(allowed - u),
                     "available": None if allowed is None else _num(allowed - u - w)})
    return {"year": year, "rows": rows}


def leave_problem(staff, leave_type, days, year, exclude_id=None):
    """Why this request can't be made (too few days left), or None."""
    row = next((r for r in balance(staff, year, exclude_id)["rows"] if r["leave_type"] == leave_type), None)
    if row is None or not row["limited"]:
        return None
    if Decimal(str(days)) > Decimal(str(row["available"])):
        label = row["label"].lower()
        waiting = f" ({_num(row['waiting'])} waiting for approval)" if row["waiting"] else ""
        return (f"Only {_num(max(Decimal(str(row['available'])), Decimal(0)))} days of {label} are left for "
                f"{year}{waiting}; you asked for {_num(days)}. Choose another leave type for the rest.")
    return None


# ============================================================ data shapes ===
def _experience(p):
    """Years here (from the joining date) and the total the office entered."""
    here = None
    if p.date_of_joining:
        end = p.relieved_on or timezone.localdate()
        here = round((end - p.date_of_joining).days / 365.25, 1)
    return here


def _missing(staff, p):
    out = []
    if not staff.sub_role:
        out.append("designation")
    if staff.role == "teacher" and not p.qualification:
        out.append("qualification")
    if not p.date_of_joining:
        out.append("joining date")
    if not p.employment_type:
        out.append("employment type")
    return out


def _row(staff, p, docs=0):
    return {
        "id": staff.id, "name": _name(staff), "employee_id": staff.employee_id or "",
        "role": staff.role, "category": "teaching" if staff.role == "teacher" else "non_teaching",
        "designation": staff.sub_role or "", "designation_label": staff.get_sub_role_display() or "",
        "department": staff.department_id, "department_name": staff.department.name if staff.department_id else "",
        "qualification": p.qualification, "specialization": p.specialization,
        "date_of_joining": p.date_of_joining, "experience_years": p.experience_years,
        "years_here": _experience(p), "employment_type": p.employment_type,
        "employment_label": dict(FacultyProfile.EMPLOYMENT_CHOICES).get(p.employment_type, ""),
        "aicte_id": p.aicte_id, "relieved_on": p.relieved_on, "is_active": staff.is_active,
        "missing": _missing(staff, p), "documents": docs,
        "has_phd": _phd(p),
    }


def record_view(staff, user):
    p = _profile(staff)
    docs = [d for d in staff.staff_documents.select_related("uploaded_by")
            if not d.is_private or can_see_private(user, staff)]
    data = _row(staff, p, len(docs))
    data.update({
        "email": staff.email or "", "phone": getattr(staff, "phone", "") or "",
        "gender": p.gender, "date_of_birth": p.date_of_birth, "blood_group": p.blood_group,
        "address": ", ".join(x for x in (p.address_line1, p.address_line2, p.city, p.district, p.state, p.pincode) if x),
        "service": [{"id": r.id, "date": r.date, "kind": r.kind, "kind_label": r.get_kind_display(),
                     "details": r.details, "order_no": r.order_no} for r in staff.service_records.all()],
        "documents_list": [{"id": d.id, "kind": d.kind, "kind_label": d.get_kind_display(), "title": d.title,
                            "url": d.file.url if d.file else "", "uploaded_at": d.uploaded_at,
                            "private": d.is_private,
                            "can_delete": is_college_admin(user) or d.uploaded_by_id == user.id}
                           for d in docs],
        "leave": balance(staff) if staff.role == "teacher" else None,
        "teaching": teaching(staff) if staff.role == "teacher" else None,
        "can_edit": is_college_admin(user),
        "can_upload": is_college_admin(user) or user.id == staff.id,
    })
    return data


# ============================================================ teaching ===
def teaching(staff):
    """The classes this teacher has now (Staff records -> Teaching tab).

    One row per teaching assignment: subject, class (course, year, semester),
    core or elective, students enrolled, and periods a week from the timetable
    (None while the class has no timetable). Teaching assignments hold only the
    current allocation, so there is no history of past semesters.
    """
    from core.academics.models import TeachingAssignment

    tas = (TeachingAssignment.objects.filter(teacher=staff)
           .select_related("course", "year", "subject")
           .annotate(n_students=Count("enrollments", distinct=True))
           .order_by("year__year_number", "subject__semester", "subject__code", "subject__name"))
    has_tt = hasattr(TeachingAssignment, "timetable_entries")   # timetable module switched on
    hours = {}
    if has_tt:
        hours = dict(TeachingAssignment.objects.filter(teacher=staff, timetable_entries__kind="class")
                     .values_list("id").annotate(n=Count("timetable_entries")))
    rows = []
    for ta in tas:
        sub = ta.subject
        rows.append({
            "id": ta.id, "subject_id": sub.id, "subject_code": sub.code or "", "subject_name": sub.name,
            "course": ta.course.name, "year": ta.year.year_number, "semester": sub.semester,
            "type": "elective" if sub.is_elective else "core",
            "students": ta.n_students, "hours": hours.get(ta.id) if has_tt else None,
        })
    all_hours = [r["hours"] for r in rows if r["hours"]]
    return {
        "classes": len(rows),
        "subjects": len({r["subject_id"] for r in rows}),
        "students": sum(r["students"] for r in rows),
        "hours": sum(all_hours) if all_hours else None,
        "rows": rows,
    }


# ============================================================ directory ===
def directory_queryset(user, params):
    qs = User.objects.filter(role__in=STAFF_ROLES).select_related("department", "faculty_profile")
    if not sees_everyone(user):
        depts = _hod_depts(user)
        if not depts:
            raise Refuse("Only the admin, the Principal and HODs can see staff records.",
                         status.HTTP_403_FORBIDDEN)
        qs = qs.filter(department_id__in=depts)
    if params.get("department"):
        qs = qs.filter(department_id=params["department"])
    if params.get("designation"):
        qs = qs.filter(sub_role=params["designation"])
    cat = params.get("category")
    if cat == "teaching":
        qs = qs.filter(role="teacher")
    elif cat == "non_teaching":
        qs = qs.exclude(role="teacher")
    st = params.get("status", "active")
    if st == "active":
        qs = qs.filter(is_active=True)
    elif st == "relieved":
        qs = qs.filter(is_active=False)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)
                       | Q(employee_id__icontains=q))
    return qs.order_by("department__name", "first_name", "username")


def _phd(p):
    return "phd" in (p.qualification or "").lower().replace(".", "").replace(" ", "")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_directory(request):
    try:
        staff = list(directory_queryset(request.user, request.query_params))
    except Refuse as exc:
        return _error(exc)
    docs = dict(StaffDocument.objects.filter(staff__in=staff).values_list("staff").annotate(n=Count("id")))
    profiles = {s.id: _profile(s) for s in staff}
    rows = [_row(s, profiles[s.id], docs.get(s.id, 0)) for s in staff]
    for r in rows:
        r.pop("has_phd", None)
    teaching = [s for s in staff if s.role == "teacher" and s.is_active]
    students = User.objects.filter(role="student", is_active=True)
    if not sees_everyone(request.user):
        students = students.filter(department_id__in=_hod_depts(request.user))
    n_students = students.count()
    summary = {
        "teaching": len(teaching),
        "non_teaching": sum(1 for s in staff if s.role != "teacher" and s.is_active),
        "phd": sum(1 for s in teaching if _phd(profiles[s.id])),
        "students": n_students,
        "student_teacher_ratio": round(n_students / len(teaching), 1) if teaching else None,
        "incomplete": sum(1 for r in rows if r["missing"] and r["is_active"]),
    }
    return Response({"rows": rows, "summary": summary, "can_edit": is_college_admin(request.user),
                     "designations": [{"value": v, "label": l} for v, l in User.SUB_ROLE_CHOICES
                                      if v in TEACHING_DESIGNATIONS + NON_TEACHING_DESIGNATIONS]})


TEACHING_DESIGNATIONS = ("professor", "associate_professor", "assistant_professor")
NON_TEACHING_DESIGNATIONS = ("office_assistant", "lab_technician", "librarian", "clerk")


# ============================================================ one record ===
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def staff_record(request, pk):
    try:
        staff = _staff(pk)
        if not can_view(request.user, staff):
            raise Refuse("You can't see this staff record.", status.HTTP_403_FORBIDDEN)
        if request.method == "PATCH":
            if not is_college_admin(request.user):
                raise Refuse("Only the admin changes job details.", status.HTTP_403_FORBIDDEN)
            _save_job(staff, request.data)
    except Refuse as exc:
        return _error(exc)
    return Response(record_view(staff, request.user))


def _date(value, label):
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        raise Refuse(f"{label}: enter a date as YYYY-MM-DD.")


@transaction.atomic
def _save_job(staff, data):
    p = _profile(staff)
    if "designation" in data:
        d = data.get("designation") or ""
        allowed = TEACHING_DESIGNATIONS if staff.role == "teacher" else NON_TEACHING_DESIGNATIONS
        if d and d not in allowed and not (staff.role == "admin"):
            raise Refuse("That designation is not for this kind of staff.")
        if staff.role != "admin":
            staff.sub_role = d or None
            staff.save(update_fields=["sub_role"])
    if "employment_type" in data:
        e = data.get("employment_type") or ""
        if e and e not in dict(FacultyProfile.EMPLOYMENT_CHOICES):
            raise Refuse("Unknown employment type.")
        p.employment_type = e
    for f in ("qualification", "specialization", "aicte_id"):
        if f in data:
            setattr(p, f, str(data.get(f) or "").strip()[:255 if f != "aicte_id" else 30])
    if "date_of_joining" in data:
        p.date_of_joining = _date(data.get("date_of_joining"), "Joining date")
        if p.date_of_joining and p.date_of_joining > timezone.localdate():
            raise Refuse("The joining date can't be in the future.")
    if "experience_years" in data:
        v = data.get("experience_years")
        try:
            p.experience_years = None if v in (None, "") else int(v)
            if p.experience_years is not None and not 0 <= p.experience_years <= 60:
                raise ValueError
        except (TypeError, ValueError):
            raise Refuse("Experience: enter years from 0 to 60.")
    p.save()


# ============================================================ service record ===
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def service_add(request, pk):
    try:
        staff = _staff(pk)
        if not is_college_admin(request.user):
            raise Refuse("Only the admin keeps the service record.", status.HTTP_403_FORBIDDEN)
        rec = _add_service(staff, request.data, request.user)
    except Refuse as exc:
        return _error(exc)
    return Response({"id": rec.id, "record": record_view(staff, request.user)}, status=status.HTTP_201_CREATED)


@transaction.atomic
def _add_service(staff, data, by):
    kind = data.get("kind")
    if kind not in dict(ServiceRecord.KINDS):
        raise Refuse("Choose what happened.")
    when = _date(data.get("date"), "Date")
    if when is None:
        raise Refuse("Enter the date.")
    details = str(data.get("details") or "").strip()
    p = _profile(staff)
    # what the entry changes on the account
    if kind == "promotion" and data.get("new_designation"):
        new = data["new_designation"]
        allowed = TEACHING_DESIGNATIONS if staff.role == "teacher" else NON_TEACHING_DESIGNATIONS
        if new not in allowed:
            raise Refuse("That designation is not for this kind of staff.")
        old = staff.get_sub_role_display() or "—"
        staff.sub_role = new
        staff.save(update_fields=["sub_role"])
        details = details or f"{old} → {staff.get_sub_role_display()}"
    if kind == "transfer":
        dept = Department.objects.filter(pk=data.get("new_department") or 0).first()
        if dept is None:
            raise Refuse("Choose the new department.")
        old = staff.department.name if staff.department_id else "—"
        staff.department = dept
        staff.save(update_fields=["department"])
        details = details or f"{old} → {dept.name}"
    if kind == "relieved":
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        p.relieved_on = when
        p.save(update_fields=["relieved_on"])
        details = details or "Relieved"
    if kind == "joined" and not p.date_of_joining:
        p.date_of_joining = when
        p.save(update_fields=["date_of_joining"])
    if not details:
        raise Refuse("Write what changed.")
    return ServiceRecord.objects.create(staff=staff, date=when, kind=kind, details=details[:300],
                                        order_no=str(data.get("order_no") or "").strip()[:60], created_by=by)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def service_delete(request, pk):
    if not is_college_admin(request.user):
        return Response({"detail": "Only the admin keeps the service record."}, status=403)
    rec = ServiceRecord.objects.filter(pk=pk).first()
    if rec is None:
        return Response({"detail": "Not found."}, status=404)
    rec.delete()          # the account changes it made stay; correct them on the profile if needed
    return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================ documents ===
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def document_add(request, pk):
    try:
        staff = _staff(pk)
        if not (is_college_admin(request.user) or request.user.id == staff.id):
            raise Refuse("Only the staff member or the admin uploads documents.", status.HTTP_403_FORBIDDEN)
        f = request.FILES.get("file")
        kind = request.data.get("kind")
        title = str(request.data.get("title") or "").strip()
        if kind not in dict(StaffDocument.KINDS):
            raise Refuse("Choose the kind of document.")
        if not title:
            raise Refuse("Give the document a name.")
        if f is None:
            raise Refuse("Choose a file.")
        if not f.name.lower().endswith(DOC_TYPES):
            raise Refuse("Upload a PDF, JPG or PNG file.")
        if f.size > MAX_DOC_MB * 1024 * 1024:
            raise Refuse(f"The file is larger than {MAX_DOC_MB} MB.")
        StaffDocument.objects.create(staff=staff, kind=kind, title=title[:150], file=f, uploaded_by=request.user)
    except Refuse as exc:
        return _error(exc)
    return Response(record_view(staff, request.user), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def document_delete(request, pk):
    d = StaffDocument.objects.filter(pk=pk).first()
    if d is None:
        return Response({"detail": "Not found."}, status=404)
    if not (is_college_admin(request.user) or d.uploaded_by_id == request.user.id):
        return Response({"detail": "Only whoever uploaded it, or the admin, can remove it."}, status=403)
    d.file.delete(save=False)
    d.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def can_open_document(user, doc):
    """For the protected file server (core/tenants/file_access.py)."""
    if doc.is_private:
        return can_see_private(user, doc.staff)
    return can_view(user, doc.staff)


# ============================================================ leave rules / balance ===
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def leave_rules(request):
    if request.method == "PUT":
        if not is_college_admin(request.user):
            return Response({"detail": "Only the admin sets the leave rules."}, status=403)
        rows = request.data.get("rules")
        if not isinstance(rows, list):
            return Response({"detail": "Send the list of rules."}, status=400)
        known = dict(leave_types())
        clean = []
        for r in rows:
            t = r.get("leave_type") if isinstance(r, dict) else None
            if t not in known:
                return Response({"detail": "Unknown leave type."}, status=400)
            v = r.get("days_per_year")
            if v in (None, ""):
                clean.append((t, None, r.get("note", "")))
                continue
            try:
                d = Decimal(str(v))
                if d < 0 or d > 365 or d * 2 != (d * 2).to_integral():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return Response({"detail": f"{known[t]}: enter days from 0 to 365, in steps of 0.5, "
                                           "or leave it blank for no limit."}, status=400)
            clean.append((t, d, r.get("note", "")))
        rules()
        for t, d, note in clean:
            LeaveRule.objects.filter(leave_type=t).update(days_per_year=d, note=str(note or "")[:200],
                                                          updated_by=request.user, updated_at=timezone.now())
    limits = rules()
    notes = dict(LeaveRule.objects.values_list("leave_type", "note"))
    return Response({"rules": [{"leave_type": t, "label": l, "days_per_year": _num(limits.get(t)),
                                "note": notes.get(t, "")} for t, l in leave_types()],
                     "can_edit": is_college_admin(request.user)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def leave_balance(request):
    try:
        staff = request.user
        if request.query_params.get("staff"):
            staff = _staff(request.query_params["staff"])
            if not can_view(request.user, staff):
                raise Refuse("You can't see this leave balance.", status.HTTP_403_FORBIDDEN)
        year = request.query_params.get("year")
        year = int(year) if str(year or "").isdigit() else None
    except Refuse as exc:
        return _error(exc)
    return Response(balance(staff, year))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leave_adjust(request, pk):
    try:
        staff = _staff(pk)
        if not is_college_admin(request.user):
            raise Refuse("Only the admin adjusts leave.", status.HTTP_403_FORBIDDEN)
        t = request.data.get("leave_type")
        if t not in dict(leave_types()):
            raise Refuse("Choose the leave type.")
        try:
            days = Decimal(str(request.data.get("days")))
            if days == 0 or abs(days) > 365 or days * 2 != (days * 2).to_integral():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise Refuse("Days: a number like 2 or -1.5 (not 0).")
        reason = str(request.data.get("reason") or "").strip()
        if len(reason) < 5:
            raise Refuse("Write the reason (e.g. 'Worked on Saturday 14 Nov').")
        year = request.data.get("year") or timezone.localdate().year
        LeaveAdjustment.objects.create(staff=staff, leave_type=t, year=int(year), days=days, reason=reason[:200],
                                       by=request.user)
    except Refuse as exc:
        return _error(exc)
    return Response(record_view(staff, request.user), status=status.HTTP_201_CREATED)


# ============================================================ reports ===
REPORTS = {
    "faculty-list": "Faculty list (AICTE / NAAC)",
    "strength": "Staff strength by department",
    "leave-taken": "Leave taken this year",
}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_report(request, key):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    if key not in REPORTS:
        return Response({"detail": "Unknown report."}, status=404)
    try:
        staff = list(directory_queryset(request.user, {**request.query_params.dict(), "status": "active"}))
    except Refuse as exc:
        return _error(exc)
    wb = Workbook()
    ws = wb.active
    ws.title = {"faculty-list": "Faculty", "strength": "Strength", "leave-taken": "Leave taken"}[key]
    if key == "faculty-list":
        ws.append(["Employee ID", "Name", "Department", "Designation", "Qualification", "Specialization",
                   "Date of joining", "Experience (years)", "Years here", "Employment", "AICTE ID"])
        for s in staff:
            if s.role != "teacher":
                continue
            p = _profile(s)
            ws.append([s.employee_id or "", _name(s), s.department.name if s.department_id else "",
                       s.get_sub_role_display() or "", p.qualification, p.specialization,
                       p.date_of_joining, p.experience_years, _experience(p),
                       dict(FacultyProfile.EMPLOYMENT_CHOICES).get(p.employment_type, ""), p.aicte_id])
    elif key == "strength":
        labels = [l for v, l in User.SUB_ROLE_CHOICES if v in TEACHING_DESIGNATIONS + NON_TEACHING_DESIGNATIONS]
        values = [v for v, l in User.SUB_ROLE_CHOICES if v in TEACHING_DESIGNATIONS + NON_TEACHING_DESIGNATIONS]
        ws.append(["Department"] + labels + ["Not set", "Total", "With Ph.D"])
        by = {}
        for s in staff:
            by.setdefault(s.department.name if s.department_id else "No department", []).append(s)
        for dept in sorted(by):
            people = by[dept]
            counts = [sum(1 for s in people if s.sub_role == v) for v in values]
            ws.append([dept] + counts + [sum(1 for s in people if s.sub_role not in values), len(people),
                                         sum(1 for s in people if s.role == "teacher" and _phd(_profile(s)))])
    else:
        from modules.attendance.models import StaffLeaveRequest as L
        year = timezone.localdate().year
        types = leave_types()
        ws.append(["Employee ID", "Name", "Department"] + [l for _, l in types] + ["Total days"])
        for s in staff:
            if s.role != "teacher":
                continue
            used = dict(L.objects.filter(teacher=s, from_date__year=year,
                                         status__in=[L.Status.APPROVED, L.Status.RECORDED])
                        .values_list("leave_type").annotate(t=Sum("days")))
            vals = [_num(used.get(t) or 0) for t, _ in types]
            ws.append([s.employee_id or "", _name(s), s.department.name if s.department_id else ""] + vals
                      + [sum(vals)])
    for c in ws[1]:
        c.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{key}.xlsx"'
    return resp
