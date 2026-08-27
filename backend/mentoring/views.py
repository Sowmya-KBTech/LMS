# backend/mentoring/views.py
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Department, User

from .models import (
    MentorAllocation,
    MentorBroadcast,
    MentorBroadcastRecipient,
    MentorChangeRequest,
    MentoringSetting,
)
from .serializers import (
    AdvisorActSerializer,
    AllocationSerializer,
    MentorRaiseSerializer,
    AssignSerializer,
    ChangeRequestSerializer,
    CreateChangeRequestSerializer,
    DecideChangeRequestSerializer,
    DecideProposalSerializer,
    MentoringSettingSerializer,
    MentorBriefSerializer,
    RemoveSerializer,
    person_name,
)
from .utils import (
    best_fit,
    cgpa_map,
    current_academic_year,
    academic_year_choices,
    band_for_cgpa,
    department_mentors,
    department_students,
    group_balance,
    hod_departments,
    mentor_loads,
    suggest_split,
    why_best_fit,
)


YEAR_LABEL = {1: "I", 2: "II", 3: "III", 4: "IV"}


def notify(recipients, title, message):
    """
    Writes to the Notification model your LMS already has, so the bell in
    the navbar counts mentoring messages like everything else.
    """
    from courses.models import Notification

    Notification.objects.bulk_create([
        Notification(
            recipient=r, title=title, message=message[:400],
            notification_type="announcement",
        )
        for r in recipients
    ])


# ================= HELPERS =================
def _dept_for(request):
    """
    The department this HOD is acting on. ?department=<id> when they head
    more than one. Returns (department, setting, error_response).
    """
    depts = hod_departments(request.user)
    if not depts.exists():
        return None, None, Response(
            {"detail": "You are not the HOD of any department."},
            status=status.HTTP_403_FORBIDDEN,
        )

    dept_id = request.query_params.get("department") or request.data.get("department")
    if dept_id:
        dept = depts.filter(id=dept_id).first()
        if not dept:
            return None, None, Response(
                {"detail": "That department is not yours."},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        dept = depts.first()

    return dept, MentoringSetting.for_department(dept), None


def _year(request):
    return request.query_params.get("academic_year") or \
           request.data.get("academic_year") or current_academic_year()


def _mentor_rows(dept, setting, ay):
    """Capacity + composition for every mentor. Used by three screens."""
    mentors = list(department_mentors(dept))
    loads = mentor_loads(dept, ay)
    rows = []
    for m in mentors:
        load = loads.get(m.id, {"total": 0, "A": 0, "B": 0, "C": 0})
        state, message = group_balance(load, setting)
        rows.append({
            "id": m.id,
            "name": person_name(m),
            "employee_id": m.employee_id,
            "designation": m.get_sub_role_display() if m.sub_role else "",
            "email": m.email,
            "assigned": load["total"],
            "capacity": setting.max_students_per_mentor,
            "available": max(0, setting.max_students_per_mentor - load["total"]),
            "is_full": load["total"] >= setting.max_students_per_mentor,
            "band_a": load["A"], "band_b": load["B"], "band_c": load["C"],
            "balance_state": state, "balance_message": message,
        })
    return rows, mentors, loads


# ================= 1. DASHBOARD =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_dashboard(request):
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    students = department_students(dept, setting=setting)
    total_students = students.count()

    allocs = MentorAllocation.objects.filter(department=dept, academic_year=ay)
    active = allocs.filter(is_active=True).count()
    pending = allocs.filter(status="pending").count()

    allocated_ids = set(
        allocs.filter(Q(is_active=True) | Q(status="pending"))
        .values_list("student_id", flat=True)
    )
    unassigned = total_students - len(allocated_ids)

    # proposals grouped by the class advisor who sent them
    by_advisor = {}
    for a in allocs.filter(source="advisor").select_related("proposed_by"):
        if not a.proposed_by_id:
            continue
        row = by_advisor.setdefault(a.proposed_by_id, {
            "advisor_id": a.proposed_by_id,
            "advisor_name": person_name(a.proposed_by),
            "proposed": 0, "approved": 0, "waiting": 0,
        })
        row["proposed"] += 1
        if a.status == "active":
            row["approved"] += 1
        elif a.status == "pending":
            row["waiting"] += 1

    recent = allocs.exclude(status="pending").order_by("-updated_at")[:6]
    mentor_rows, _, _ = _mentor_rows(dept, setting, ay)

    return Response({
        "department": {"id": dept.id, "name": dept.name},
        "academic_year": ay,
        "academic_year_choices": academic_year_choices(),
        "cards": {
            "total_mentors": len(mentor_rows),
            "total_students": total_students,
            "active_allocations": active,
            "pending_allocations": pending,
        },
        "waiting_on_you": {
            "advisor_proposals": pending,
            "students_without_mentor": unassigned,
            "unallocated_pool": unassigned,
        },
        "advisor_proposals": list(by_advisor.values()),
        "recent_changes": AllocationSerializer(recent, many=True).data,
        "mentors": mentor_rows,
    })


# ================= 2. ALLOCATION LIST =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_allocations(request):
    """
    Every student in the department with their allocation state.
    Students with no row at all come back as status 'none'.

    Filters: ?year= &course= &band= &mentor= &status= &q= &academic_year=
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    students = list(department_students(
        dept,
        year=request.query_params.get("year") or None,
        course=request.query_params.get("course") or None,
        setting=setting,
    ))
    cgpas = cgpa_map(students)

    live = {
        a.student_id: a
        for a in MentorAllocation.objects.filter(
            department=dept, academic_year=ay
        ).filter(Q(is_active=True) | Q(status="pending"))
        .select_related("mentor", "proposed_by")
    }

    f_band = request.query_params.get("band")
    f_mentor = request.query_params.get("mentor")
    f_status = request.query_params.get("status")
    q = (request.query_params.get("q") or "").strip().lower()

    rows = []
    for s in students:
        a = live.get(s.id)
        cgpa = cgpas.get(s.id)
        band = a.grade_band if a and a.grade_band else band_for_cgpa(cgpa, setting)

        row = {
            "student_id": s.id,
            "student_name": person_name(s),
            "roll_number": s.roll_number,
            "year": s.year,
            "semester": s.semester,
            "course_name": s.course.name if s.course_id else "",
            "cgpa": cgpa,
            "grade_band": band or "",
            "academic_year": ay,
            "allocation_id": a.id if a else None,
            "mentor_id": a.mentor_id if a else None,
            "mentor_name": person_name(a.mentor) if a else "",
            "status": a.status if a else "none",
            "source": a.source if a else "",
            "recommended_by": (
                person_name(a.proposed_by) if a and a.source == "advisor" and a.proposed_by
                else ("Auto-distributed" if a and a.source == "auto"
                      else ("HOD" if a else ""))
            ),
        }

        if f_band and row["grade_band"] != f_band:
            continue
        if f_status and row["status"] != f_status:
            continue
        if f_mentor == "none" and row["mentor_id"]:
            continue
        if f_mentor and f_mentor != "none" and str(row["mentor_id"]) != str(f_mentor):
            continue
        if q:
            emp = ""
            if a and a.mentor:
                emp = (a.mentor.employee_id or "").lower()
            hay = " ".join([
                row["student_name"].lower(),
                (row["roll_number"] or "").lower(),
                row["mentor_name"].lower(),
                emp,
            ])
            if q not in hay:
                continue

        rows.append(row)

    rows.sort(key=lambda r: (r["year"] or 0, r["student_name"]))
    mentor_rows, _, _ = _mentor_rows(dept, setting, ay)

    return Response({
        "academic_year": ay,
        "academic_year_choices": academic_year_choices(),
        "department": {"id": dept.id, "name": dept.name},
        "settings": MentoringSettingSerializer(setting).data,
        "count": len(rows),
        "results": rows,
        "mentors": mentor_rows,
    })


# ================= 3. PROPOSAL BATCHES =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_proposals(request):
    """Pending advisor proposals grouped by advisor, plus the unassigned pool."""
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    pending = MentorAllocation.objects.filter(
        department=dept, academic_year=ay, status="pending"
    ).select_related("student", "mentor", "proposed_by", "student__course")

    batches = {}
    for a in pending:
        key = a.proposed_by_id or 0
        b = batches.setdefault(key, {
            "key": f"advisor-{key}",
            "advisor_id": a.proposed_by_id,
            "advisor_name": person_name(a.proposed_by) or "Unknown advisor",
            "students": [], "mentor_spread": {},
            "band_a": 0, "band_b": 0, "band_c": 0,
        })
        b["students"].append({
            "allocation_id": a.id,
            "student_id": a.student_id,
            "student_name": person_name(a.student),
            "roll_number": a.student.roll_number,
            "year": a.student.year,
            "course_name": a.student.course.name if a.student.course_id else "",
            "grade_band": a.grade_band,
            "mentor_id": a.mentor_id,
            "mentor_name": person_name(a.mentor),
        })
        name = person_name(a.mentor)
        b["mentor_spread"][name] = b["mentor_spread"].get(name, 0) + 1
        if a.grade_band in ("A", "B", "C"):
            b["band_" + a.grade_band.lower()] += 1

    for b in batches.values():
        b["count"] = len(b["students"])
        b["balanced"] = (b["band_a"] > 0 and b["band_c"] > 0) if setting.require_all_bands else True

    # unassigned pool
    students = list(department_students(dept, setting=setting))
    taken = set(
        MentorAllocation.objects.filter(department=dept, academic_year=ay)
        .filter(Q(is_active=True) | Q(status="pending"))
        .values_list("student_id", flat=True)
    )
    pool_students = [s for s in students if s.id not in taken]
    cgpas = cgpa_map(pool_students)
    pool = [{
        "id": s.id,
        "student_name": person_name(s),
        "roll_number": s.roll_number,
        "year": s.year,
        "course_name": s.course.name if s.course_id else "",
        "cgpa": cgpas.get(s.id),
        "band": band_for_cgpa(cgpas.get(s.id), setting),
    } for s in pool_students]

    return Response({
        "academic_year": ay,
        "batches": sorted(batches.values(), key=lambda b: -b["count"]),
        "pool": {
            "count": len(pool),
            "band_a": sum(1 for p in pool if p["band"] == "A"),
            "band_b": sum(1 for p in pool if p["band"] == "B"),
            "band_c": sum(1 for p in pool if p["band"] == "C"),
            "students": pool,
        },
    })


# ================= 4. SUGGESTION / PREVIEW =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_suggest(request):
    """
    ?student=<id>   -> best fit for one student, with the reasons
    (no student)    -> preview split for the whole unassigned pool
    Read-only. Nothing is written here.
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)
    mentor_rows, mentors, loads = _mentor_rows(dept, setting, ay)

    sid = request.query_params.get("student")
    if sid:
        student = User.objects.filter(id=sid, department=dept, role="student").first()
        if not student:
            return Response({"detail": "Student not found in your department."},
                            status=status.HTTP_404_NOT_FOUND)
        cgpa = cgpa_map([student]).get(student.id)
        band = band_for_cgpa(cgpa, setting)
        pick = best_fit(mentors, loads, band, setting)
        if not pick:
            return Response({"suggested": None,
                             "reasons": ["Every mentor is at capacity."]})
        return Response({
            "student_id": student.id,
            "grade_band": band,
            "suggested": MentorBriefSerializer(pick).data,
            "reasons": why_best_fit(pick, loads, band, setting),
        })

    taken = set(
        MentorAllocation.objects.filter(department=dept, academic_year=ay)
        .filter(Q(is_active=True) | Q(status="pending"))
        .values_list("student_id", flat=True)
    )
    pool_students = [s for s in department_students(dept, setting=setting) if s.id not in taken]
    cgpas = cgpa_map(pool_students)
    payload = [{
        "id": s.id,
        "band": band_for_cgpa(cgpas.get(s.id), setting),
    } for s in pool_students]

    plan = suggest_split(payload, mentors, loads, setting)
    by_id = {m.id: m for m in mentors}

    preview = []
    for mid, sids in plan.items():
        load = loads.get(mid, {"total": 0, "A": 0, "B": 0, "C": 0})
        after = load["total"] + len(sids)
        preview.append({
            "mentor_id": mid,
            "mentor_name": person_name(by_id[mid]),
            "before": load["total"],
            "adding": len(sids),
            "after": after,
            "capacity": setting.max_students_per_mentor,
            "over_capacity": after > setting.max_students_per_mentor,
            "student_ids": sids,
        })

    preview.sort(key=lambda p: -p["adding"])
    return Response({
        "academic_year": ay,
        "total_students": len(pool_students),
        "preview": preview,
        "any_over_capacity": any(p["over_capacity"] for p in preview),
    })


