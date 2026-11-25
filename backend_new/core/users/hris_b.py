"""
HRIS PART B - achievements (verified by the HOD) and the yearly appraisal.

ACHIEVEMENTS are the existing "My Contributions" entries (FacultyParticipation).
A new entry waits for verification. The HOD of the teacher's department verifies it
or returns it with a note; an HOD's own entries go to the Principal. The college
admin and the IQAC admin can verify too. Only verified entries count in the
appraisal and in the NAAC / NBA reports. A verified entry is locked.

  GET   /api/users/achievements/review/?status=pending|verified|returned|all&department=
  POST  /api/users/achievements/<id>/review/   {action: verify|return, note}
  PATCH /api/users/achievements/<id>/          the teacher corrects a waiting or returned entry

APPRAISAL: once a year (a cycle, e.g. 2025-26, June to May) each teacher scores
themselves in the college's areas, the HOD reviews (own scores and remarks), the
Principal finalises with a grade, and the teacher sees the result and may reply
once. "From the app" facts (subjects, classes held, results, feedback, verified
achievements, class in-charge ...) are filled in so nobody types them.
An HOD's appraisal skips the HOD step. With no Principal set, the admin finalises.

  GET/POST  /api/users/appraisal/cycles/          list / open a cycle (admin)
  PATCH     /api/users/appraisal/cycles/<id>/     close / reopen, change areas (admin)
  GET       /api/users/appraisal/mine/?cycle=     my appraisal (started when first opened)
  GET       /api/users/appraisal/list/?cycle=&department=   teachers and where each is
  GET       /api/users/appraisal/<id>/
  POST      /api/users/appraisal/<id>/self/       {scores, summary, submit}
  POST      /api/users/appraisal/<id>/hod/        {scores, remarks, action: save|forward|send_back, note}
  POST      /api/users/appraisal/<id>/principal/  {grade, remarks, action: save|finalise|send_back, note}
  POST      /api/users/appraisal/<id>/reply/      {reply}
  GET       /api/users/appraisal/export/?cycle=   Excel
"""
import datetime
import io

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.notifications.services import notify
from core.permissions import is_college_admin

from .models import Appraisal, AppraisalCycle, FacultyParticipation, User


