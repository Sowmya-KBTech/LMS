from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q
from datetime import timedelta
from django.utils import timezone

from courses.models import Enrollment, TeachingAssignment

from .models import (
    TimeSlot, TimetableEntry, TimetableApproval, Room,
    ActivityType, ClassActivity, Semester, Holiday,
)
from .serializers import (
    TimeSlotSerializer, TimetableEntrySerializer, RoomSerializer,
    ActivityTypeSerializer, ClassActivitySerializer,
    SemesterSerializer, HolidaySerializer,
)

from .services import availability, validate_submission, _locked_entries
from .solver import autofill


# ---------- tunables ----------
# How long an untouched DRAFT keeps its hold on the slots it occupies.
# One number, one place — read wherever a draft's freshness is judged.
HOLD_HOURS = 48


# ---------- role helpers ----------
def is_admin(user):
    return getattr(user, "role", "") == "admin" or bool(getattr(user, "is_staff", False))


def is_teacher(user):
    return getattr(user, "role", "") == "teacher"


# ---------- HOD scoping (mirrors users/views.py) ----------
def _hod_course_ids(user):
    """
    Course IDs that belong to this user's department(s) as HOD.
    Derived from the department's students (same approach as users.views).
    Returns [] if the user is not an HOD of any department.
    """
    from users.models import Department, User
    dept_ids = list(
        Department.objects.filter(hod=user).values_list("id", flat=True)
    )
    if not dept_ids:
        return []
    return list(
        User.objects.filter(role="student", department_id__in=dept_ids)
        .exclude(course__isnull=True)
        .values_list("course_id", flat=True)
        .distinct()
    )


def is_hod(user):
    """True if this user is the HOD of at least one department."""
    from users.models import Department
    return Department.objects.filter(hod=user).exists()


def _assignment_course_id(assignment):
    """Course id of a TeachingAssignment (direct FK, or via its year)."""
    cid = getattr(assignment, "course_id", None)
    if cid:
        return cid
    year = getattr(assignment, "year", None)
    return getattr(year, "course_id", None)


def _can_edit_timetable(user, assignment):
    """
    Admin: any class.
    HOD:   only classes whose course is in their own department.
    """
    if is_admin(user):
        return True
    return _assignment_course_id(assignment) in _hod_course_ids(user)


# ---------- entry helpers ----------
def _entry_class(entry):
    """
    (year_id, semester, course_id) for any TimetableEntry — lecture or activity.

    An activity has no assignment, so nothing may reach through
    entry.assignment without checking class_activity first.
    """
    if entry.class_activity_id:
        ca = entry.class_activity
        return ca.year_id, ca.semester, ca.year.course_id
    a = entry.assignment
    return a.year_id, a.subject.semester, a.course_id


# ---------- approval helpers ----------
def _class_key(assignment):
    """(year_id, semester) — the class a timetable entry belongs to."""
    return assignment.year_id, assignment.subject.semester


def _get_approval(year_id, semester):
    return TimetableApproval.objects.filter(year_id=year_id, semester=semester).first()


def _ensure_approval(assignment):
    obj, _ = TimetableApproval.objects.get_or_create(
        year_id=assignment.year_id,
        semester=assignment.subject.semester,
        defaults={
            "course_id": assignment.course_id,
            "status": TimetableApproval.Status.DRAFT,
        },
    )
    # Layer 2: the HOD is working — keep their holds alive.
    obj.last_active = timezone.now()
    obj.save(update_fields=["last_active"])
    return obj


def _ensure_approval_for_class(year_id, semester, course_id=None):
    """
    Same as _ensure_approval, but takes the class directly instead of an
    assignment. Activities have no TeachingAssignment behind them, so they
    can't use the version above.
    """
    obj, _ = TimetableApproval.objects.get_or_create(
        year_id=year_id,
        semester=semester,
        defaults={
            "course_id": course_id,
            "status": TimetableApproval.Status.DRAFT,
        },
    )
    obj.last_active = timezone.now()
    obj.save(update_fields=["last_active"])
    return obj


def _reset_to_draft(approval):
    approval.status = TimetableApproval.Status.DRAFT
    approval.submitted_by = None
    approval.submitted_at = None
    approval.reviewed_by = None
    approval.reviewed_at = None
    approval.remark = ""
    approval.save()