# ================= 5. ASSIGN / REASSIGN / BULK =================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_assign(request):
    """
    Assign or reassign one or many students to one mentor.
    Reassign is two writes in one transaction: close the old row, open a new one.
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err

    ser = AssignSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    ay = data.get("academic_year") or current_academic_year()

    mentor = User.objects.filter(
        id=data["mentor_id"], role="teacher", department=dept
    ).first()
    if not mentor:
        return Response({"detail": "Mentor not found in your department."},
                        status=status.HTTP_400_BAD_REQUEST)

    students = list(User.objects.filter(
        id__in=data["student_ids"], role="student", department=dept
    ))
    if not students:
        return Response({"detail": "No matching student in your department."},
                        status=status.HTTP_400_BAD_REQUEST)

    _, mentors, loads = _mentor_rows(dept, setting, ay)
    load = loads.get(mentor.id, {"total": 0, "A": 0, "B": 0, "C": 0})
    after = load["total"] + len(students)

    # capacity is a warning: the client confirms with override=true
    if after > setting.max_students_per_mentor and not data["override"]:
        return Response({
            "warning": "capacity",
            "message": (
                f"{person_name(mentor)} would hold {after} of "
                f"{setting.max_students_per_mentor}. Send override=true to continue."
            ),
            "before": load["total"], "after": after,
            "capacity": setting.max_students_per_mentor,
        }, status=status.HTTP_409_CONFLICT)

    cgpas = cgpa_map(students)
    created = []

    with transaction.atomic():
        for s in students:
            cgpa = cgpas.get(s.id)
            band = band_for_cgpa(cgpa, setting)
            if band is None and setting.first_year_rule == "band_b":
                band = "B"

            old = MentorAllocation.objects.select_for_update().filter(
                student=s, academic_year=ay
            ).filter(Q(is_active=True) | Q(status="pending")).first()

            previous_mentor = None
            if old:
                previous_mentor = old.mentor
                if old.mentor_id == mentor.id and old.is_active:
                    continue  # already with this mentor, nothing to do
                old.close(reason="Reassigned by the HOD", by_user=request.user)

            suggested = best_fit(mentors, loads, band, setting)
            reason = "Reassigned by the HOD" if previous_mentor else "Assigned by the HOD"
            if suggested and suggested.id != mentor.id:
                reason += f" · best fit was {person_name(suggested)}"

            created.append(MentorAllocation.objects.create(
                student=s, mentor=mentor, department=dept, academic_year=ay,
                grade_band=band or "", cgpa_at_allocation=cgpa,
                status="active", is_active=True, source="hod",
                approved_by=request.user,
                previous_mentor=previous_mentor,
                suggested_mentor=suggested if (suggested and suggested.id != mentor.id) else None,
                reason=reason, note=data.get("note", ""),
            ))

            d = loads.setdefault(mentor.id, {"total": 0, "A": 0, "B": 0, "C": 0})
            d["total"] += 1
            if band:
                d[band] += 1

    return Response({
        "assigned": len(created),
        "mentor": person_name(mentor),
        "results": AllocationSerializer(created, many=True).data,
    }, status=status.HTTP_201_CREATED)


# ================= 6. AUTO-DISTRIBUTE (confirm step) =================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_auto_distribute(request):
    """Applies the plan from hod_suggest. Call that first to show the preview."""
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    _, mentors, loads = _mentor_rows(dept, setting, ay)
    taken = set(
        MentorAllocation.objects.filter(department=dept, academic_year=ay)
        .filter(Q(is_active=True) | Q(status="pending"))
        .values_list("student_id", flat=True)
    )
    pool = [s for s in department_students(dept, setting=setting) if s.id not in taken]
    if not pool:
        return Response({"assigned": 0, "detail": "Every student already has a mentor."})

    cgpas = cgpa_map(pool)
    payload = [{"id": s.id, "band": band_for_cgpa(cgpas.get(s.id), setting)} for s in pool]
    plan = suggest_split(payload, mentors, loads, setting)

    by_student = {s.id: s for s in pool}
    by_mentor = {m.id: m for m in mentors}
    made = 0

    with transaction.atomic():
        for mid, sids in plan.items():
            for sid in sids:
                s = by_student[sid]
                cgpa = cgpas.get(sid)
                band = band_for_cgpa(cgpa, setting)
                if band is None and setting.first_year_rule == "band_b":
                    band = "B"
                MentorAllocation.objects.create(
                    student=s, mentor=by_mentor[mid], department=dept,
                    academic_year=ay, grade_band=band or "", cgpa_at_allocation=cgpa,
                    status="active", is_active=True, source="auto",
                    approved_by=request.user,
                    reason="Auto-distributed by the HOD, balanced by grade band",
                )
                made += 1

    return Response({"assigned": made}, status=status.HTTP_201_CREATED)


# ================= 7. APPROVE / REJECT PROPOSALS =================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_decide_proposals(request):
    """Approve or reject advisor proposals. Send one id or a whole batch."""
    dept, _setting, err = _dept_for(request)
    if err:
        return err

    ser = DecideProposalSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    qs = MentorAllocation.objects.filter(
        id__in=data["allocation_ids"], department=dept, status="pending"
    )
    if not qs.exists():
        return Response({"detail": "No pending proposal matched."},
                        status=status.HTTP_404_NOT_FOUND)

    n = 0
    with transaction.atomic():
        for a in qs.select_for_update():
            if data["decision"] == "approve":
                a.approved_by = request.user
                a.status = "active"
                a.is_active = True
                a.reason = "Advisor proposal approved by the HOD"
                if data.get("note"):
                    a.note = data["note"]
                a.save()
            else:
                a.status = "rejected"
                a.is_active = False
                a.end_date = timezone.localdate()
                a.approved_by = request.user
                a.reason = (
                    f"Proposal of {person_name(a.mentor)} rejected by the HOD"
                )
                if data.get("note"):
                    a.note = data["note"]
                a.save()
            n += 1

    return Response({"decision": data["decision"], "count": n})


# ================= 8. REMOVE AN ALLOCATION =================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_remove_allocation(request, allocation_id):
    """Soft close. The row stays so history survives."""
    dept, _setting, err = _dept_for(request)
    if err:
        return err

    a = MentorAllocation.objects.filter(
        id=allocation_id, department=dept, is_active=True
    ).first()
    if not a:
        return Response({"detail": "Active allocation not found."},
                        status=status.HTTP_404_NOT_FOUND)

    ser = RemoveSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    a.close(
        reason=ser.validated_data.get("reason") or "Allocation removed by the HOD",
        by_user=request.user,
    )
    return Response({"detail": "Allocation closed. The record is kept."})


# ================= 9. MENTOR DETAIL =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_mentor_detail(request, mentor_id):
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    mentor = User.objects.filter(id=mentor_id, role="teacher", department=dept).first()
    if not mentor:
        return Response({"detail": "Mentor not found in your department."},
                        status=status.HTTP_404_NOT_FOUND)

    active = MentorAllocation.objects.filter(
        mentor=mentor, department=dept, academic_year=ay, is_active=True
    ).select_related("student", "student__course")

    load = {"total": active.count(), "A": 0, "B": 0, "C": 0}
    for b in active.values_list("grade_band", flat=True):
        if b in ("A", "B", "C"):
            load[b] += 1
    state, message = group_balance(load, setting)

    prev_year = academic_year_choices(2)[1] if len(academic_year_choices(2)) > 1 else None
    previous = MentorAllocation.objects.filter(
        mentor=mentor, department=dept, academic_year=prev_year
    ).count() if prev_year else 0

    return Response({
        "mentor": {
            "id": mentor.id,
            "name": person_name(mentor),
            "employee_id": mentor.employee_id,
            "designation": mentor.get_sub_role_display() if mentor.sub_role else "",
            "department": dept.name,
            "email": mentor.email,
        },
        "academic_year": ay,
        "capacity": {
            "assigned": load["total"],
            "capacity": setting.max_students_per_mentor,
            "available": max(0, setting.max_students_per_mentor - load["total"]),
            "is_full": load["total"] >= setting.max_students_per_mentor,
        },
        "composition": {
            "band_a": load["A"], "band_b": load["B"], "band_c": load["C"],
            "state": state, "message": message,
        },
        "previous_year": {"academic_year": prev_year, "count": previous},
        "students": AllocationSerializer(active, many=True).data,
    })


# ================= 10. ALLOCATION HISTORY =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_history(request):
    """
    Every allocation row ever written for this department, newest first.
    Filters: ?q= &changed_by=hod|advisor|auto &academic_year=
    """
    dept, _setting, err = _dept_for(request)
    if err:
        return err

    qs = MentorAllocation.objects.filter(department=dept).select_related(
        "student", "mentor", "previous_mentor", "proposed_by", "approved_by"
    )

    ay = request.query_params.get("academic_year")
    if ay:
        qs = qs.filter(academic_year=ay)

    src = request.query_params.get("changed_by")
    if src in ("hod", "advisor", "auto", "request"):
        qs = qs.filter(source=src)

    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(student__roll_number__icontains=q)
            | Q(mentor__first_name__icontains=q)
            | Q(mentor__last_name__icontains=q)
            | Q(reason__icontains=q)
        )

    qs = qs.order_by("-updated_at", "-id")[:500]
    return Response({
        "count": qs.count() if hasattr(qs, "count") else len(qs),
        "results": AllocationSerializer(qs, many=True).data,
    })


# ================= 11. SETTINGS =================
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def hod_settings(request):
    dept, setting, err = _dept_for(request)
    if err:
        return err

    if request.method == "PATCH":
        ser = MentoringSettingSerializer(setting, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    return Response(MentoringSettingSerializer(setting).data)


# ================= 12. FILTER OPTIONS =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_filter_options(request):
    """Everything the filter bar needs, so the frontend hardcodes nothing."""
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    from courses.models import Course

    courses = Course.objects.filter(
        id__in=department_students(dept, setting=setting).values_list("course_id", flat=True)
    ).values("id", "name")

    years = sorted(
        set(department_students(dept, setting=setting).exclude(year=None).values_list("year", flat=True))
    )

    mentor_rows, _, _ = _mentor_rows(dept, setting, ay)

    return Response({
        "departments": [
            {"id": d.id, "name": d.name} for d in hod_departments(request.user)
        ],
        "academic_years": academic_year_choices(),
        "courses": list(courses),
        "years": years,
        "bands": [{"value": "A", "label": "Grade A"},
                  {"value": "B", "label": "Grade B"},
                  {"value": "C", "label": "Grade C"}],
        "statuses": [{"value": "pending", "label": "Awaiting approval"},
                     {"value": "active", "label": "Active"},
                     {"value": "none", "label": "No mentor"}],
        "mentors": mentor_rows,
    })


# ==================================================================
# ================= STAFF (MENTOR) ENDPOINTS =======================
# ==================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_my_mentees(request):
    """
    Students the HOD has allocated to the logged-in teacher.
    A mentor cannot add or remove anyone here — this is read-only.

    Filters: ?year= &course= &band= &q= &academic_year=
    """
    from .utils import attendance_map

    ay = _year(request)

    allocs = (
        MentorAllocation.objects
        .filter(mentor=request.user, academic_year=ay, is_active=True)
        .select_related("student", "student__course", "department")
    )

    students = [a.student for a in allocs]
    cgpas = cgpa_map(students)
    att = attendance_map(students)

    f_year = request.query_params.get("year")
    f_course = request.query_params.get("course")
    f_band = request.query_params.get("band")
    q = (request.query_params.get("q") or "").strip().lower()

    rows = []
    for a in allocs:
        s = a.student
        row = {
            "allocation_id": a.id,
            "student_id": s.id,
            "student_name": person_name(s),
            "roll_number": s.roll_number,
            "year": s.year,
            "semester": s.semester,
            "course_name": s.course.name if s.course_id else "",
            "department": a.department.name,
            "grade_band": a.grade_band,
            "cgpa": cgpas.get(s.id),
            "attendance": att.get(s.id),
            "email": s.email,
            "assigned_on": a.start_date,
        }
        if f_year and str(row["year"]) != str(f_year):
            continue
        if f_course and str(s.course_id) != str(f_course):
            continue
        if f_band and row["grade_band"] != f_band:
            continue
        if q and q not in f"{row['student_name']} {row['roll_number'] or ''}".lower():
            continue
        rows.append(row)

    rows.sort(key=lambda r: (r["year"] or 0, r["student_name"]))

    # composition of this mentor's own group, so they can see it is balanced
    load = {"total": len(rows), "A": 0, "B": 0, "C": 0}
    for r in rows:
        if r["grade_band"] in ("A", "B", "C"):
            load[r["grade_band"]] += 1

    dept = allocs[0].department if allocs else request.user.department
    setting = MentoringSetting.for_department(dept) if dept else None
    state, message = group_balance(load, setting) if setting else ("ok", "")

    below = [r for r in rows if r["attendance"] is not None and r["attendance"] < 75]
    watch = sorted(
        [r for r in rows if r["attendance"] is not None and r["attendance"] < 80],
        key=lambda r: r["attendance"],
    )

    cg = [r["cgpa"] for r in rows if r["cgpa"] is not None]
    at = [r["attendance"] for r in rows if r["attendance"] is not None]

    years = {}
    for r in rows:
        y = r["year"]
        d = years.setdefault(y, {"year": y, "count": 0, "A": 0, "B": 0, "C": 0})
        d["count"] += 1
        if r["grade_band"] in ("A", "B", "C"):
            d[r["grade_band"]] += 1

    return Response({
        "academic_year": ay,
        "academic_year_choices": academic_year_choices(),
        "is_mentor": bool(rows) or allocs.exists(),
        "cards": {
            "total_mentees": len(rows),
            "average_attendance": round(sum(at) / len(at)) if at else None,
            "below_75": len(below),
            "average_cgpa": round(sum(cg) / len(cg), 2) if cg else None,
        },
        "composition": {
            "band_a": load["A"], "band_b": load["B"], "band_c": load["C"],
            "state": state, "message": message,
        },
        "by_year": sorted(years.values(), key=lambda d: d["year"] or 0),
        "watchlist": watch[:8],
        "count": len(rows),
        "results": rows,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_student_detail(request, student_id):
    """
    One mentee's read-only profile.
    A mentor may only open a student CURRENTLY allocated to them. That is
    checked here, not by hiding the button in the UI.
    """
    from .utils import attendance_map

    ay = _year(request)

    alloc = (
        MentorAllocation.objects
        .filter(mentor=request.user, student_id=student_id,
                academic_year=ay, is_active=True)
        .select_related("student", "student__course", "department")
        .first()
    )
    if not alloc:
        return Response(
            {"detail": "That student is not currently allocated to you."},
            status=status.HTTP_403_FORBIDDEN,
        )

    s = alloc.student
    cgpa = cgpa_map([s]).get(s.id)
    att = attendance_map([s]).get(s.id)

    # published semester results, newest first — read from your exams app
    from exams.models import ResultEntry, SemesterResult

    semesters = []
    for r in SemesterResult.objects.filter(student=s, is_published=True).order_by("-semester"):
        entries = list(
            ResultEntry.objects.filter(result=r, marks_obtained__isnull=False)
            .select_related("subject")
        )
        if not entries:
            continue
        pct = sum(e.marks_obtained / e.max_marks for e in entries) / len(entries) * 100
        semesters.append({
            "semester": r.semester,
            "percentage": round(pct, 1),
            "subjects": len(entries),
            "backlogs": sum(1 for e in entries if not e.is_pass),
        })

    return Response({
        "academic_year": ay,
        "student": {
            "id": s.id,
            "name": person_name(s),
            "roll_number": s.roll_number,
            "email": s.email,
            "year": s.year,
            "semester": s.semester,
            "course_name": s.course.name if s.course_id else "",
            "department": alloc.department.name,
        },
        "allocation": {
            "grade_band": alloc.grade_band,
            "cgpa_at_allocation": alloc.cgpa_at_allocation,
            "assigned_on": alloc.start_date,
        },
        "academics": {
            "cgpa": cgpa,
            "attendance": att,
            "backlogs": sum(x["backlogs"] for x in semesters),
            "semesters": semesters,
        },
        "note": (
            "Read-only. Meeting records, counselling notes and remarks are not "
            "part of this version."
        ),
    })


# ==================================================================
# ================= STUDENT ENDPOINT ===============================
# ==================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_my_mentor(request):
    """
    The logged-in student's own mentor plus their own progress figures.
    Returns has_mentor:false with a clear message when nothing is allocated,
    so the page can show a proper empty state instead of a blank card.
    """
    from .utils import attendance_map

    ay = _year(request)
    me = request.user

    alloc = (
        MentorAllocation.objects
        .filter(student=me, academic_year=ay, is_active=True)
        .select_related("mentor", "department")
        .first()
    )

    cgpa = cgpa_map([me]).get(me.id)
    att = attendance_map([me]).get(me.id)

    from courses.models import Subject
    from exams.models import ResultEntry

    entries = ResultEntry.objects.filter(
        result__student=me, result__is_published=True, marks_obtained__isnull=False
    )
    backlogs = sum(1 for e in entries if not e.is_pass)

    # the class advisor, from your courses.YearTutor
    from .utils import advisor_for_student
    advisor = advisor_for_student(me)

    progress = {
        "attendance": att,
        "cgpa": cgpa,
        "backlogs": backlogs,
        "semesters_published": entries.values("result__semester").distinct().count(),
    }

    if not alloc:
        return Response({
            "has_mentor": False,
            "academic_year": ay,
            "message": (
                "Your department has not allocated a mentor to you for "
                f"{ay.replace('-', '–')}. Please contact your class advisor "
                "or the department office."
            ),
            "class_advisor": (
                {"name": person_name(advisor), "email": advisor.email}
                if advisor else None
            ),
            "progress": progress,
        })

    m = alloc.mentor
    return Response({
        "has_mentor": True,
        "academic_year": ay,
        "mentor": {
            "id": m.id,
            "name": person_name(m),
            "employee_id": m.employee_id,
            "designation": m.get_sub_role_display() if m.sub_role else "",
            "department": alloc.department.name,
            "email": m.email,
        },
        "assigned_on": alloc.start_date,
        "class_advisor": (
            {"name": person_name(advisor), "email": advisor.email}
            if advisor else None
        ),
        "me": {
            "name": person_name(me),
            "roll_number": me.roll_number,
            "year": me.year,
            "semester": me.semester,
            "course_name": me.course.name if me.course_id else "",
        },
        "progress": progress,
        # deliberately NOT sent: grade_band. A student must never see their band.
    })


# ==================================================================
# ================= STAFF: MESSAGES ================================
# ==================================================================
# Reuses courses.ConversationMessage — the model your LMS already has.
# No second inbox, no new table.

def _my_mentee_ids(user, ay):
    return set(
        MentorAllocation.objects
        .filter(mentor=user, academic_year=ay, is_active=True)
        .values_list("student_id", flat=True)
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_conversations(request):
    """One row per mentee, newest message first, with an unread count."""
    from courses.models import ConversationMessage

    ay = _year(request)
    ids = _my_mentee_ids(request.user, ay)
    if not ids:
        return Response({"count": 0, "unread_total": 0, "results": []})

    msgs = (
        ConversationMessage.objects
        .filter(Q(sender=request.user, receiver_id__in=ids)
                | Q(receiver=request.user, sender_id__in=ids),
                context="mentor")
        .select_related("sender", "receiver")
        .order_by("-created_at")
    )

    latest, unread = {}, {}
    for m in msgs:
        other = m.receiver_id if m.sender_id == request.user.id else m.sender_id
        if other not in latest:
            latest[other] = m
        if m.receiver_id == request.user.id and not m.is_read:
            unread[other] = unread.get(other, 0) + 1

    students = {s.id: s for s in User.objects.filter(id__in=ids).select_related("course")}

    rows = []
    for sid, s in students.items():
        m = latest.get(sid)
        rows.append({
            "student_id": sid,
            "student_name": person_name(s),
            "roll_number": s.roll_number,
            "year": s.year,
            "course_name": s.course.name if s.course_id else "",
            "last_message": (m.text[:120] if m else ""),
            "last_from_me": (m.sender_id == request.user.id) if m else False,
            "last_at": m.created_at if m else None,
            "unread": unread.get(sid, 0),
        })

    rows.sort(key=lambda r: (r["last_at"] is None, -(r["last_at"].timestamp() if r["last_at"] else 0)))
    return Response({
        "count": len(rows),
        "unread_total": sum(unread.values()),
        "results": rows,
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def staff_thread(request, student_id):
    """
    Read or send messages to ONE mentee.
    A mentor may only message a student currently allocated to them —
    checked here, not by hiding a button.
    """
    from courses.models import ConversationMessage

    ay = _year(request)
    if student_id not in _my_mentee_ids(request.user, ay):
        return Response({"detail": "That student is not currently allocated to you."},
                        status=status.HTTP_403_FORBIDDEN)

    student = User.objects.filter(id=student_id).select_related("course").first()

    if request.method == "POST":
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "Message cannot be empty."},
                            status=status.HTTP_400_BAD_REQUEST)
        m = ConversationMessage.objects.create(
            sender=request.user, receiver=student, text=text, context="mentor"
        )
        notify([student], f"Message from {person_name(request.user)}", text)
        return Response({
            "id": m.id, "text": m.text, "from_me": True,
            "created_at": m.created_at, "is_read": m.is_read,
        }, status=status.HTTP_201_CREATED)

    qs = ConversationMessage.objects.filter(
        Q(sender=request.user, receiver=student) | Q(sender=student, receiver=request.user),
        context="mentor",
    ).order_by("created_at")

    # opening the thread marks their messages read
    qs.filter(receiver=request.user, is_read=False).update(is_read=True)

    return Response({
        "student": {
            "id": student.id,
            "name": person_name(student),
            "roll_number": student.roll_number,
            "year": student.year,
            "course_name": student.course.name if student.course_id else "",
            "email": student.email,
        },
        "messages": [{
            "id": m.id,
            "text": m.text,
            "from_me": m.sender_id == request.user.id,
            "created_at": m.created_at,
            "is_read": m.is_read,
        } for m in qs],
    })


# ==================================================================
# ================= STAFF: GROUPS ==================================
# ==================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_groups(request):
    """
    Groups are saved queries over this mentor's own mentees, not member lists,
    so they cannot drift out of date when the HOD moves a student.

    `visible_to_student` is false for anything derived from performance — a
    student must never read "you are in: attendance below 80%".
    """
    from .utils import attendance_map

    ay = _year(request)
    allocs = (
        MentorAllocation.objects
        .filter(mentor=request.user, academic_year=ay, is_active=True)
        .select_related("student")
    )
    students = [a.student for a in allocs]
    if not students:
        return Response({"groups": [], "academic_year": ay})

    att = attendance_map(students)
    years = sorted({s.year for s in students if s.year})

    groups = [{
        "key": "all",
        "name": "All my mentees",
        "why": "Everyone assigned to you",
        "count": len(students),
        "visible_to_student": True,
    }]
    for y in years:
        n = sum(1 for s in students if s.year == y)
        groups.append({
            "key": f"year-{y}",
            "name": f"{YEAR_LABEL.get(y, y)} Year mentees",
            "why": "Year group",
            "count": n,
            "visible_to_student": True,
        })

    low = [s for s in students if att.get(s.id) is not None and att[s.id] < 80]
    if low:
        groups.append({
            "key": "low-attendance",
            "name": "Attendance below 80%",
            "why": "Updates on its own",
            "count": len(low),
            "visible_to_student": False,
        })

    return Response({"academic_year": ay, "groups": groups})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_broadcast(request):
    """
    Send one message to a whole group. Fans out to individual
    ConversationMessage rows, so a student who changes mentor next month
    keeps what they already received.
    """
    from .utils import attendance_map

    ay = _year(request)
    key = request.data.get("group") or "all"
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"detail": "Message cannot be empty."},
                        status=status.HTTP_400_BAD_REQUEST)

    allocs = (
        MentorAllocation.objects
        .filter(mentor=request.user, academic_year=ay, is_active=True)
        .select_related("student")
    )
    students = [a.student for a in allocs]

    if key.startswith("year-"):
        y = int(key.split("-")[1])
        students = [s for s in students if s.year == y]
    elif key == "low-attendance":
        att = attendance_map(students)
        students = [s for s in students if att.get(s.id) is not None and att[s.id] < 80]

    if not students:
        return Response({"detail": "That group has no students."},
                        status=status.HTTP_400_BAD_REQUEST)

    labels = {"all": "All my mentees", "low-attendance": "Attendance below 80%"}
    label = labels.get(key) or (
        f"{YEAR_LABEL.get(int(key.split('-')[1]), '')} Year mentees"
        if key.startswith("year-") else key
    )

    dept = allocs[0].department

    with transaction.atomic():
        bc = MentorBroadcast.objects.create(
            mentor=request.user, department=dept, academic_year=ay,
            group_key=key, group_label=label, text=text,
        )
        MentorBroadcastRecipient.objects.bulk_create([
            MentorBroadcastRecipient(broadcast=bc, student=s) for s in students
        ])

    notify(students, f"Announcement from {person_name(request.user)}", text)

    return Response({"sent": len(students), "group": key, "broadcast_id": bc.id},
                    status=status.HTTP_201_CREATED)


# ==================================================================
# ================= STUDENT: MESSAGES ==============================
# ==================================================================

def _my_mentor(user, ay):
    return (
        MentorAllocation.objects
        .filter(student=user, academic_year=ay, is_active=True)
        .select_related("mentor")
        .first()
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def student_thread(request):
    """
    A student has exactly one conversation — with their current mentor.
    No conversation list is needed, so none is built.
    """
    from courses.models import ConversationMessage

    ay = _year(request)
    alloc = _my_mentor(request.user, ay)
    if not alloc:
        return Response(
            {"detail": "You do not have a mentor allocated yet."},
            status=status.HTTP_403_FORBIDDEN,
        )

    mentor = alloc.mentor

    if request.method == "POST":
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "Message cannot be empty."},
                            status=status.HTTP_400_BAD_REQUEST)
        m = ConversationMessage.objects.create(
            sender=request.user, receiver=mentor, text=text, context="mentor"
        )
        notify([mentor], f"Message from {person_name(request.user)}", text)
        return Response({
            "id": m.id, "text": m.text, "from_me": True,
            "created_at": m.created_at,
        }, status=status.HTTP_201_CREATED)

    qs = ConversationMessage.objects.filter(
        Q(sender=request.user, receiver=mentor) | Q(sender=mentor, receiver=request.user),
        context="mentor",
    ).order_by("created_at")

    qs.filter(receiver=request.user, is_read=False).update(is_read=True)

    return Response({
        "mentor": {
            "id": mentor.id,
            "name": person_name(mentor),
            "designation": mentor.get_sub_role_display() if mentor.sub_role else "",
            "email": mentor.email,
        },
        "messages": [{
            "id": m.id,
            "text": m.text,
            "from_me": m.sender_id == request.user.id,
            "created_at": m.created_at,
        } for m in qs],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_announcements(request):
    """
    Group announcements this student received.

    The group LABEL is deliberately not sent. A student must never read
    "you are in: attendance below 80%" about themselves.
    """
    ay = _year(request)
    alloc = _my_mentor(request.user, ay)
    if not alloc:
        return Response({"count": 0, "unread": 0, "mentor_name": "", "results": []})

    rows = (
        MentorBroadcastRecipient.objects
        .filter(student=request.user, broadcast__mentor=alloc.mentor)
        .select_related("broadcast")
        .order_by("-broadcast__created_at")
    )

    out = [{
        "id": r.id,
        "text": r.broadcast.text,
        "created_at": r.broadcast.created_at,
        "is_read": r.is_read,
        "recipients": r.broadcast.recipients.count(),
    } for r in rows]

    unread = sum(1 for r in out if not r["is_read"])
    rows.filter(is_read=False).update(is_read=True)

    return Response({
        "count": len(out),
        "unread": unread,
        "mentor_name": person_name(alloc.mentor),
        "results": out,
    })



# ================= HOD — CHANGE REQUESTS =================
def _change_request_qs(dept, ay):
    return (
        MentorChangeRequest.objects
        .filter(department=dept, academic_year=ay)
        .select_related("student", "student__course", "current_mentor",
                        "advisor", "new_mentor", "raised_by", "decided_by")
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_change_requests(request):
    """
    The HOD queue. ?bucket=waiting|advisor|decided

    'waiting' is what the HOD must act on. 'advisor' is visible but not
    theirs yet, and confidential ones never appear in it because they
    never had an advisor step.
    """
    dept, _setting, err = _dept_for(request)
    if err:
        return err

    ay = _year(request)
    qs = _change_request_qs(dept, ay)

    counts = {
        "waiting": qs.filter(status="hod").count(),
        "with_advisor": qs.filter(status="advisor").count(),
        "confidential": qs.filter(status="hod", is_confidential=True).count(),
        "decided": qs.filter(status__in=("approved", "rejected")).count(),
        "resolved_by_advisor": qs.filter(status="resolved").count(),
    }

    bucket = request.query_params.get("bucket", "waiting")
    if bucket == "advisor":
        rows = qs.filter(status="advisor")
    elif bucket == "decided":
        rows = qs.filter(status__in=("approved", "rejected", "resolved", "withdrawn"))
    else:
        rows = qs.filter(status="hod")

    return Response({
        "academic_year": ay,
        "department": dept.name,
        "counts": counts,
        "bucket": bucket,
        "results": ChangeRequestSerializer(rows, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_change_request_detail(request, request_id):
    """One request plus the mentors it can be moved to."""
    dept, setting, err = _dept_for(request)
    if err:
        return err

    ay = _year(request)
    cr = (
        _change_request_qs(dept, ay)
        .filter(id=request_id)
        .first()
        or MentorChangeRequest.objects
        .select_related("student", "student__course", "current_mentor",
                        "advisor", "new_mentor", "raised_by", "decided_by")
        .filter(id=request_id, department=dept)
        .first()
    )
    if not cr:
        return Response({"detail": "Change request not found."},
                        status=status.HTTP_404_NOT_FOUND)

    rows, mentors, loads = _mentor_rows(dept, setting, cr.academic_year)

    # the current mentor cannot be the answer
    options = [r for r in rows if r["id"] != cr.current_mentor_id]
    options.sort(key=lambda r: (-r["available"], r["name"]))

    band = (
        MentorAllocation.objects
        .filter(student=cr.student, academic_year=cr.academic_year, is_active=True)
        .values_list("grade_band", flat=True)
        .first()
    ) or ""

    return Response({
        "request": ChangeRequestSerializer(cr).data,
        "student_band": band,
        "capacity": setting.max_students_per_mentor,
        "mentor_options": options,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hod_decide_change_request(request, request_id):
    """
    Approve (move the student) or reject (mentor stays).

    Approving mirrors hod_assign: close the old allocation, open a new one
    with source='request'. Both rows stay, so Allocation History shows the
    move with no change to that page.
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err

    cr = (
        MentorChangeRequest.objects
        .select_related("student", "current_mentor")
        .filter(id=request_id, department=dept, status="hod")
        .first()
    )
    if not cr:
        return Response(
            {"detail": "No request is waiting on you with that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    ser = DecideChangeRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    ay = cr.academic_year

    # ---------- reject ----------
    if data["decision"] == "reject":
        cr.status = "rejected"
        cr.decided_by = request.user
        cr.decision_note = data["note"].strip()
        cr.decided_at = timezone.now()
        cr.save()

        notify(
            [cr.raised_by or cr.student],
            "Mentor change request declined",
            f"Your request about {person_name(cr.current_mentor)} was declined. "
            f"Reason given: {cr.decision_note}",
        )
        return Response({
            "decision": "reject",
            "request": ChangeRequestSerializer(cr).data,
        })

    # ---------- approve ----------
    new_mentor = User.objects.filter(
        id=data["new_mentor_id"], role="teacher", department=dept, is_active=True
    ).first()
    if not new_mentor:
        return Response({"detail": "Mentor not found in your department."},
                        status=status.HTTP_400_BAD_REQUEST)

    if new_mentor.id == cr.current_mentor_id:
        return Response(
            {"detail": "That is the mentor the student asked to move away from."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _, mentors, loads = _mentor_rows(dept, setting, ay)
    load = loads.get(new_mentor.id, {"total": 0, "A": 0, "B": 0, "C": 0})
    after = load["total"] + 1

    if after > setting.max_students_per_mentor and not data["override"]:
        return Response({
            "warning": "capacity",
            "message": (
                f"{person_name(new_mentor)} would hold {after} of "
                f"{setting.max_students_per_mentor}. Send override=true to continue."
            ),
            "before": load["total"], "after": after,
            "capacity": setting.max_students_per_mentor,
        }, status=status.HTTP_409_CONFLICT)

    with transaction.atomic():
        old = MentorAllocation.objects.select_for_update().filter(
            student=cr.student, academic_year=ay
        ).filter(Q(is_active=True) | Q(status="pending")).first()

        previous_mentor = old.mentor if old else cr.current_mentor
        band = old.grade_band if old else ""
        cgpa = old.cgpa_at_allocation if old else None

        if old:
            old.close(reason="Change request approved by the HOD", by_user=request.user)

        allocation = MentorAllocation.objects.create(
            student=cr.student, mentor=new_mentor, department=dept,
            academic_year=ay,
            grade_band=band, cgpa_at_allocation=cgpa,
            status="active", is_active=True, source="request",
            approved_by=request.user,
            previous_mentor=previous_mentor,
            reason=f"Change request approved — {cr.get_reason_display()}",
            note=(data.get("note") or "").strip(),
        )

        cr.status = "approved"
        cr.new_mentor = new_mentor
        cr.new_allocation = allocation
        cr.decided_by = request.user
        cr.decision_note = (data.get("note") or "").strip()
        cr.decided_at = timezone.now()
        cr.save()

    notify(
        [cr.student],
        "Your mentor has changed",
        f"Your mentor is now {person_name(new_mentor)}.",
    )
    notify(
        [new_mentor],
        "A new mentee has been assigned to you",
        f"{person_name(cr.student)} is now one of your mentees.",
    )

    return Response({
        "decision": "approve",
        "request": ChangeRequestSerializer(cr).data,
        "allocation": AllocationSerializer(allocation).data,
    }, status=status.HTTP_201_CREATED)



# ==================================================================
# ================= STUDENT: CHANGE REQUEST ========================
# ==================================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def student_change_request(request):
    """
    GET  — the student's own request, plus what they need to raise one.
    POST — raise one. {"reason": "timing", "detail": "..."}

    Scoped to raised_role='student' throughout, so a request their MENTOR
    raised about them never appears here.
    """
    from .utils import advisor_for_student

    ay = _year(request)
    me = request.user

    alloc = (
        MentorAllocation.objects
        .filter(student=me, academic_year=ay, is_active=True)
        .select_related("mentor", "department")
        .first()
    )

    # ---------- POST ----------
    if request.method == "POST":
        if not alloc:
            return Response(
                {"detail": "You do not have a mentor allocated yet, so there is "
                           "nothing to change."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = CreateChangeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        already = MentorChangeRequest.objects.filter(
            student=me, academic_year=ay,
            status__in=MentorChangeRequest.OPEN_STATUSES,
        ).first()
        if already:
            return Response(
                {"detail": "You already have a request in progress. Withdraw it "
                           "before raising another."},
                status=status.HTTP_409_CONFLICT,
            )

        setting = MentoringSetting.for_department(alloc.department)

        cr = MentorChangeRequest(
            student=me,
            current_mentor=alloc.mentor,
            department=alloc.department,
            academic_year=ay,
            raised_by=me,
            raised_role="student",
            reason=data["reason"],
            detail=(data.get("detail") or "").strip(),
        )
        cr.resolve_route(setting)
        cr.save()

        if cr.status == "advisor":
            notify(
                [cr.advisor],
                "A student has asked to change mentor",
                f"{person_name(me)} raised a mentor change request. "
                f"Review it on My Mentees, Change Requests.",
            )
        elif alloc.department.hod_id:
            notify(
                [alloc.department.hod],
                "A mentor change request needs your decision",
                f"A request from {person_name(me)} is waiting on you.",
            )

        return Response(
            ChangeRequestSerializer(cr).data, status=status.HTTP_201_CREATED
        )

    # ---------- GET ----------
    mine = MentorChangeRequest.objects.filter(
        student=me, academic_year=ay, raised_role="student"
    ).select_related("current_mentor", "advisor", "new_mentor",
                     "raised_by", "decided_by")

    open_one = mine.filter(status__in=MentorChangeRequest.OPEN_STATUSES).first()
    past = mine.exclude(status__in=MentorChangeRequest.OPEN_STATUSES)[:5]

    advisor = advisor_for_student(me) if alloc else None
    setting = MentoringSetting.for_department(alloc.department) if alloc else None

    reasons = [
        {"value": v, "label": label}
        for v, label in MentorChangeRequest.REASON_CHOICES
        if v not in MentorChangeRequest.STAFF_ONLY_REASONS
    ]

    if not alloc:
        can_raise, why = False, "You do not have a mentor allocated yet."
    elif open_one:
        can_raise, why = False, "You already have a request in progress."
    else:
        can_raise, why = True, ""

    return Response({
        "academic_year": ay,
        "has_mentor": bool(alloc),
        "current_mentor": (
            {"id": alloc.mentor_id,
             "name": person_name(alloc.mentor),
             "assigned_on": alloc.start_date}
            if alloc else None
        ),
        "can_raise": can_raise,
        "why_not": why,
        "reasons": reasons,
        "confidential_reasons": list(MentorChangeRequest.CONFIDENTIAL_REASONS),
        "advisor": (
            {
                "name": person_name(advisor),
                "is_my_mentor": bool(alloc and advisor.id == alloc.mentor_id),
            }
            if advisor else None
        ),
        "advisor_step_enabled": bool(setting and setting.route_via_advisor),
        "open_request": ChangeRequestSerializer(open_one).data if open_one else None,
        "past_requests": ChangeRequestSerializer(past, many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_withdraw_change_request(request, request_id):
    """Cancel an open request. Frees the one-open-request rule immediately."""
    cr = MentorChangeRequest.objects.filter(
        id=request_id, student=request.user, raised_role="student",
        status__in=MentorChangeRequest.OPEN_STATUSES,
    ).first()
    if not cr:
        return Response(
            {"detail": "No open request of yours with that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    cr.status = "withdrawn"
    cr.decided_at = timezone.now()
    cr.save()

    return Response({
        "detail": "Request withdrawn. You can raise a new one whenever you need to.",
        "request": ChangeRequestSerializer(cr).data,
    })


# ==================================================================
# ================= CLASS ADVISOR: CHANGE REQUESTS =================
# ==================================================================

def _advisor_qs(user, ay):
    """
    Requests sitting with this teacher as class advisor.

    Filtered on advisor=user, so a teacher only ever sees requests the
    routing actually assigned to them. is_confidential is excluded as a
    second line of defence — a sensitive request should never have been
    given an advisor in the first place.
    """
    return (
        MentorChangeRequest.objects
        .filter(advisor=user, academic_year=ay, is_confidential=False)
        .select_related("student", "student__course", "current_mentor",
                        "new_mentor", "raised_by", "decided_by")
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_change_requests(request):
    """?bucket=waiting|forwarded|resolved — the class advisor queue."""
    ay = _year(request)
    qs = _advisor_qs(request.user, ay)

    counts = {
        "waiting": qs.filter(status="advisor").count(),
        "forwarded": qs.filter(status__in=("hod", "approved", "rejected")).count(),
        "resolved": qs.filter(status="resolved").count(),
    }

    bucket = request.query_params.get("bucket", "waiting")
    if bucket == "forwarded":
        rows = qs.filter(status__in=("hod", "approved", "rejected"))
    elif bucket == "resolved":
        rows = qs.filter(status__in=("resolved", "withdrawn"))
    else:
        rows = qs.filter(status="advisor")

    return Response({
        "academic_year": ay,
        "is_advisor": qs.exists() or bool(counts["waiting"]),
        "counts": counts,
        "bucket": bucket,
        "results": ChangeRequestSerializer(rows, many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_change_request_detail(request, request_id):
    ay = _year(request)
    cr = (
        _advisor_qs(request.user, ay).filter(id=request_id).first()
        or MentorChangeRequest.objects
        .filter(id=request_id, advisor=request.user, is_confidential=False)
        .select_related("student", "student__course", "current_mentor",
                        "new_mentor", "raised_by", "decided_by")
        .first()
    )
    if not cr:
        return Response({"detail": "Change request not found."},
                        status=status.HTTP_404_NOT_FOUND)

    return Response({"request": ChangeRequestSerializer(cr).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_act_change_request(request, request_id):
    """
    forward — passes it to the HOD with your note.
    resolve — closes it, the mentor stays as they are.

    A note is required either way, because the student is shown it.
    The advisor never picks a replacement mentor; that is the HOD's call.
    """
    cr = (
        MentorChangeRequest.objects
        .select_related("student", "current_mentor", "department")
        .filter(id=request_id, advisor=request.user,
                status="advisor", is_confidential=False)
        .first()
    )
    if not cr:
        return Response(
            {"detail": "No request is waiting on you with that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    ser = AdvisorActSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    cr.advisor_note = data["note"]
    cr.advisor_acted_at = timezone.now()

    if data["action"] == "forward":
        cr.status = "hod"
        cr.save()
        if cr.department.hod_id:
            notify(
                [cr.department.hod],
                "A mentor change request needs your decision",
                f"{person_name(request.user)} forwarded a request from "
                f"{person_name(cr.student)}.",
            )
        notify(
            [cr.student],
            "Your request went to the HOD",
            f"{person_name(request.user)} reviewed it and passed it on. "
            f"Their note: {cr.advisor_note}",
        )
    else:
        cr.status = "resolved"
        cr.save()
        notify(
            [cr.student],
            "Your mentor stays the same",
            f"{person_name(request.user)} resolved your request without a "
            f"change. Their note: {cr.advisor_note}",
        )

    return Response({
        "action": data["action"],
        "request": ChangeRequestSerializer(cr).data,
    })




# ==================================================================
# ================= MENTOR-RAISED CHANGE REQUESTS ==================
# ==================================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def staff_my_change_requests(request):
    """
    GET  — requests this teacher raised about their own mentees, plus the
           mentees they can still raise one for.
    POST — raise one. {"student_id": 4, "reason": "capacity", "detail": "..."}

    Goes straight to the HOD: there is no advisor step when a mentor asks.
    The student is never told a request exists — only that they moved, if
    the HOD approves it.
    """
    ay = _year(request)
    me = request.user

    mine = (
        MentorChangeRequest.objects
        .filter(raised_by=me, raised_role="mentor", academic_year=ay)
        .select_related("student", "student__course", "current_mentor",
                        "new_mentor", "decided_by")
    )

    # ---------- POST ----------
    if request.method == "POST":
        ser = MentorRaiseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        alloc = (
            MentorAllocation.objects
            .filter(mentor=me, student_id=data["student_id"],
                    academic_year=ay, is_active=True)
            .select_related("student", "department")
            .first()
        )
        if not alloc:
            return Response(
                {"detail": "That student is not currently one of your mentees."},
                status=status.HTTP_403_FORBIDDEN,
            )

        already = MentorChangeRequest.objects.filter(
            student=alloc.student, academic_year=ay,
            status__in=MentorChangeRequest.OPEN_STATUSES,
        ).first()
        if already:
            return Response(
                {"detail": f"{person_name(alloc.student)} already has a request "
                           f"in progress."},
                status=status.HTTP_409_CONFLICT,
            )

        setting = MentoringSetting.for_department(alloc.department)

        cr = MentorChangeRequest(
            student=alloc.student,
            current_mentor=me,
            department=alloc.department,
            academic_year=ay,
            raised_by=me,
            raised_role="mentor",
            reason=data["reason"],
            detail=(data.get("detail") or "").strip(),
        )
        cr.resolve_route(setting)   # always "hod" for raised_role="mentor"
        cr.save()

        if alloc.department.hod_id:
            notify(
                [alloc.department.hod],
                "A mentor has asked for a mentee to be moved",
                f"{person_name(me)} raised a request about "
                f"{person_name(alloc.student)}.",
            )

        return Response(ChangeRequestSerializer(cr).data,
                        status=status.HTTP_201_CREATED)

    # ---------- GET ----------
    open_student_ids = set(
        MentorChangeRequest.objects
        .filter(academic_year=ay, status__in=MentorChangeRequest.OPEN_STATUSES)
        .values_list("student_id", flat=True)
    )

    mentees = []
    for a in (MentorAllocation.objects
              .filter(mentor=me, academic_year=ay, is_active=True)
              .select_related("student")
              .order_by("student__first_name")):
        mentees.append({
            "id": a.student_id,
            "name": person_name(a.student),
            "roll_number": a.student.roll_number,
            "year": a.student.year,
            # true when ANY open request exists for them, whoever raised it —
            # the mentor is not told which, only that they cannot raise one
            "has_open_request": a.student_id in open_student_ids,
        })

    reasons = [
        {"value": v, "label": label}
        for v, label in MentorChangeRequest.REASON_CHOICES
        if v not in MentorChangeRequest.CONFIDENTIAL_REASONS
    ]

    load = len(mentees)
    setting = None
    first = MentorAllocation.objects.filter(
        mentor=me, academic_year=ay, is_active=True
    ).select_related("department").first()
    if first:
        setting = MentoringSetting.for_department(first.department)

    return Response({
        "academic_year": ay,
        "my_load": load,
        "capacity": setting.max_students_per_mentor if setting else None,
        "over_capacity_by": (
            max(0, load - setting.max_students_per_mentor) if setting else 0
        ),
        "mentees": mentees,
        "reasons": reasons,
        "open": ChangeRequestSerializer(
            mine.filter(status__in=MentorChangeRequest.OPEN_STATUSES), many=True
        ).data,
        "decided": ChangeRequestSerializer(
            mine.exclude(status__in=MentorChangeRequest.OPEN_STATUSES)[:10], many=True
        ).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_withdraw_change_request(request, request_id):
    """Cancel a request you raised, while it is still open."""
    cr = MentorChangeRequest.objects.filter(
        id=request_id, raised_by=request.user, raised_role="mentor",
        status__in=MentorChangeRequest.OPEN_STATUSES,
    ).first()
    if not cr:
        return Response(
            {"detail": "No open request of yours with that id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    cr.status = "withdrawn"
    cr.decided_at = timezone.now()
    cr.save()

    return Response({
        "detail": "Request withdrawn.",
        "request": ChangeRequestSerializer(cr).data,
    })