class Refuse(Exception):
    def __init__(self, message, code=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code


def _error(exc):
    return Response({"detail": str(exc)}, status=exc.code)


def _name(u):
    return ((u.get_full_name() or "").strip() or u.username) if u else ""


# ============================================================ who ===
def _hod_depts(user):
    if getattr(user, "role", None) != "teacher":
        return set()
    from core.users.acting_hod import hod_department_ids
    return set(hod_department_ids(user))


def _is_principal(user):
    from core.users.principal import is_principal
    return is_principal(user)


def _principal():
    from core.users.principal import current_principal
    return current_principal()


def _is_iqac(user):
    return bool(user.is_superuser) or getattr(user, "sub_role", "") == "iqac_admin"


def _is_hod_of_own_dept(staff):
    return staff.department_id is not None and staff.department_id in _hod_depts(staff)


def _dept_hod(staff):
    if staff.department_id is None:
        return None
    from core.users.acting_hod import current_hod
    return current_hod(staff.department)


def _admins():
    return list(User.objects.filter(role="admin", is_active=True, sub_role__in=[None, "", "super_admin"]))


# ============================================================ achievements ===
def can_verify(user, item):
    staff = item.faculty
    if user.id == staff.id:
        return False
    if is_college_admin(user) or _is_iqac(user) or _is_principal(user):
        return True
    # an HOD's own entries: the "not your own" rule above leaves them to the Principal
    return staff.department_id is not None and staff.department_id in _hod_depts(user)


def verifiers(staff):
    """Who is told about a new entry."""
    if _is_hod_of_own_dept(staff):
        return [_principal()]
    return [_dept_hod(staff)]


def on_added(item):
    """Called after a teacher adds an entry under My Contributions."""
    staff = item.faculty
    notify([v for v in verifiers(staff) if v and v.id != staff.id],
           f"Verify: {item.get_category_display()} by {_name(staff)}",
           f'"{item.title}" is waiting for your verification.', link="/staff?tab=verify")


def _item(i, user):
    return {
        "id": i.id, "faculty": i.faculty_id, "faculty_name": _name(i.faculty),
        "department_name": i.faculty.department.name if i.faculty.department_id else "",
        "category": i.category, "category_label": i.get_category_display(), "title": i.title,
        "organizer": i.organizer, "role_label": i.get_activity_role_display(), "date": i.date,
        "details": i.details, "indexing": i.indexing, "indexing_label": i.get_indexing_display() if i.indexing else "",
        "amount_lakhs": float(i.amount_lakhs) if i.amount_lakhs is not None else None,
        "has_proof": bool(i.proof), "proof_url": i.proof.url if i.proof else None,
        "status": i.status, "status_label": i.get_status_display(), "review_note": i.review_note,
        "verified_by_name": _name(i.verified_by), "verified_at": i.verified_at,
        "can_verify": can_verify(user, i),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def achievements_review(request):
    user = request.user
    qs = FacultyParticipation.objects.select_related("faculty", "faculty__department", "verified_by")
    if not (is_college_admin(user) or _is_iqac(user) or _is_principal(user)):
        depts = _hod_depts(user)
        if not depts:
            return Response({"detail": "Only HODs, the Principal and the admin verify achievements."}, status=403)
        qs = qs.filter(faculty__department_id__in=depts)
    qs = qs.exclude(faculty=user)
    counts = dict(qs.values_list("status").annotate(n=Count("id")))
    st = request.query_params.get("status", "pending")
    if st in ("pending", "verified", "returned"):
        qs = qs.filter(status=st)
    if request.query_params.get("department"):
        qs = qs.filter(faculty__department_id=request.query_params["department"])
    qs = qs.order_by("created_at" if st == "pending" else "-date")[:300]
    return Response({"rows": [_item(i, user) for i in qs],
                     "counts": {k: counts.get(k, 0) for k in ("pending", "verified", "returned")}})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def achievement_review(request, pk):
    i = FacultyParticipation.objects.select_related("faculty").filter(pk=pk).first()
    if i is None:
        return Response({"detail": "Not found."}, status=404)
    if not can_verify(request.user, i):
        return Response({"detail": "You can't verify this entry."}, status=403)
    action = request.data.get("action")
    note = str(request.data.get("note") or "").strip()
    if action == "verify":
        i.status, i.review_note = "verified", note[:300]
        i.verified_by, i.verified_at = request.user, timezone.now()
        msg = f'"{i.title}" was verified by {_name(request.user)}.'
    elif action == "return":
        if len(note) < 5:
            return Response({"detail": "Write what needs correcting."}, status=400)
        i.status, i.review_note, i.verified_by, i.verified_at = "returned", note[:300], None, None
        msg = f'"{i.title}" was returned: {note}'
    else:
        return Response({"detail": "Choose verify or return."}, status=400)
    i.save(update_fields=["status", "review_note", "verified_by", "verified_at"])
    notify([i.faculty], "Contribution verified" if action == "verify" else "Contribution returned",
           msg, link="/my-contributions")
    return Response(_item(i, request.user))


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def achievement_edit(request, pk):
    from .serializers import FacultyParticipationSerializer
    i = FacultyParticipation.objects.filter(pk=pk, faculty=request.user).first()
    if i is None:
        return Response({"detail": "Not found."}, status=404)
    if i.status == "verified":
        return Response({"detail": "A verified entry can't be changed. Ask your HOD to return it."}, status=400)
    ser = FacultyParticipationSerializer(i, data=request.data, partial=True, context={"request": request})
    ser.is_valid(raise_exception=True)
    was_returned = i.status == "returned"
    ser.save(status="pending", review_note="")
    if was_returned:
        on_added(i)
    return Response(ser.data)


# ============================================================ appraisal: facts ===
def _safe(fn):
    try:
        return fn()
    except Exception:            # a module switched off for this product, or no data yet
        return None


def facts(staff, cycle):
    """{area key: [lines]} - what the app already knows for this cycle's dates."""
    start, end = cycle.start, cycle.end
    out = {}

    def teaching():
        from core.academics.models import TeachingAssignment
        lines = []
        tas = TeachingAssignment.objects.filter(teacher=staff)
        n = tas.count()
        lines.append(f"{n} subject{'s' if n != 1 else ''} assigned")
        hours = _safe(lambda: __import__("modules.attendance.models", fromlist=["Attendance"]).Attendance.objects
                      .filter(marked_by=staff, date__range=(start, end)).values("teaching_assignment", "date", "hour")
                      .distinct().count())
        if hours:
            lines.append(f"{hours} class hours with attendance taken")

        def plans():
            from modules.teachingplan.models import HELD_STATUSES, SessionDelivery, TeachingPlan
            p = TeachingPlan.objects.filter(teacher=staff, created_at__date__range=(start, end))
            total, ok = p.count(), p.filter(status="approved").count()
            d = SessionDelivery.objects.filter(plan__teacher=staff, date__range=(start, end))
            rec, held = d.count(), d.filter(status__in=HELD_STATUSES).count()
            got = []
            if total:
                got.append(f"Teaching plans approved: {ok} of {total}")
            if rec:
                got.append(f"Planned classes held: {round(held * 100 / rec)}% ({held} of {rec} recorded)")
            return got
        lines += _safe(plans) or []
        return lines

    def results():
        lines = []

        def passes():
            from core.academics.models import TeachingAssignment
            from modules.exams.models import ResultEntry
            subjects = TeachingAssignment.objects.filter(teacher=staff).values("subject")
            e = ResultEntry.objects.filter(subject__in=subjects, result__is_published=True,
                                           result__created_at__date__range=(start, end))
            n = e.count()
            if n:
                return f"Pass in your subjects: {round(e.filter(is_pass=True).count() * 100 / n)}% of {n} results"
        p = _safe(passes)
        if p:
            lines.append(p)

        def feedback():
            from modules.learning.models import Feedback
            f = Feedback.objects.filter(teacher=staff, direction="s2t", rating__isnull=False,
                                        created_at__date__range=(start, end)).aggregate(a=Avg("rating"), n=Count("id"))
            if f["n"]:
                return f"Student feedback: {f['a']:.1f} / 5 from {f['n']} responses"
        f = _safe(feedback)
        if f:
            lines.append(f)
        return lines or ["No published results or feedback in these dates yet"]

    verified = FacultyParticipation.objects.filter(faculty=staff, status="verified", date__range=(start, end))
    by_cat = dict(verified.values_list("category").annotate(n=Count("id")))

    def count_line(cats, empty):
        labels = dict(FacultyParticipation.CATEGORY_CHOICES)
        parts = [f"{by_cat[c]} {labels[c].lower()}" for c in cats if by_cat.get(c)]
        return [", ".join(parts) + " (verified)"] if parts else [empty]

    def research():
        lines = count_line(["journal", "conference", "book", "patent", "project"], "No verified research entries")
        money = verified.filter(category="project").aggregate(t=Sum("amount_lakhs"))["t"]
        if money:
            lines.append(f"Funded projects: ₹{money} lakh")
        indexed = verified.filter(category="journal", indexing__in=["scopus", "sci", "wos"]).count()
        if indexed:
            lines.append(f"{indexed} journal paper{'s' if indexed != 1 else ''} in Scopus / SCI / Web of Science")
        return lines

    def department():
        lines = []
        tutor = _safe(lambda: staff.tutor_years.count())
        if tutor:
            lines.append(f"Class in-charge for {tutor} class{'es' if tutor != 1 else ''}")
        if _is_hod_of_own_dept(staff):
            lines.append("Head of Department")
        roles = list(staff.service_records.filter(kind="role", date__range=(start, end)).values_list("details", flat=True))
        lines += [f"Role: {r}" for r in roles[:4]]
        lines += count_line(["committee", "workshop_conducted", "guest_lecture"], "") if any(
            by_cat.get(c) for c in ("committee", "workshop_conducted", "guest_lecture")) else []
        return lines or ["Nothing recorded yet"]

    def development():
        return count_line(["fdp", "workshop_attended", "certification"], "No verified FDPs, workshops or courses")

    makers = {"teaching": teaching, "results": results, "research": research,
              "department": department, "development": development}
    for a in cycle.areas:
        fn = makers.get(a["key"])
        out[a["key"]] = (_safe(fn) or ["Could not read this yet"]) if fn else []
    return out


# ============================================================ appraisal: rules ===
GRADE_CUTS = [(90, "A+"), (75, "A"), (60, "B"), (50, "C"), (0, "D")]


def suggest_grade(total, out_of):
    if total is None or not out_of:
        return ""
    pct = total * 100 / out_of
    return next(g for cut, g in GRADE_CUTS if pct >= cut)


def _total(scores, areas):
    vals = [scores.get(a["key"]) for a in areas]
    return sum(v for v in vals if isinstance(v, int)) if any(isinstance(v, int) for v in vals) else None


def _clean_scores(raw, areas, need_all):
    if not isinstance(raw, dict):
        raw = {}
    out = {}
    for a in areas:
        v = raw.get(a["key"])
        if v in (None, ""):
            if need_all:
                raise Refuse(f"Give a score for {a['label']}.")
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise Refuse(f"{a['label']}: enter a whole number.")
        if not 0 <= v <= int(a["max"]):
            raise Refuse(f"{a['label']}: enter 0 to {a['max']}.")
        out[a["key"]] = v
    return out


def hod_step_needed(staff):
    return not _is_hod_of_own_dept(staff) and _dept_hod(staff) is not None


def can_hod(user, ap):
    staff = ap.staff
    if user.id == staff.id:
        return False
    if staff.department_id is not None and staff.department_id in _hod_depts(user):
        return True
    return is_college_admin(user) and _dept_hod(staff) is None


def can_principal(user, ap):
    p = _principal()
    if user.id == ap.staff_id:
        return False
    if p is not None and p.id == user.id:
        return True
    return is_college_admin(user) and (p is None or p.id == ap.staff_id)


def can_view(user, ap):
    return (user.id == ap.staff_id or is_college_admin(user) or _is_principal(user)
            or (ap.staff.department_id is not None and ap.staff.department_id in _hod_depts(user)))


def finalisers(ap):
    p = _principal()
    return [p] if p and p.id != ap.staff_id else _admins()


def view(ap, user):
    c, staff = ap.cycle, ap.staff
    areas = c.areas
    out_of = sum(int(a["max"]) for a in areas)
    mine = user.id == staff.id
    show_review = not mine or ap.status == "done"      # the teacher sees the review once it is final
    hod_total = _total(ap.hod_scores, areas)
    self_total = _total(ap.self_scores, areas)
    return {
        "id": ap.id, "status": ap.status, "status_label": ap.get_status_display(),
        "cycle": {"id": c.id, "name": c.name, "start": c.start, "end": c.end, "is_open": c.is_open},
        "staff": {"id": staff.id, "name": _name(staff), "designation": staff.get_sub_role_display() or "",
                  "department": staff.department.name if staff.department_id else ""},
        "areas": areas, "out_of": out_of, "facts": facts(staff, c),
        "self_scores": ap.self_scores, "self_total": self_total, "self_summary": ap.self_summary,
        "submitted_at": ap.submitted_at,
        "hod_step": hod_step_needed(staff) or bool(ap.hod_at),
        "hod_scores": ap.hod_scores if show_review else {}, "hod_total": hod_total if show_review else None,
        "hod_remarks": ap.hod_remarks if show_review else "", "hod_name": _name(ap.hod_by) if show_review else "",
        "hod_at": ap.hod_at,
        "grade": ap.grade if show_review else "", "grade_label": ap.get_grade_display() if ap.grade and show_review else "",
        "suggested_grade": suggest_grade(hod_total if hod_total is not None else self_total, out_of),
        "principal_remarks": ap.principal_remarks if show_review else "",
        "principal_name": _name(ap.principal_by) if show_review else "", "finalised_at": ap.finalised_at,
        "returned_note": ap.returned_note, "staff_reply": ap.staff_reply,
        "can_self": mine and ap.status == "draft" and c.is_open,
        "can_hod": ap.status == "with_hod" and can_hod(user, ap),
        "can_principal": ap.status == "with_principal" and can_principal(user, ap),
        "can_reply": mine and ap.status == "done" and not ap.staff_reply,
        "grades": [{"value": v, "label": f"{v} · {l}"} for v, l in Appraisal.GRADES],
    }


def _get(pk, user):
    ap = Appraisal.objects.select_related("cycle", "staff", "staff__department", "hod_by", "principal_by") \
        .filter(pk=pk).first()
    if ap is None:
        raise Refuse("Not found.", status.HTTP_404_NOT_FOUND)
    if not can_view(user, ap):
        raise Refuse("You can't see this appraisal.", status.HTTP_403_FORBIDDEN)
    return ap


def current_cycle():
    return AppraisalCycle.objects.filter(is_open=True).order_by("-start").first()


# ============================================================ appraisal: cycles ===
def _cycle_row(c):
    n = dict(c.appraisals.values_list("status").annotate(k=Count("id")))
    return {"id": c.id, "name": c.name, "start": c.start, "end": c.end, "is_open": c.is_open, "areas": c.areas,
            "counts": {k: n.get(k, 0) for k, _ in Appraisal.STATUS_CHOICES},
            "areas_locked": c.appraisals.exclude(status="draft").exists()}


def _clean_areas(raw):
    if not isinstance(raw, list) or not 2 <= len(raw) <= 8:
        raise Refuse("Give 2 to 8 areas.")
    out, keys = [], set()
    for i, a in enumerate(raw):
        label = str((a or {}).get("label") or "").strip()[:60]
        if not label:
            raise Refuse("Every area needs a name.")
        try:
            mx = int(a.get("max"))
        except (TypeError, ValueError):
            raise Refuse(f"{label}: enter the highest score.")
        if not 1 <= mx <= 100:
            raise Refuse(f"{label}: the highest score must be 1 to 100.")
        key = str(a.get("key") or "").strip()[:20] or f"area{i + 1}"
        if key in keys:
            key = f"{key}{i + 1}"
        keys.add(key)
        out.append({"key": key, "label": label, "max": mx})
    return out


def _date(v, label):
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise Refuse(f"{label}: enter a date.")


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def cycles(request):
    if request.method == "POST":
        try:
            if not is_college_admin(request.user):
                raise Refuse("Only the admin opens an appraisal year.", status.HTTP_403_FORBIDDEN)
            name = str(request.data.get("name") or "").strip()[:20]
            if not name:
                raise Refuse("Name the appraisal year, e.g. 2025-26.")
            if AppraisalCycle.objects.filter(name=name).exists():
                raise Refuse("An appraisal year with this name already exists.")
            start, end = _date(request.data.get("start"), "Start"), _date(request.data.get("end"), "End")
            if end <= start:
                raise Refuse("The end date must be after the start date.")
            areas = _clean_areas(request.data["areas"]) if request.data.get("areas") else None
            c = AppraisalCycle.objects.create(name=name, start=start, end=end, created_by=request.user,
                                              **({"areas": areas} if areas else {}))
        except Refuse as exc:
            return _error(exc)
        return Response(_cycle_row(c), status=201)
    return Response({"cycles": [_cycle_row(c) for c in AppraisalCycle.objects.all()],
                     "can_edit": is_college_admin(request.user)})


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def cycle_edit(request, pk):
    try:
        if not is_college_admin(request.user):
            raise Refuse("Only the admin changes an appraisal year.", status.HTTP_403_FORBIDDEN)
        c = AppraisalCycle.objects.filter(pk=pk).first()
        if c is None:
            raise Refuse("Not found.", status.HTTP_404_NOT_FOUND)
        if "is_open" in request.data:
            c.is_open = bool(request.data["is_open"])
        if "areas" in request.data:
            if c.appraisals.exclude(status="draft").exists():
                raise Refuse("Appraisals have already been sent in for this year, so its areas are fixed.")
            c.areas = _clean_areas(request.data["areas"])
            c.appraisals.update(self_scores={}, hod_scores={})
        if "end" in request.data:
            c.end = _date(request.data["end"], "End")
            if c.end <= c.start:
                raise Refuse("The end date must be after the start date.")
        c.save()
    except Refuse as exc:
        return _error(exc)
    return Response(_cycle_row(c))


# ============================================================ appraisal: the steps ===
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mine(request):
    user = request.user
    if user.role != "teacher":
        return Response({"detail": "Appraisal is for teaching staff."}, status=403)
    cid = request.query_params.get("cycle")
    c = AppraisalCycle.objects.filter(pk=cid).first() if cid else current_cycle()
    years = [{"id": x.id, "name": x.name} for x in AppraisalCycle.objects.filter(appraisals__staff=user)] \
        + ([{"id": c.id, "name": c.name}] if c else [])
    years = list({y["id"]: y for y in years}.values())
    if c is None:
        return Response({"appraisal": None, "years": years,
                         "message": "No appraisal year is open. The admin opens one."})
    ap = Appraisal.objects.filter(cycle=c, staff=user).first()
    if ap is None:
        if not c.is_open:
            return Response({"appraisal": None, "years": years, "message": f"You had no appraisal in {c.name}."})
        ap = Appraisal.objects.create(cycle=c, staff=user)
    return Response({"appraisal": view(_get(ap.id, user), user), "years": years})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def one(request, pk):
    try:
        ap = _get(pk, request.user)
    except Refuse as exc:
        return _error(exc)
    return Response(view(ap, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def self_step(request, pk):
    try:
        with transaction.atomic():
            ap = _get(pk, request.user)
            if ap.staff_id != request.user.id:
                raise Refuse("Only the teacher fills in their own scores.", status.HTTP_403_FORBIDDEN)
            if ap.status != "draft" or not ap.cycle.is_open:
                raise Refuse("This appraisal has been sent in and can't be changed now.")
            submit = bool(request.data.get("submit"))
            ap.self_scores = _clean_scores(request.data.get("scores"), ap.cycle.areas, need_all=submit)
            ap.self_summary = str(request.data.get("summary") or "").strip()[:3000]
            if submit:
                if len(ap.self_summary) < 20:
                    raise Refuse("Write a short summary of your year (at least a sentence).")
                ap.submitted_at = timezone.now()
                ap.returned_note = ""
                ap.status = "with_hod" if hod_step_needed(ap.staff) else "with_principal"
            ap.save()
    except Refuse as exc:
        return _error(exc)
    if submit:
        to = [_dept_hod(ap.staff)] if ap.status == "with_hod" else finalisers(ap)
        notify(to, f"Appraisal to review: {_name(ap.staff)}",
               f"{_name(ap.staff)} sent in their {ap.cycle.name} appraisal.", link=f"/staff?tab=appraisals&open={ap.id}")
    return Response(view(ap, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def hod_step(request, pk):
    try:
        with transaction.atomic():
            ap = _get(pk, request.user)
            if ap.status != "with_hod" or not can_hod(request.user, ap):
                raise Refuse("This appraisal is not waiting for you.", status.HTTP_403_FORBIDDEN)
            action = request.data.get("action", "save")
            if action == "send_back":
                note = str(request.data.get("note") or "").strip()
                if len(note) < 5:
                    raise Refuse("Write what the teacher should change.")
                ap.status, ap.returned_note = "draft", note[:300]
            else:
                ap.hod_scores = _clean_scores(request.data.get("scores"), ap.cycle.areas,
                                              need_all=action == "forward")
                ap.hod_remarks = str(request.data.get("remarks") or "").strip()[:3000]
                if action == "forward":
                    if len(ap.hod_remarks) < 10:
                        raise Refuse("Write your remarks before sending it on.")
                    ap.status, ap.hod_by, ap.hod_at = "with_principal", request.user, timezone.now()
            ap.save()
    except Refuse as exc:
        return _error(exc)
    if action == "send_back":
        notify([ap.staff], "Appraisal sent back", f"Your HOD sent back your {ap.cycle.name} appraisal: {ap.returned_note}",
               link="/staff?tab=appraisal")
    elif action == "forward":
        notify(finalisers(ap), f"Appraisal to finalise: {_name(ap.staff)}",
               f"The HOD has reviewed {_name(ap.staff)}'s {ap.cycle.name} appraisal.",
               link=f"/staff?tab=appraisals&open={ap.id}")
    return Response(view(ap, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def principal_step(request, pk):
    try:
        with transaction.atomic():
            ap = _get(pk, request.user)
            if ap.status != "with_principal" or not can_principal(request.user, ap):
                raise Refuse("This appraisal is not waiting for you.", status.HTTP_403_FORBIDDEN)
            action = request.data.get("action", "save")
            note = str(request.data.get("note") or "").strip()
            if action == "send_back":
                if len(note) < 5:
                    raise Refuse("Write why it is going back.")
                back_to_hod = bool(ap.hod_at)
                ap.status, ap.returned_note = ("with_hod" if back_to_hod else "draft"), note[:300]
                if back_to_hod:
                    ap.hod_at = None
            else:
                grade = request.data.get("grade") or ""
                if grade and grade not in dict(Appraisal.GRADES):
                    raise Refuse("Choose a grade.")
                ap.grade = grade
                ap.principal_remarks = str(request.data.get("remarks") or "").strip()[:3000]
                if action == "finalise":
                    if not grade:
                        raise Refuse("Choose the grade.")
                    if len(ap.principal_remarks) < 10:
                        raise Refuse("Write your remarks before finalising.")
                    ap.status, ap.principal_by, ap.finalised_at = "done", request.user, timezone.now()
                    ap.returned_note = ""
            ap.save()
    except Refuse as exc:
        return _error(exc)
    if action == "finalise":
        notify([ap.staff], "Your appraisal is final",
               f"Your {ap.cycle.name} appraisal is final: {ap.grade} ({ap.get_grade_display()}).",
               link="/staff?tab=appraisal")
    elif action == "send_back":
        to = [ap.hod_by or _dept_hod(ap.staff)] if ap.status == "with_hod" else [ap.staff]
        notify(to, "Appraisal sent back", f"{_name(ap.staff)}'s {ap.cycle.name} appraisal came back: {ap.returned_note}",
               link=f"/staff?tab=appraisals&open={ap.id}" if ap.status == "with_hod" else "/staff?tab=appraisal")
    return Response(view(ap, request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def reply_step(request, pk):
    try:
        ap = _get(pk, request.user)
        if ap.staff_id != request.user.id or ap.status != "done":
            raise Refuse("You can reply once your appraisal is final.", status.HTTP_403_FORBIDDEN)
        if ap.staff_reply:
            raise Refuse("You have already replied.")
        reply = str(request.data.get("reply") or "").strip()
        if len(reply) < 5:
            raise Refuse("Write your reply.")
        ap.staff_reply = reply[:2000]
        ap.save(update_fields=["staff_reply", "updated_at"])
    except Refuse as exc:
        return _error(exc)
    return Response(view(ap, request.user))


# ============================================================ appraisal: lists ===
def _scope_teachers(user):
    qs = User.objects.filter(role="teacher", is_active=True).select_related("department")
    if is_college_admin(user) or _is_principal(user):
        return qs
    depts = _hod_depts(user)
    if not depts:
        raise Refuse("Only HODs, the Principal and the admin see appraisals.", status.HTTP_403_FORBIDDEN)
    return qs.filter(department_id__in=depts)


def _rows(user, c, department=None):
    teachers = _scope_teachers(user).exclude(pk=user.pk)
    if department:
        teachers = teachers.filter(department_id=department)
    aps = {a.staff_id: a for a in Appraisal.objects.filter(cycle=c, staff__in=teachers)}
    out_of = sum(int(a["max"]) for a in c.areas)
    rows = []
    for t in teachers.order_by("department__name", "first_name", "username"):
        a = aps.get(t.id)
        rows.append({
            "staff": t.id, "name": _name(t), "designation": t.get_sub_role_display() or "",
            "department": t.department.name if t.department_id else "",
            "id": a.id if a else None, "status": a.status if a else "not_started",
            "status_label": a.get_status_display() if a else "Not started",
            "self_total": _total(a.self_scores, c.areas) if a and a.status != "draft" else None,
            "hod_total": _total(a.hod_scores, c.areas) if a else None,
            "grade": a.grade if a and a.status == "done" else "",
            "waiting_for_me": bool(a) and ((a.status == "with_hod" and can_hod(user, a))
                                           or (a.status == "with_principal" and can_principal(user, a))),
        })
    return rows, out_of


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def appraisal_list(request):
    cid = request.query_params.get("cycle")
    c = AppraisalCycle.objects.filter(pk=cid).first() if cid else (current_cycle() or AppraisalCycle.objects.first())
    if c is None:
        return Response({"cycle": None, "rows": [], "cycles": [], "can_edit": is_college_admin(request.user)})
    try:
        rows, out_of = _rows(request.user, c, request.query_params.get("department"))
    except Refuse as exc:
        return _error(exc)
    return Response({"cycle": _cycle_row(c), "rows": rows, "out_of": out_of,
                     "cycles": [{"id": x.id, "name": x.name, "is_open": x.is_open} for x in AppraisalCycle.objects.all()],
                     "can_edit": is_college_admin(request.user)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def appraisal_export(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    c = AppraisalCycle.objects.filter(pk=request.query_params.get("cycle") or 0).first() or current_cycle()
    if c is None:
        return Response({"detail": "No appraisal year."}, status=404)
    try:
        rows, out_of = _rows(request.user, c)
    except Refuse as exc:
        return _error(exc)
    full = {a.staff_id: a for a in Appraisal.objects.filter(cycle=c)}
    wb = Workbook()
    ws = wb.active
    ws.title = "Appraisal"
    ws.append(["Name", "Department", "Designation", "Status"]
              + [f"{a['label']} (HOD, of {a['max']})" for a in c.areas]
              + [f"Self total (of {out_of})", f"HOD total (of {out_of})", "Grade"])
    for r in rows:
        a = full.get(r["staff"])
        ws.append([r["name"], r["department"], r["designation"], r["status_label"]]
                  + [(a.hod_scores.get(x["key"]) if a else None) for x in c.areas]
                  + [r["self_total"], r["hod_total"], r["grade"]])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="appraisal-{c.name}.xlsx"'
    return resp