def _approved_filter(qs):
    """
    Limit a queryset of TimetableEntry to classes that are APPROVED.

    Matches activities too. Without the class_activity half, an approved
    timetable's Library and Sports periods are invisible to the students
    and teachers who are supposed to attend them.
    """
    pairs = list(
        TimetableApproval.objects
        .filter(status=TimetableApproval.Status.APPROVED)
        .values_list("year_id", "semester")
    )
    if not pairs:
        return qs.none()
    q = Q()
    for yid, sem in pairs:
        q |= Q(assignment__year_id=yid, assignment__subject__semester=sem)
        q |= Q(class_activity__year_id=yid, class_activity__semester=sem)
    return qs.filter(q)


# =====================================================
#  TIME SLOTS  (bell schedule)  — admin only (college-wide)
# =====================================================
class TimeSlotListCreate(generics.ListCreateAPIView):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can edit periods.")
        serializer.save()


class TimeSlotDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can edit periods.")
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can edit periods.")
        instance.delete()


# =====================================================
#  TIMETABLE ENTRIES
# =====================================================
class TimetableListCreate(generics.ListCreateAPIView):
    serializer_class = TimetableEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        qs = TimetableEntry.objects.select_related(
            "assignment", "assignment__course", "assignment__year",
            "assignment__subject", "assignment__teacher", "time_slot", "room",
            "class_activity", "class_activity__activity",
        )

        scope = params.get("scope")

        # An activity has no assignment, so it must be matched on class_activity
        # or it will vanish from the grid the moment it is saved.
        year_id = params.get("year")
        semester = params.get("semester")

        if year_id or semester:
            if year_id and semester:
                qs = qs.filter(
                    Q(assignment__year_id=year_id, assignment__subject__semester=semester)
                    | Q(class_activity__year_id=year_id, class_activity__semester=semester)
                )
            elif year_id:
                qs = qs.filter(
                    Q(assignment__year_id=year_id)
                    | Q(class_activity__year_id=year_id)
                )
            else:
                qs = qs.filter(
                    Q(assignment__subject__semester=semester)
                    | Q(class_activity__semester=semester)
                )

            if not is_admin(user) and is_hod(user):
                mine = _hod_course_ids(user)
                qs = qs.filter(
                    Q(assignment__course_id__in=mine)
                    | Q(class_activity__year__course_id__in=mine)
                )

            return qs

        # ---- TEACHER: own classes, APPROVED only ----
        if scope == "teacher" or (scope is None and is_teacher(user) and not is_hod(user)):
            return _approved_filter(
                qs.filter(
                    Q(assignment__teacher=user)
                    | Q(class_activity__teacher=user)
                )
            )

        # ---- STUDENT: from enrollment, fall back to course/year/semester ----
        enrolled_ids = Enrollment.objects.filter(
            student=user
        ).values_list("teaching_assignment_id", flat=True)

        if enrolled_ids:
            enrolled_ids = list(enrolled_ids)
            # An enrolled student sees their lectures AND their class's
            # activities. The activities are found through the class the
            # enrolments point at, not through the enrolment rows.
            classes = set(
                TeachingAssignment.objects
                .filter(id__in=enrolled_ids)
                .values_list("year_id", "subject__semester")
            )
            q = Q(assignment_id__in=enrolled_ids)
            for yid, sem in classes:
                q |= Q(class_activity__year_id=yid, class_activity__semester=sem)
            return _approved_filter(qs.filter(q))

        if user.course_id and user.year and user.semester:
            return _approved_filter(qs.filter(
                Q(
                    assignment__course=user.course,
                    assignment__year__year_number=user.year,
                    assignment__subject__semester=user.semester,
                )
                | Q(
                    class_activity__year__course=user.course,
                    class_activity__year__year_number=user.year,
                    class_activity__semester=user.semester,
                )
            ))

        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        day = serializer.validated_data["day_of_week"]
        slot = serializer.validated_data["time_slot"]
        kind = serializer.validated_data.get("kind", TimetableEntry.Kind.CLASS)

        assignment = serializer.validated_data.get("assignment")
        class_activity = serializer.validated_data.get("class_activity")

        # ---- work out which class this cell belongs to, and who (if anyone)
        #      is standing at the front of the room ----
        if kind == TimetableEntry.Kind.ACTIVITY:
            if not class_activity:
                raise ValidationError("An activity entry needs a class_activity.")
            year_id = class_activity.year_id
            semester = class_activity.semester
            teacher = class_activity.teacher          # may be None — that's fine
            course_id = class_activity.year.course_id
        else:
            if not assignment:
                raise ValidationError("A class entry needs an assignment.")
            year_id = assignment.year_id
            semester = assignment.subject.semester
            teacher = assignment.teacher
            course_id = assignment.course_id

        # ---- permission: HODs only touch their own department ----
        if not is_admin(user):
            if course_id not in _hod_course_ids(user):
                raise PermissionDenied("This class is not in your department.")

        # ---- a submitted timetable is locked ----
        approval = _get_approval(year_id, semester)
        if approval and approval.status == TimetableApproval.Status.SUBMITTED and not is_admin(user):
            raise PermissionDenied(
                "This timetable is submitted for approval and locked. "
                "Wait for the admin to review it."
            )

        same_slot = TimetableEntry.objects.filter(day_of_week=day, time_slot=slot)

        # ---- 1) CLASS clash: one thing per cell, whatever kind it is ----
        # An activity and a lecture cannot share a cell either.
        my_class = same_slot.filter(
            Q(assignment__year_id=year_id, assignment__subject__semester=semester)
            | Q(class_activity__year_id=year_id, class_activity__semester=semester)
        )
        if my_class.exists():
            raise ValidationError("This class already has something in that period.")

        # ---- which timetables are allowed to block us? ----
        # Submitted / approved always block. An ACTIVE draft blocks too — that's
        # Layer 2, so two HODs can't both build the same cell and only find out
        # at submit. An abandoned draft lapses after HOLD_HOURS.
        cutoff = timezone.now() - timedelta(hours=HOLD_HOURS)
        blocking_pairs = TimetableApproval.objects.filter(
            Q(status__in=[
                TimetableApproval.Status.SUBMITTED,
                TimetableApproval.Status.APPROVED,
            ])
            | Q(status=TimetableApproval.Status.DRAFT, last_active__gt=cutoff)
        ).values_list("year_id", "semester")

        blocking_q = Q()
        for yid, sem in blocking_pairs:
            blocking_q |= (
                Q(assignment__year_id=yid, assignment__subject__semester=sem)
                | Q(class_activity__year_id=yid, class_activity__semester=sem)
            )

        if blocking_pairs:
            locked = same_slot.filter(blocking_q)

            # ---- 2) TEACHER clash ----
            # An activity with no teacher (Library, Sports) clashes with nobody.
            # An activity WITH a teacher clashes exactly like a lecture.
            if teacher:
                busy = locked.filter(
                    Q(assignment__teacher=teacher)
                    | Q(class_activity__teacher=teacher)
                ).exists()
                if busy:
                    name = (teacher.get_full_name() or "").strip() or teacher.username
                    raise ValidationError(
                        f"{name} is already booked in that period by another department."
                    )

            # ---- 3) ROOM clash ----
            room = serializer.validated_data.get("room")
            if room and locked.filter(room=room).exists():
                raise ValidationError(f"{room.name} is already booked in that period.")

        serializer.save()

        # renew this class's hold
        _ensure_approval_for_class(year_id, semester, course_id)


class TimetableDetail(generics.RetrieveDestroyAPIView):
    queryset = TimetableEntry.objects.all()
    serializer_class = TimetableEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        user = self.request.user

        # An activity has no assignment — work out its class from class_activity.
        # Every line below has to survive `assignment` being None.
        year_id, semester, course_id = _entry_class(instance)

        if not is_admin(user):
            if course_id not in _hod_course_ids(user):
                raise PermissionDenied("This class is not in your department.")

        approval = _get_approval(year_id, semester)
        if approval and approval.status == TimetableApproval.Status.SUBMITTED and not is_admin(user):
            raise PermissionDenied(
                "This timetable is submitted for approval and locked. "
                "Wait for the admin to review it."
            )

        instance.delete()

        # renew the hold — the HOD is still working
        _ensure_approval_for_class(year_id, semester, course_id)

        if approval and approval.status == TimetableApproval.Status.APPROVED and not is_admin(user):
            _reset_to_draft(approval)


# =====================================================
#  ASSIGNMENT OPTIONS  — subjects/teachers placeable for a class.
#  Admin: any class. HOD: only her department's classes.
# =====================================================
class AssignmentOptions(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can build the timetable.")

        year_id = request.query_params.get("year")
        semester = request.query_params.get("semester")

        qs = TeachingAssignment.objects.select_related(
            "subject", "teacher", "year", "course"
        )
        if year_id:
            qs = qs.filter(year_id=year_id)
        if semester:
            qs = qs.filter(subject__semester=semester)

        if not is_admin(user) and is_hod(user):
            qs = qs.filter(course_id__in=_hod_course_ids(user))

        # how many periods of each subject are already on this class's grid
        data = []
        for a in qs:
            placed = TimetableEntry.objects.filter(assignment=a).count()
            data.append({
                "id": a.id,
                "subject": a.subject.name,
                "teacher_name": (a.teacher.get_full_name() or "").strip() or a.teacher.username,
                "weekly_hours": a.subject.weekly_hours,
                "placed": placed,
            })
        return Response(data)


# =====================================================
#  APPROVAL WORKFLOW
# =====================================================
class TimetableSubmit(APIView):
    """HOD (or admin) submits a class timetable (year + semester) for approval."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        year_id = request.data.get("year")
        semester = request.data.get("semester")

        if not year_id or not semester:
            return Response({"detail": "year and semester are required."}, status=400)

        from courses.models import Year
        try:
            year = Year.objects.get(id=year_id)
        except Year.DoesNotExist:
            return Response({"detail": "Year not found."}, status=404)

        course_id = getattr(year, "course_id", None)

        # HOD can only submit her own department's class
        if not is_admin(user):
            if course_id not in _hod_course_ids(user):
                return Response({"detail": "This class is not in your department."}, status=403)

        # must have at least one entry placed — a lecture or an activity
        has_entries = TimetableEntry.objects.filter(
            Q(assignment__year_id=year_id, assignment__subject__semester=semester)
            | Q(class_activity__year_id=year_id, class_activity__semester=semester)
        ).exists()
        if not has_entries:
            return Response(
                {"detail": "Add at least one class to the timetable before submitting."},
                status=400,
            )

        obj, _ = TimetableApproval.objects.get_or_create(
            year_id=year_id,
            semester=semester,
            defaults={"course_id": course_id, "status": TimetableApproval.Status.DRAFT},
        )

        # ---- Layer 3: per-cell validation before we lock anything ----
        # Two HODs can draft the same slot at once. The first to submit wins.
        # The second gets told exactly which cells clash — not "submit failed".
        conflicts = validate_submission(year_id, semester)
        if conflicts:
            return Response(
                {
                    "detail": "Some slots were taken by another department while you were working.",
                    "conflicts": conflicts,
                },
                status=409,
            )

        obj.status = TimetableApproval.Status.SUBMITTED
        obj.submitted_by = user
        obj.submitted_at = timezone.now()
        obj.reviewed_by = None
        obj.reviewed_at = None
        obj.remark = ""
        obj.save()

        return Response({"status": obj.status, "message": "Submitted for approval."})


class TimetableApprovalStatus(APIView):
    """Current approval status for one class (used by the HOD builder badge)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        year_id = request.query_params.get("year")
        semester = request.query_params.get("semester")
        if not year_id or not semester:
            return Response({"status": None})

        obj = _get_approval(year_id, semester)
        if not obj:
            return Response({"status": "draft", "remark": ""})

        return Response({
            "status": obj.status,
            "remark": obj.remark or "",
            "submitted_at": obj.submitted_at,
            "reviewed_at": obj.reviewed_at,
        })


# =====================================================
#  APPROVALS LIST  (admin only)
#  Everything the admin needs to review a submission.
#  `year` is the database id — the Review screen uses it to
#  fetch the grid. `year_number` is only for display.
# =====================================================
class TimetableApprovalList(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only an admin can review timetables.")

        qs = (
            TimetableApproval.objects
            .select_related("course", "year", "submitted_by")
            .all()
        )

        data = [
            {
                "id": a.id,
                "year": a.year_id,                                   # the id the Review screen needs
                "year_number": a.year.year_number if a.year else None,
                "course": a.course.name if a.course else None,
                "semester": a.semester,
                "status": a.status,
                "submitted_by": (
                    (a.submitted_by.get_full_name() or "").strip()
                    or a.submitted_by.username
                ) if a.submitted_by else "",
                "submitted_at": a.submitted_at,
                "remark": a.remark,
            }
            for a in qs
        ]
        return Response(data)


class TimetableApprovalAction(APIView):
    """Admin approves or rejects (with remark) a submitted class timetable."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not is_admin(request.user):
            raise PermissionDenied("Only an admin can approve timetables.")

        try:
            a = TimetableApproval.objects.get(pk=pk)
        except TimetableApproval.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        action = request.data.get("action")
        remark = request.data.get("remark", "")

        a.reviewed_by = request.user
        a.reviewed_at = timezone.now()

        if action == "approve":
            a.status = TimetableApproval.Status.APPROVED
            a.remark = ""
        elif action == "reject":
            a.status = TimetableApproval.Status.REJECTED
            a.remark = remark
            # Layer 2: a refused claim holds nothing. Release its slots now,
            # so other departments aren't blocked by a timetable the admin
            # has already turned down.
            a.last_active = timezone.now() - timedelta(days=365)
        else:
            return Response({"detail": "action must be approve or reject."}, status=400)

        a.save()
        return Response({"status": a.status, "message": f"Timetable {a.status}."})


# =====================================================
#  SEMESTER + HOLIDAYS  — admin only (college-wide)
# =====================================================
class SemesterActive(generics.ListCreateAPIView):
    """
    GET  -> the active semester (as a 1-item list, or empty)
    POST -> save a semester; marks it active and deactivates the others
    """
    serializer_class = SemesterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Semester.objects.filter(is_active=True)

    def perform_create(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can set the semester.")
        Semester.objects.update(is_active=False)
        serializer.save(is_active=True)


class HolidayListCreate(generics.ListCreateAPIView):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can add holidays.")
        serializer.save()


class HolidayDetail(generics.RetrieveDestroyAPIView):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can delete holidays.")
        instance.delete()


# =====================================================
#  ROOMS — admin-managed, shared across the whole college
# =====================================================
class RoomListCreate(generics.ListCreateAPIView):
    queryset = Room.objects.filter(is_active=True)
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can manage rooms.")
        serializer.save()


class RoomDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can manage rooms.")
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can manage rooms.")
        instance.delete()


# =====================================================
#  AVAILABILITY — which cells can this subject go into?
#  The grid calls this the moment a drag starts, so blocked
#  slots grey out BEFORE the HOD drops. They can't create a clash.
# =====================================================
class TimetableAvailability(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can build the timetable.")

        assignment_id = request.data.get("assignment")
        year_id = request.data.get("year")
        semester = request.data.get("semester")

        if not assignment_id or not year_id or not semester:
            return Response(
                {"detail": "assignment, year and semester are required."},
                status=400,
            )

        try:
            assignment = TeachingAssignment.objects.select_related(
                "teacher", "subject", "year", "course"
            ).get(pk=assignment_id)
        except TeachingAssignment.DoesNotExist:
            return Response({"detail": "Assignment not found."}, status=404)

        # an HOD may only ask about her own department's classes
        if not _can_edit_timetable(user, assignment):
            raise PermissionDenied("This class is not in your department.")

        room = None
        room_id = request.data.get("room")
        if room_id:
            room = Room.objects.filter(pk=room_id).first()

        return Response(
            availability(
                assignment,
                year_id=year_id,
                semester=semester,
                room=room,
            )
        )


# =====================================================
#  AUTO-FILL — the AI. A CP-SAT constraint solver fills
#  the empty cells, obeying every rule the grid enforces.
# =====================================================
class TimetableAutoFill(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can build the timetable.")

        year_id = request.data.get("year")
        semester = request.data.get("semester")

        if not year_id or not semester:
            return Response({"detail": "year and semester are required."}, status=400)

        # the class must be one this user is allowed to edit
        sample = TeachingAssignment.objects.filter(
            year_id=year_id, subject__semester=semester
        ).select_related("year", "course", "subject", "teacher").first()

        if not sample:
            return Response(
                {"detail": "No subjects are assigned to this class yet."}, status=400
            )

        if not _can_edit_timetable(user, sample):
            raise PermissionDenied("This class is not in your department.")

        # a submitted timetable is locked
        approval = _get_approval(year_id, semester)
        if approval and approval.status == TimetableApproval.Status.SUBMITTED and not is_admin(user):
            raise PermissionDenied(
                "This timetable is submitted and locked. Wait for the admin to review it."
            )

        room = None
        room_id = request.data.get("room")
        if room_id:
            room = Room.objects.filter(pk=room_id).first()

        created, message = autofill(
            year_id=year_id,
            semester=semester,
            room=room,
        )

        # renew the hold, even if nothing was placed
        _ensure_approval(sample)

        return Response({"created": created, "message": message})


class TimetableBusy(APIView):
    """
    Every teacher for THIS class, and where they're already booked
    by another department. Loaded once when the class opens — so the
    grid can show 'R.Rajesh is busy' on empty cells without a drag.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can build the timetable.")

        year_id = request.query_params.get("year")
        semester = request.query_params.get("semester")
        if not year_id or not semester:
            return Response({})

        year_id = int(year_id)

        # teachers of this class: from its subjects AND from its activities
        teacher_ids = set(
            TeachingAssignment.objects
            .filter(year_id=year_id, subject__semester=semester)
            .values_list("teacher_id", flat=True)
        )
        teacher_ids |= set(
            ClassActivity.objects
            .filter(year_id=year_id, semester=semester)
            .exclude(teacher__isnull=True)
            .values_list("teacher_id", flat=True)
        )
        teacher_ids.discard(None)

        # An entry can be a lecture or an activity, so we have to look for the
        # teacher on either side. An activity with no teacher blocks nobody.
        entries = _locked_entries().filter(
            Q(assignment__teacher_id__in=teacher_ids)
            | Q(class_activity__teacher_id__in=teacher_ids)
        ).select_related(
            "assignment__teacher", "class_activity__teacher", "class_activity__year",
        )

        busy = {}
        for e in entries:
            e_year, _e_sem, _e_course = _entry_class(e)
            # skip this class's own entries
            if e_year == year_id:
                continue

            t = e.assignment.teacher if e.assignment_id else e.class_activity.teacher
            if not t:
                continue

            key = f"{e.day_of_week}_{e.time_slot_id}"
            name = (t.get_full_name() or "").strip() or t.username
            busy.setdefault(key, []).append(name)

        return Response(busy)


# =====================================================
#  MOVE — shift one entry to a different (day, slot).
#  Powers the "Move to Tue P3" buttons on the conflict panel:
#  the HOD fixes one cell instead of rebuilding the timetable.
# =====================================================
class TimetableMove(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can build the timetable.")

        try:
            entry = TimetableEntry.objects.select_related(
                "assignment__year", "assignment__course", "assignment__subject",
                "class_activity__year", "class_activity__activity",
            ).get(pk=request.data.get("entry"))
        except TimetableEntry.DoesNotExist:
            return Response({"detail": "Entry not found."}, status=404)

        # An activity has no assignment. Read the class off whichever side exists.
        year_id, semester, course_id = _entry_class(entry)

        # HOD may only move her own department's classes
        if not is_admin(user):
            if course_id not in _hod_course_ids(user):
                return Response(
                    {"detail": "This class is not in your department."}, status=403
                )

        day = request.data.get("day")
        slot = request.data.get("slot")
        if day is None or slot is None:
            return Response({"detail": "day and slot are required."}, status=400)

        entry.day_of_week = day
        entry.time_slot_id = slot
        entry.save()

        _ensure_approval_for_class(year_id, semester, course_id)

        return Response({"ok": True})


# =====================================================
#  ACTIVITY TYPES  — the college defines these once.
#  Admin manages them; HODs read them.
# =====================================================
class ActivityTypeListCreate(generics.ListCreateAPIView):
    queryset = ActivityType.objects.filter(is_active=True)
    serializer_class = ActivityTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # a HOD can invent a new activity ("Placement Training") on the fly —
        # activities have no master syllabus, so free text is correct here.
        if not (is_admin(self.request.user) or is_hod(self.request.user)):
            raise PermissionDenied("Only an admin or HOD can add activities.")
        serializer.save()


class ActivityTypeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = ActivityType.objects.all()
    serializer_class = ActivityTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can edit activity types.")
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin(self.request.user):
            raise PermissionDenied("Only an admin can delete activity types.")
        instance.delete()


# =====================================================
#  CLASS ACTIVITIES  — "this class has Library, 1/week".
#  Configured ONCE per class, then Auto-fill just knows.
#  No popup, ever.
# =====================================================
class ClassActivityList(generics.ListCreateAPIView):
    serializer_class = ClassActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ClassActivity.objects.select_related("activity", "year", "teacher")
        year = self.request.query_params.get("year")
        semester = self.request.query_params.get("semester")
        if year:
            qs = qs.filter(year_id=year)
        if semester:
            qs = qs.filter(semester=semester)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can configure activities.")
        serializer.save()


class ClassActivityDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = ClassActivity.objects.all()
    serializer_class = ClassActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        user = self.request.user
        if not (is_admin(user) or is_hod(user)):
            raise PermissionDenied("Only an admin or HOD can configure activities.")
        serializer.save()

    def perform_destroy(self, instance):
        # removing an activity from a class also clears it off the grid
        instance.entries.all().delete()
        instance.delete()