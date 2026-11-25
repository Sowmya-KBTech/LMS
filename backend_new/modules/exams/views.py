import datetime
from decimal import Decimal, InvalidOperation
import os, json, datetime, requests
from django.apps import apps
from core.academics.models import Subject
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied, APIException
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .services import compute_grade
from core.academics.holidays import holiday_dates

from .models import( InternalAssessment, IAMark,ExamSchedule,RevaluationRequest, RevaluationWindow,SemesterResult, ResultEntry, EligibilitySetting, EligibilityOverride)

from .serializers import (
    InternalAssessmentSerializer,
    IAMarkStudentSerializer,
    SemesterResultSerializer,
    SemesterResultStudentSerializer,
    ExamScheduleSerializer,
    RevaluationRequestSerializer,
    RevaluationWindowSerializer

)

User = get_user_model()

# ===================== EXAM ADMIN HELPER =====================
# #49 SECURITY FIX: who may manage exams (IA, results, hall tickets, exam
# schedule, revaluation, eligibility rules). Before, this only checked
# role == "admin", so EVERY admin sub-role passed - a placement officer or an
# accounts admin could publish results. Now: superuser, the main admin (no
# sub-role), super admin and the Examination admin. One rule for the whole
# module (and the Results / IA / exam-schedule imports, which call it).
EXAM_ADMIN_SUB_ROLES = ("", "super_admin", "exam_admin")


def is_exam_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = getattr(user, "role", None)
    if role == "exam_admin":          # legacy role value, kept for safety
        return True
    if role != "admin":
        return False
    return (getattr(user, "sub_role", None) or "") in EXAM_ADMIN_SUB_ROLES


# ELIGIBILITY RULES (#41): changing the hall-ticket eligibility rules and
# overriding a student - the same people as above.
def can_manage_eligibility(user):
    return is_exam_admin(user)


# ===================== INTERNAL ASSESSMENT =====================
class InternalAssessmentViewSet(viewsets.ModelViewSet):

    serializer_class = InternalAssessmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = InternalAssessment.objects.select_related(
            "teaching_assignment__subject"
        ).prefetch_related("marks__student")

        # ---- role branches flow INTO shared filter, never return early ----
        if user.role == "teacher":
            qs = qs.filter(teaching_assignment__teacher=user)
        elif not is_exam_admin(user) and user.role != "admin":
            # PHASE 5: students / parents read their own marks through /ia-marks/.
            # This list carries EVERY student's marks, so it is staff-only.
            qs = qs.none()
        # admin / exam_admin see everything (no extra filter)

        # ?teaching_assignment= filter for both roles
        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            qs = qs.filter(teaching_assignment_id=ta)
        return qs

    # PHASE 5: creating / editing / deleting an IA slot is the exam admin's job
    # (teachers enter marks through /ia-marks/save_marks/).
    def _require_exam_admin(self):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can change internal assessments.")

    def perform_create(self, serializer):
        self._require_exam_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_exam_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_exam_admin()
        instance.delete()

    # ================= LOCK (ADMIN — DECLARE) =================
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        if not is_exam_admin(request.user):
            raise PermissionDenied("Only admin or exam admin can lock IA marks.")
        ia = self.get_object()
        was_locked = ia.is_locked
        ia.is_locked = True
        ia.save(update_fields=["is_locked"])

        # FIX #11: tell students (and parents) once, when marks are declared.
        # Re-declaring after a correction tells them again, because the mark changed.
        if not was_locked:
            from core.academics.models import Enrollment
            from core.notifications.services import notify, notify_parents
            ta = ia.teaching_assignment
            subject = ta.subject.name
            students = [e.student for e in Enrollment.objects.filter(
                teaching_assignment=ta).select_related("student")]
            title = f"IA {ia.number} marks declared – {subject}"
            notify(students, title,
                   f"Your Internal Assessment {ia.number} marks for {subject} are now published.",
                   "exam", link="/results?tab=ia", ta=ta)
            for s in students:
                notify_parents(s, title,
                               f"{s.username}'s IA {ia.number} marks for {subject} are published.",
                               "exam", link="/results?tab=ia")
        return Response({"status": "locked"})

    # ================= UNLOCK (ADMIN) =================
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        if not is_exam_admin(request.user):
            raise PermissionDenied("Only admin or exam admin can unlock IA marks.")
        ia = self.get_object()
        ia.is_locked = False
        ia.save(update_fields=["is_locked"])
        return Response({"status": "unlocked"})


# ===================== IA MARK =====================
class IAMarkViewSet(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.user.role in ("student", "parent"):
            return IAMarkStudentSerializer
        from .serializers import IAMarkSerializer
        return IAMarkSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IAMark.objects.select_related(
            "assessment__teaching_assignment__subject",
            "student",
        )

        if user.role == "student":
            # own marks, declared slots only
            return qs.filter(student=user, assessment__is_locked=True)

        if user.role == "parent":
            # children's marks, declared (locked) slots only
            from core.academics.helpers import get_parent_children
            child_ids = [c.id for c in get_parent_children(user)]
            qs = qs.filter(student_id__in=child_ids, assessment__is_locked=True)

            child = self.request.query_params.get("child")
            if child:
                qs = qs.filter(student_id=child)
            return qs

        if user.role == "teacher":
            qs = qs.filter(
                assessment__teaching_assignment__teacher=user
            )

        assessment = self.request.query_params.get("assessment")
        if assessment:
            qs = qs.filter(assessment_id=assessment)
        return qs

    # ================= BLOCK EDITS ON LOCKED SLOTS =================
    def perform_create(self, serializer):
        self._reject_if_student()          # PHASE 5: role first, then the data
        assessment = serializer.validated_data.get("assessment")
        if assessment is None:
            raise ValidationError({"assessment": ["This field is required."]})
        self._reject_if_locked(assessment)
        serializer.save()

    def perform_update(self, serializer):
        self._reject_if_student()
        self._reject_if_locked(serializer.instance.assessment)
        serializer.save()

    def _reject_if_locked(self, assessment):
        if assessment.is_locked:
            raise ValidationError(
                "This IA is locked and can no longer be edited."
            )

    def _reject_if_student(self):
        if self.request.user.role in ("student", "parent"):
            raise PermissionDenied("Read-only role cannot edit marks.")

    # ================= BULK SAVE (TEACHER GRID) =================
    @action(detail=False, methods=["post"])
    def save_marks(self, request):
        """
        Teacher saves a whole IA grid in one call (mirrors attendance bulk_mark).
        Gets or creates the IA slot, then upserts each student's mark.
        Blocked once the slot is locked.
        """
        user = request.user
        ta_id = request.data.get("teaching_assignment")
        number = request.data.get("number")
        records = request.data.get("records", [])

        if not ta_id or not number:
            raise ValidationError("teaching_assignment and number are required.")

        # FIX #14: max_marks must be a whole number between 1 and 100.
        try:
            max_marks = int(request.data.get("max_marks", 50))
        except (TypeError, ValueError):
            return Response({"detail": "Maximum marks must be a whole number."},
                            status=status.HTTP_400_BAD_REQUEST)
        if max_marks < 1 or max_marks > 100:
            return Response({"detail": "Maximum marks must be between 1 and 100."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(records, list):
            return Response({"detail": "records must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)

        from core.academics.models import TeachingAssignment, Enrollment
        ta = get_object_or_404(TeachingAssignment, id=ta_id)

        if user.role == "teacher" and ta.teacher_id != user.id:
            raise PermissionDenied("Not your teaching assignment.")
        if user.role in ("student", "parent"):
            raise PermissionDenied("This role cannot enter marks.")

        existing = InternalAssessment.objects.filter(
            teaching_assignment=ta, number=number
        ).first()
        if existing and existing.is_locked:
            return Response({"detail": "This IA is locked and can no longer be edited."},
                            status=status.HTTP_400_BAD_REQUEST)
        # CO-PO PART B: with a question paper the total is the sum of the question marks
        if existing and existing.questions.exists():
            return Response({"detail": "This IA has a question paper: enter its marks question by question."},
                            status=status.HTTP_400_BAD_REQUEST)

        # FIX #14: check EVERY row before saving ANY row. One bad mark means
        # nothing is saved, so the class never ends up half-updated.
        enrolled = dict(
            Enrollment.objects.filter(teaching_assignment=ta)
            .values_list("student_id", "student__username")
        )
        errors = []
        clean = []
        for r in records:
            sid = r.get("student")
            if not sid:
                continue
            try:
                sid = int(sid)
            except (TypeError, ValueError):
                errors.append(f"Invalid student id '{sid}'.")
                continue
            if sid not in enrolled:
                errors.append(f"Student {sid} is not enrolled in this subject.")
                continue
            name = enrolled[sid]
            absent = bool(r.get("is_absent", False))
            raw = None if absent else r.get("marks_obtained")
            if raw is None or raw == "":
                clean.append((sid, None, absent))
                continue
            try:
                obtained = float(raw)
            except (TypeError, ValueError):
                errors.append(f"{name}: '{raw}' is not a number.")
                continue
            if obtained != obtained or obtained < 0 or obtained > max_marks:  # NaN / range
                errors.append(f"{name}: {raw} is out of range (0 to {max_marks}).")
                continue
            clean.append((sid, obtained, absent))

        if errors:
            return Response(
                {"detail": "Marks not saved. Please correct: " + " ".join(errors),
                 "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.db import transaction
        with transaction.atomic():
            slot, _ = InternalAssessment.objects.get_or_create(
                teaching_assignment=ta,
                number=number,
                defaults={"max_marks": max_marks},
            )
            if slot.is_locked:
                return Response({"detail": "This IA is locked and can no longer be edited."},
                                status=status.HTTP_400_BAD_REQUEST)
            if slot.max_marks != max_marks:
                slot.max_marks = max_marks
                slot.save(update_fields=["max_marks"])
            for sid, obtained, absent in clean:
                IAMark.objects.update_or_create(
                    assessment=slot,
                    student_id=sid,
                    defaults={"marks_obtained": obtained, "is_absent": absent},
                )

        return Response({"status": "saved", "assessment_id": slot.id})

# IA marks CSV template/import live in the shared Import & Export engine:
#   modules/exams/importers.py  ->  /api/dataio/ia_marks/...


# ===================== SEMESTER RESULT =====================
class SemesterResultViewSet(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.user.role in ("student", "parent"):
            return SemesterResultStudentSerializer
        return SemesterResultSerializer

    def get_queryset(self):
        user = self.request.user
        qs = SemesterResult.objects.select_related("student").prefetch_related(
            "entries__subject"
        )

        if user.role == "student":
            # own results, published only, all semesters
            return qs.filter(student=user, is_published=True)

        if user.role == "parent":
            # children's results, published only
            from core.academics.helpers import get_parent_children
            child_ids = [c.id for c in get_parent_children(user)]
            qs = qs.filter(student_id__in=child_ids, is_published=True)

            child = self.request.query_params.get("child")
            if child:
                qs = qs.filter(student_id=child)

            return qs

        # PHASE 5: only the admin / exam admin may see every student's results
        # (teachers and other staff have no results screen).
        if not (is_exam_admin(user) or user.role == "admin"):
            return qs.none()

        # admin / exam_admin see everything; optional filters for the entry screen
        semester = self.request.query_params.get("semester")
        if semester:
            qs = qs.filter(semester=semester)

        student = self.request.query_params.get("student")
        if student:
            qs = qs.filter(student_id=student)

        return qs

    # PHASE 5: the plain create / edit / delete routes are the exam admin's too
    def perform_create(self, serializer):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can enter semester results.")
        serializer.save()

    def perform_update(self, serializer):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can change semester results.")
        serializer.save()

    def perform_destroy(self, instance):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can delete semester results.")
        instance.delete()

    # ================= BULK SAVE (ADMIN ENTRY) =================
    @action(detail=False, methods=["post"])
    def save_results(self, request):
        """
        Admin saves final marks for one subject, for many students, in one call.
        For each student: get-or-create their SemesterResult for that semester,
        then upsert the ResultEntry for this subject (grade computed server-side).

        WAVE 3 PART 1B (CBCS): a record may carry
          internal_marks + end_marks   graded by the student's regulation
          marks_obtained               one total (as before)
          grade                        a grade given by hand (SA, W)
        exam_session ("Apr/May 2026") on a re-exam of an arrear records a NEW
        attempt; the first attempt's internal mark is kept when the regulation
        says so. All rows or none: one bad row -> 400, nothing saved.
        """
        from django.db import transaction
        from .grading import GradingError, keep_internal, record_result

        user = request.user
        if not is_exam_admin(user):
            raise PermissionDenied("Only admin or exam admin can enter semester results.")

        subject_id = request.data.get("subject")
        semester = request.data.get("semester")
        max_marks = request.data.get("max_marks", 100)
        exam_session = (request.data.get("exam_session") or "").strip()
        records = request.data.get("records", [])

        if not subject_id or not semester:
            raise ValidationError("subject and semester are required.")

        from core.academics.models import Subject
        subject = get_object_or_404(Subject, id=subject_id)

        def number(value, label):
            if value in ("", None):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                raise GradingError(f"{label} must be a number.")

        errors, done = [], {"new": 0, "updated": 0, "new_attempt": 0}
        with transaction.atomic():
            for r in records:
                sid = r.get("student")
                if not sid:
                    continue
                student = User.objects.filter(pk=sid, role="student").first()
                if student is None:
                    errors.append({"student": sid, "detail": "Not a student."})
                    continue
                try:
                    internal = number(r.get("internal_marks"), "Internal")
                    end = number(r.get("end_marks"), "End-semester")
                    total = number(r.get("marks_obtained"), "Marks")
                    if end is not None and internal is None:
                        internal = keep_internal(student, subject, None)
                    _, action_done = record_result(
                        student, subject, semester,
                        internal=internal, end=end,
                        total=None if (internal is not None or end is not None) else total,
                        max_marks=float(max_marks) if max_marks not in ("", None) else None,
                        manual=(r.get("grade") or "").strip() or None, exam_session=exam_session)
                    done[action_done] += 1
                except GradingError as e:
                    errors.append({"student": sid, "name": student.display_name,
                                   "roll_number": student.roll_number or "", "detail": str(e)})
            if errors:
                transaction.set_rollback(True)

        if errors:
            return Response({"detail": f"Nothing saved: {len(errors)} row{'s need' if len(errors) != 1 else ' needs'} "
                                       f"fixing.", "errors": errors}, status=400)
        return Response({"status": "saved", **done})

    # ================= PUBLISH (ADMIN — DECLARE) =================
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        if not is_exam_admin(request.user):
            raise PermissionDenied("Only admin or exam admin can publish results.")
        result = self.get_object()
        was_published = result.is_published
        result.is_published = True
        result.save(update_fields=["is_published"])
        # RESULTS PUBLISHED (Point 12, step 7): tell the student and parents,
        # once per result. A failed notice never blocks the publish.
        if not was_published:
            try:
                from modules.automation.jobs import notify_results_published
                notify_results_published(result)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("results notice failed: %s", result.pk)
        return Response({"status": "published"})

    # ================= UNPUBLISH (ADMIN) =================
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        if not is_exam_admin(request.user):
            raise PermissionDenied("Only admin or exam admin can unpublish results.")
        result = self.get_object()
        result.is_published = False
        result.save(update_fields=["is_published"])
        return Response({"status": "unpublished"})


# ===================== STUDENTS BY CLASS (SEMESTER RESULT ROSTER) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students_by_class(request):
    """
    Students in a given course + year + semester.
    Used by the semester-result entry grid — the roster is class-wide,
    not tied to a single teaching assignment.
    """
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    course = request.query_params.get("course")
    year = request.query_params.get("year")
    semester = request.query_params.get("semester")

    if not (course and year and semester):
        return Response(
            {"detail": "course, year and semester are required."},
            status=400,
        )

    students = User.objects.filter(
        role="student",
        course_id=course,
        year=year,
        semester=semester,
    ).order_by("roll_number")

    data = [
        {
            "student": s.id,
            "student_name": s.username,
            "student_roll_no": s.roll_number,
        }
        for s in students
    ]
    return Response(data)

from config.module_registry import module_enabled, optional_model

# Attendance is optional. When it is switched off, attendance is simply not
# used for hall-ticket eligibility (see _is_eligible).
Attendance = optional_model("attendance", "attendance", "Attendance")
from core.academics.models import Enrollment
from modules.fees.models import Fee

ATTENDANCE_FINE_TERM = "Attendance Shortage Fine"
# ELIGIBILITY RULES (#41): 75 is now only the DEFAULT. The real value comes
# from EligibilitySetting.current().min_attendance, which the admin can change.
ATTENDANCE_THRESHOLD = 75


def _rules():
    """The college's eligibility rules (minimum %, does a paid fine unlock)."""
    return EligibilitySetting.current()


def _active_override(student):
    """ELIGIBILITY OVERRIDE (#41 Part B): this semester's active override, or None."""
    return EligibilityOverride.objects.filter(
        student=student,
        semester=student.semester,
        revoked_at__isnull=True,
    ).first()


def _fine_term(semester):
    """
    One fine per student per semester. The term string is the key.

    Fee has no semester column, so the semester lives in the term text.
    Without this, a fine paid in Sem 3 would keep a student 'eligible'
    for every later semester regardless of their attendance.
    """
    return f"{ATTENDANCE_FINE_TERM} - Sem {semester}"

EXAM_FEE_TERM = "Semester Exam Fee"


def _exam_fee_term(semester):
    """
    One exam fee per student per semester, keyed by the term string — the same
    approach _fine_term uses, and for the same reason: Fee has no semester
    column.
    """
    return f"{EXAM_FEE_TERM} - Sem {semester}"


def _exam_fee_unpaid(student):
    """
    The fee must EXIST and be unpaid to block. If the office has not generated
    exam fees for this semester, nobody is blocked — otherwise switching this
    on would bar every student in the college overnight.
    """
    return Fee.objects.filter(
        student=student,
        term=_exam_fee_term(student.semester),
    ).exclude(status="paid").exists()


def _attendance_percent(student):

    records = Attendance.objects.filter(
        student=student,
        teaching_assignment__subject__semester=student.semester,
    )
    total = records.count()
    if total == 0:
        return None  # no records yet
    counted = records.filter(status__in=["present", "duty_leave"]).count()
    return round((counted / total) * 100, 1)


def _is_eligible(student, rules=None):
    """
    ELIGIBILITY RULES (#41): uses the college's rules, not a fixed 75%.

    Eligible if attendance >= rules.min_attendance, OR (only when the college
    allows it) this semester's attendance fine is paid.

    No attendance records at all -> blocked. With fines on, such a student IS
    fineable (see generate_attendance_fines), so they have a way to unblock.
    With fines off, only attendance (or, in Part B, an override) unblocks.
    """
    if not module_enabled("attendance"):
        # College does not use the attendance module -> attendance never blocks.
        return True, None, "attendance"

    rules = rules or _rules()

    pct = _attendance_percent(student)
    if pct is not None and pct >= rules.min_attendance:
        return True, pct, "attendance"

    # ELIGIBILITY OVERRIDE (#41 Part B): staff approved this student, with a reason
    if _active_override(student):
        return True, pct, "override"

    # below the minimum (or no records) — a paid fine counts only if allowed
    if rules.fine_unlocks:
        fine_paid = Fee.objects.filter(
            student=student,
            term=_fine_term(student.semester),
            status="paid",
        ).exists()
        if fine_paid:
            return True, pct, "fine_paid"

    return False, pct, "blocked"

def _can_sit_exam(student, rules=None):
    """
    Two independent gates. Both must pass before a hall ticket is issued:
        1. the semester exam fee is paid (if one has been generated)
        2. attendance >= 75%, or this semester's shortage fine is paid

    Kept separate from _is_eligible because generate_attendance_fines uses that
    one to decide who gets an ATTENDANCE fine. Folding the exam fee into it
    would fine a student with perfect attendance for a shortage they do not have.
    """
    if _exam_fee_unpaid(student):
        return False, _attendance_percent(student), "exam_fee_unpaid"

    return _is_eligible(student, rules)

# Semester results CSV template/import live in the shared Import & Export engine:
#   modules/exams/importers.py  ->  /api/dataio/results/...

# ===================== HALL TICKET: STUDENT ELIGIBILITY =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_hall_ticket(request):
    """
    Student's own hall-ticket status + the data needed to render it.
    """
    user = request.user
    if user.role != "student":
        return Response({"detail": "Students only."}, status=403)

    rules = _rules()
    eligible, pct, reason = _can_sit_exam(user, rules)

    # WAVE 3 PART 2: the current exam session decides the timetable, and - when
    # it uses registration - which papers (this semester's + arrears) are listed.
    from .exam_sessions import current_session, hall_ticket_papers, schedule_rows, session_payload
    session = current_session()
    slots = {r.subject_id: r for r in schedule_rows(session)}
    extra = {"session": session_payload(session) if session else None,
             "registration_required": bool(session and session.registration_required),
             "registered": None, "released": bool(session is None or session.hall_tickets_released),
             "registration_fee": None}
    if session and session.registration_required:
        registered, fee_ok, papers = hall_ticket_papers(session, user, eligible, reason)
        from .models import ExamRegistration
        reg = ExamRegistration.objects.filter(exam_session=session, student=user).select_related("fee").first()
        if reg and reg.fee_id:
            extra["registration_fee"] = {"id": reg.fee.id, "amount": float(reg.fee.amount),
                                         "paid_amount": float(reg.fee.paid_amount), "status": reg.fee.status}
        extra["registered"] = registered
        regular_reason = reason
        if not registered:
            reason = "not_registered"
        elif not fee_ok:
            reason = "registration_fee_unpaid"
        elif not session.hall_tickets_released:
            reason = "not_released"
        writable = [p for p in papers if not p["withheld"]]
        ticket_ok = registered and session.hall_tickets_released and bool(writable)
        exam_fee = Fee.objects.filter(student=user, term=_exam_fee_term(user.semester)).exclude(status="paid").first()
        fine = Fee.objects.filter(student=user, term=_fine_term(user.semester)).exclude(status="paid").first()
        if not rules.fine_unlocks:
            fine = None
        return Response({
            "student_name": user.username,
            "roll_number": user.roll_number,
            "attendance_percent": pct,
            "threshold": rules.min_attendance,
            "fine_unlocks": rules.fine_unlocks,
            "eligible": ticket_ok,
            "reason": reason,
            "regular_reason": regular_reason,
            "subjects": papers,
            "fine_id": fine.id if fine else None,
            "fine_amount": float(fine.amount) if fine else None,
            "exam_fee_id": exam_fee.id if exam_fee else None,
            "exam_fee_amount": float(exam_fee.amount) if exam_fee else None,
            **extra,
        })

    # subjects = the student's enrolled subjects, with code + exam schedule
    enrollments = Enrollment.objects.filter(student=user).select_related(
        "teaching_assignment__subject"
    )
    seen = {}
    for e in enrollments:
        subj = e.teaching_assignment.subject
        seen[subj.id] = subj  # dedupe by subject id

    subjects = []
    for subj in seen.values():
        sched = slots.get(subj.id)
        subjects.append({
            "name": subj.name,
            "code": subj.code or "",
            "kind": "regular",
            "semester": subj.semester,
            "exam_date": sched.exam_date.isoformat() if sched else None,
            "session": sched.session if sched else None,
        })
    # sort by exam date (subjects without a date go last)
    subjects.sort(key=lambda s: (s["exam_date"] is None, s["exam_date"] or ""))

    # is there an unpaid attendance fine for THIS semester to show a Pay button for?
    fine = Fee.objects.filter(
        student=user,
        term=_fine_term(user.semester),
    ).exclude(status="paid").first()
    # ELIGIBILITY RULES (#41): no Pay button when a fine cannot unlock the ticket
    if not rules.fine_unlocks:
        fine = None

        # same idea for the exam fee, so the student can pay it from this screen
    exam_fee = Fee.objects.filter(
        student=user,
        term=_exam_fee_term(user.semester),
    ).exclude(status="paid").first()

    return Response({
        "student_name": user.username,
        "roll_number": user.roll_number,
        "attendance_percent": pct,
        "threshold": rules.min_attendance,
        "fine_unlocks": rules.fine_unlocks,
        "eligible": eligible,
        "reason": reason,   # attendance | fine_paid | blocked | exam_fee_unpaid
        "subjects": subjects,
        "fine_id": fine.id if fine else None,   # frontend pays this fee
        "fine_amount": float(fine.amount) if fine else None,
        "exam_fee_id": exam_fee.id if exam_fee else None,
        "exam_fee_amount": float(exam_fee.amount) if exam_fee else None,
        **extra,
    })
    


# ===================== HALL TICKET: ADMIN ROSTER =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hall_ticket_roster(request):
    """
    Admin view: students in a course/year/semester with eligibility status.
    """
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    course = request.query_params.get("course")
    year = request.query_params.get("year")
    semester = request.query_params.get("semester")
    if not (course and year and semester):
        return Response({"detail": "course, year and semester are required."}, status=400)

    students = User.objects.filter(
        role="student", course_id=course, year=year, semester=semester,
    ).order_by("roll_number")

    rules = _rules()
    data = []
    for s in students:
        eligible, pct, reason = _can_sit_exam(s, rules)
        has_fine = Fee.objects.filter(
            student=s, term=_fine_term(s.semester),
        ).exclude(status="paid").exists()
        data.append({
            "student": s.id,
            "student_name": s.username,
            "student_roll_no": s.roll_number,
            "attendance_percent": pct,
            "eligible": eligible,
            "reason": reason,
            "has_unpaid_fine": has_fine and rules.fine_unlocks,
            # ELIGIBILITY OVERRIDE (#41 Part B): id of the active override, for Revoke
            "override_id": getattr(_active_override(s), "id", None),
            "has_unpaid_exam_fee": _exam_fee_unpaid(s),
        })
    return Response(data)


# ===================== HALL TICKET: ADMIN GENERATE FINES =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_attendance_fines(request):
    """
    Admin creates an attendance-shortage fine for every NOT-ELIGIBLE student
    in a course/year/semester who doesn't already have one for this semester.

    The rule is _is_eligible() — the SAME rule that blocks the hall ticket.
    If a student is blocked, they must be fineable, or they can never unblock.
    (This covers students with no attendance records at all: previously they
    were blocked but skipped by fine generation, leaving them stuck.)
    """
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    course = request.data.get("course")
    year = request.data.get("year")
    semester = request.data.get("semester")
    amount = request.data.get("amount")
    due_date = request.data.get("due_date") or None

    if not (course and year and semester and amount):
        return Response({"detail": "course, year, semester and amount are required."}, status=400)

    # ELIGIBILITY RULES (#41): a fine is pointless if paying it can't unlock
    rules = _rules()
    if not rules.fine_unlocks:
        return Response(
            {"detail": "Fines are turned off in the eligibility rules. "
                       "Turn on 'A paid fine unlocks the hall ticket' first."},
            status=400,
        )

    # Fee.due_date is NOT NULL, and the roster has no date picker.
    # Default to 14 days out when the admin doesn't supply one.
    if not due_date:
        due_date = datetime.date.today() + datetime.timedelta(days=14)

    students = User.objects.filter(
        role="student", course_id=course, year=year, semester=semester,
    )

    term = _fine_term(semester)

    created = 0
    skipped = 0
    for s in students:
        eligible, pct, reason = _is_eligible(s, rules)
        if eligible:
            continue  # meets attendance, or already paid this semester's fine

        if Fee.objects.filter(student=s, term=term).exists():
            skipped += 1
            continue

        Fee.objects.create(
            student=s,
            term=term,
            amount=amount,
            due_date=due_date,
            status="pending",
        )
        created += 1

        # FIX #11: the student is told why the hall ticket is blocked
        # PART C (#41): this block was pasted twice, so every student got the
        # notification two times. One copy now, and the real % from the rules.
        from core.notifications.services import notify
        why = (f"Your attendance is {pct:.1f}%." if pct is not None
               else "No attendance is recorded for you yet.")
        due_txt = (due_date.strftime("%d-%m-%Y") if hasattr(due_date, "strftime")
                   else str(due_date))
        notify([s], f"Hall ticket blocked – attendance below {rules.min_attendance}%",
               f"{why} Pay the attendance fine of ₹{amount} (due {due_txt}) "
               f"to unlock your hall ticket.",
               "exam", link="/results?tab=ht")

    return Response({
        "message": f"{created} attendance fine(s) created, {skipped} already existed.",
        "created": created,
        "skipped": skipped,
    })
# ===================== ELIGIBILITY RULES (#41) =====================
def _rules_payload(rules, user):
    who = rules.updated_by
    return {
        "min_attendance": rules.min_attendance,
        "fine_unlocks": rules.fine_unlocks,
        "updated_by": ((who.get_full_name() or "").strip() or who.username) if who else None,
        "updated_at": rules.updated_at,
        "can_edit": can_manage_eligibility(user),
    }


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def eligibility_rules(request):
    """
    GET: the college's hall-ticket eligibility rules (exam admins can read).
    PUT: change them (main admin / Examination admin only).
         Body: {"min_attendance": 70, "fine_unlocks": true}
    """
    user = request.user
    if not (is_exam_admin(user) or can_manage_eligibility(user)):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    rules = _rules()

    if request.method == "GET":
        return Response(_rules_payload(rules, user))

    if not can_manage_eligibility(user):
        return Response(
            {"detail": "Only the main admin or the Examination admin can change eligibility rules."},
            status=403,
        )

    raw = request.data.get("min_attendance", rules.min_attendance)
    try:
        pct = int(str(raw).strip())
    except (TypeError, ValueError):
        return Response({"detail": "Minimum attendance must be a whole number."}, status=400)
    if pct < 1 or pct > 100:
        return Response({"detail": "Minimum attendance must be between 1 and 100."}, status=400)

    fine = request.data.get("fine_unlocks", rules.fine_unlocks)
    if isinstance(fine, str):
        fine = fine.strip().lower() in ("1", "true", "yes", "on")

    rules.min_attendance = pct
    rules.fine_unlocks = bool(fine)
    rules.updated_by = user
    rules.save()
    return Response(_rules_payload(rules, user))


# ===================== ELIGIBILITY OVERRIDE (#41 Part B) =====================
MIN_REASON = 10   # characters — a real reason, not "ok"


def _person(u):
    return ((u.get_full_name() or "").strip() or u.username) if u else None


def _override_payload(o):
    return {
        "id": o.id,
        "student": o.student_id,
        "student_name": o.student.username,
        "student_roll_no": o.student.roll_number,
        "semester": o.semester,
        "reason": o.reason,
        "created_by": _person(o.created_by),
        "created_at": o.created_at,
        "is_active": o.is_active,
        "revoked_by": _person(o.revoked_by),
        "revoked_at": o.revoked_at,
        "revoke_reason": o.revoke_reason,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def eligibility_override(request):
    """
    Unblock ONE student's hall ticket for their current semester.
    Body: {"student": <id>, "reason": "Medical leave – certificate verified"}
    Main admin / Examination admin only. Reason required. Audit row kept forever.
    """
    if not can_manage_eligibility(request.user):
        return Response(
            {"detail": "Only the main admin or the Examination admin can override eligibility."},
            status=403,
        )

    reason = (request.data.get("reason") or "").strip()
    if len(reason) < MIN_REASON:
        return Response(
            {"detail": f"Please write the reason (at least {MIN_REASON} characters)."},
            status=400,
        )

    student = User.objects.filter(pk=request.data.get("student"), role="student").first()
    if not student:
        return Response({"detail": "Student not found."}, status=404)

    if _active_override(student):
        return Response(
            {"detail": "This student already has an active override for this semester."},
            status=400,
        )

    eligible, pct, why = _is_eligible(student)
    if eligible:
        return Response(
            {"detail": "This student already meets the eligibility rules. No override is needed."},
            status=400,
        )

    o = EligibilityOverride.objects.create(
        student=student,
        semester=student.semester,
        reason=reason,
        created_by=request.user,
    )

    try:
        from core.notifications.services import notify
        notify([student], "Hall ticket approved by the college",
               "The college has approved your hall ticket for this semester despite "
               "the attendance shortage. You can download it now.",
               "exam", link="/results?tab=ht")
    except Exception:
        pass

    return Response(_override_payload(o), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def eligibility_override_revoke(request, pk):
    """
    Withdraw an active override. Body: {"reason": "..."}.
    The row is NOT deleted: the revoke is recorded on it, so both events stay.
    """
    if not can_manage_eligibility(request.user):
        return Response(
            {"detail": "Only the main admin or the Examination admin can revoke an override."},
            status=403,
        )

    o = EligibilityOverride.objects.filter(pk=pk).select_related("student").first()
    if not o:
        return Response({"detail": "Override not found."}, status=404)
    if not o.is_active:
        return Response({"detail": "This override was already revoked."}, status=400)

    reason = (request.data.get("reason") or "").strip()
    if len(reason) < MIN_REASON:
        return Response(
            {"detail": f"Please write the reason (at least {MIN_REASON} characters)."},
            status=400,
        )

    o.revoked_by = request.user
    o.revoked_at = timezone.now()
    o.revoke_reason = reason
    o.save(update_fields=["revoked_by", "revoked_at", "revoke_reason"])

    try:
        from core.notifications.services import notify
        notify([o.student], "Hall ticket approval withdrawn",
               "The college has withdrawn the approval of your hall ticket. "
               "Please contact the examination office.",
               "exam", link="/results?tab=ht")
    except Exception:
        pass

    return Response(_override_payload(o))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def eligibility_override_log(request):
    """
    The audit log, newest first. Optional ?course=&year=&semester= for one class.
    Read-only: there is no edit or delete endpoint for overrides.
    """
    user = request.user
    if not (is_exam_admin(user) or can_manage_eligibility(user)):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    qs = EligibilityOverride.objects.select_related("student", "created_by", "revoked_by")
    course = request.query_params.get("course")
    year = request.query_params.get("year")
    semester = request.query_params.get("semester")
    if course:
        qs = qs.filter(student__course_id=course)
    if year:
        qs = qs.filter(student__year=year)
    if semester:
        qs = qs.filter(semester=semester)

    return Response([_override_payload(o) for o in qs[:200]])


# ===================== EXAM DRAFT HELPERS =====================
def _term_window():
    # The active semester comes from the timetable module. Without it there
    # is no term window (callers already handle (None, None)).
    if not module_enabled("timetable"):
        return (None, None)
    Semester = apps.get_model("timetable", "Semester")
    sem = Semester.objects.filter(is_active=True).order_by("-start_date").first()
    return (sem.start_date, sem.end_date) if sem else (None, None)

def _working_dates(start, end):
    
    """
    Working days in the term: no weekends (Sat OR Sun), no holidays.
    Every date the auto-arrange / AI-arrange can use comes from here, so the
    weekend rule only has to be correct in this one place.
    """
    holidays = holiday_dates()
    out, d = [], start
    while d and d <= end:
        is_weekend = d.weekday() >= 5          # 5 = Saturday, 6 = Sunday
        if not is_weekend and d not in holidays:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out

def _class_subjects(course, year, semester):
    return list(Subject.objects.filter(
        year__course_id=course, year__year_number=year, semester=semester,
    ).order_by("name"))

def _auto_arrange(subjects, dates, gap=1, session="FN", per_day=1):
    rows = []
    if not dates:
        return rows
    # only two sessions exist (FN, AN) -> at most 2 non-clashing exams per day
    per_day = max(1, min(2, per_day))
    if per_day == 1:
        slot_sessions = [session]
    else:
        # 2 per day: pair one FN + one AN; "afternoon" pref just puts AN first
        slot_sessions = ["AN", "FN"] if session == "AN" else ["FN", "AN"]
    for i, s in enumerate(subjects):
        slot = i % per_day               # which session slot within the day
        day_no = (i // per_day) * gap    # advance the day every `per_day` subjects
        d = dates[min(day_no, len(dates) - 1)]
        rows.append({"subject": s.id, "exam_date": d.isoformat(), "session": slot_sessions[slot]})
    return rows

def _norm_date(s):
    """Coerce whatever Gemini returns into 'YYYY-MM-DD', or None if unusable."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
                "%B %d, %Y", "%B %d %Y", "%d %B %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # non-padded ISO like 2025-8-5
    import re as _re
    m = _re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, da = map(int, m.groups())
        try:
            return datetime.date(y, mo, da).isoformat()
        except ValueError:
            return None
    return None


def _ai_arrange(subjects, dates, preference, session="FN"):
    """Ask Gemini to arrange subjects across the given dates. Returns normalized rows.
    Raises on any failure so the caller can fall back to regex."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    subj = "\n".join(f"- id={s.id} {s.code or ''} {s.name}" for s in subjects)
    days = ", ".join(d.isoformat() for d in dates)
    prompt = (
        "Schedule exams for one class.\n"
        "Subjects:\n" + subj +
        "\n\nAllowed dates (weekends/holidays already removed, use ONLY these): " + days +
        "\nSessions are FN or AN. Default session: " + session +
        "\nPreference from admin: " + (preference or "none") +
        '\n\nReturn ONLY a JSON array, no markdown, no explanation: '
        '[{"subject": <id>, "exam_date": "YYYY-MM-DD", "session": "FN"}]. '
        "Use only the ids and dates listed above. "
        "No two subjects on the same date+session."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent?key=" + key
    )
    r = requests.post(
        url,
        headers={"content-type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    data = r.json()
    if "candidates" not in data:
        raise ValueError(f"Gemini error: {data}")

    text = data["candidates"][0]["content"]["parts"][0]["text"]

    # strip ```json fences if present, then pull out the array
    import re as _re
    text = _re.sub(r"```(?:json)?", "", text).strip()
    m = _re.search(r"\[.*\]", text, _re.S)
    if not m:
        raise ValueError(f"No JSON array in reply: {text[:300]}")

    parsed = json.loads(m.group(0))

    # normalize each row (fix date formats, clamp session)
    out = []
    for row in parsed:
        d = _norm_date(row.get("exam_date"))
        if not d:
            continue
        sess = row.get("session")
        out.append({
            "subject":   row.get("subject"),
            "exam_date": d,
            "session":   sess if sess in ("FN", "AN") else session,
        })
    return out


class ScheduleLocked(APIException):
    """400 with a plain-text detail (the published-timetable / duplicate rules)."""
    status_code = 400
    default_detail = "This exam date can't be changed."


# ===================== EXAM SCHEDULE =====================
class ExamScheduleViewSet(viewsets.ModelViewSet):
    """
    Admin enters exam date + session per subject per semester.
    Everyone authenticated can read (hall ticket needs it).
    """

    serializer_class = ExamScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ExamSchedule.objects.select_related("subject")

        semester = self.request.query_params.get("semester")
        if semester:
            qs = qs.filter(semester=semester)

        # WAVE 3 PART 2: a list shows one exam session - the one asked for, or the current one
        if self.action == "list":
            from .exam_sessions import current_session
            sess = self.request.query_params.get("exam_session")
            if sess:
                qs = qs.filter(exam_session_id=sess)
            else:
                cur = current_session()
                qs = qs.filter(exam_session=cur) if cur else qs.filter(exam_session__isnull=True)

        return qs

    @staticmethod
    def _check_open(session):
        if session is not None and session.timetable_published:
            raise ScheduleLocked(f"The {session.name} timetable is published. Unpublish it to change exam dates.")

    @staticmethod
    def _check_unique(session, subject, semester, exclude=None):
        qs = ExamSchedule.objects.filter(subject=subject)
        qs = qs.filter(exam_session=session) if session else qs.filter(exam_session__isnull=True, semester=semester)
        if exclude is not None:
            qs = qs.exclude(pk=exclude.pk)
        if qs.exists():
            raise ScheduleLocked(f"{subject.name} already has an exam date in this session.")

    def perform_create(self, serializer):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can set exam schedules.")
        from .exam_sessions import current_session
        session = serializer.validated_data.get("exam_session") or current_session()
        self._check_open(session)
        self._check_unique(session, serializer.validated_data["subject"], serializer.validated_data["semester"])
        serializer.save(exam_session=session)

    def perform_update(self, serializer):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can edit exam schedules.")
        inst = serializer.instance
        self._check_open(inst.exam_session)
        self._check_unique(inst.exam_session, serializer.validated_data.get("subject", inst.subject),
                           serializer.validated_data.get("semester", inst.semester), exclude=inst)
        serializer.save(exam_session=inst.exam_session)    # a slot never moves to another session

    def perform_destroy(self, instance):
        if not is_exam_admin(self.request.user):
            raise PermissionDenied("Only admin or exam admin can delete exam schedules.")
        self._check_open(instance.exam_session)
        instance.delete()

    # ================= DRAFT (reads the preference text reliably) =================
    @action(detail=False, methods=["post"], url_path="draft")
    def draft(self, request):
        if not is_exam_admin(request.user):
            raise PermissionDenied("Only admin or exam admin.")
        course     = request.data.get("course")
        year       = request.data.get("year")
        semester   = request.data.get("semester")
        preference = request.data.get("preference", "")
        mode       = (request.data.get("mode") or "auto").lower()   # NEW
        if not (course and year and semester):
            return Response({"detail": "course, year and semester are required."}, status=400)

        subjects = _class_subjects(course, year, semester)
        if not subjects:
            return Response({"detail": "No subjects for this class."}, status=400)
        # WAVE 3 PART 2: inside an exam session, use its exam dates
        from .exam_sessions import current_session, avoid_clashes
        from .models import ExamSession
        sess_id = request.data.get("exam_session")
        exam_session = ExamSession.objects.filter(pk=sess_id).first() if sess_id else current_session()
        if exam_session and exam_session.exam_start and exam_session.exam_end:
            start, end = exam_session.exam_start, exam_session.exam_end
        else:
            start, end = _term_window()
        if not start:
            return Response({"detail": "Set the active semester first."}, status=400)
        dates = _working_dates(start, end)
        if not dates:
            return Response({"detail": "No working dates in the term."}, status=400)

        # ---------- read the preference text (narrows the date pool) ----------
        import re as _re
        pref = (preference or "").lower()

        # gap: from the stepper, overridden by "3 day gap" in the text
        try:
            gap = int(request.data.get("gap", 2))
        except (TypeError, ValueError):
            gap = 2
        gm = _re.search(r"(\d+)\s*days?\s*gap", pref)
        gap_explicit = bool(gm)          # did the user actually type "N day gap"?
        if gm:
            gap = int(gm.group(1))
        if gap < 1:
            gap = 1

        # session: from the dropdown, overridden by words
        session = request.data.get("session", "FN")
        if session not in ("FN", "AN"):
            session = "FN"
        if "afternoon" in pref or " an " in pref:
            session = "AN"
        elif "forenoon" in pref or "morning" in pref:
            session = "FN"

        # exams per day: "2 exams per day" / "each day have 2 exams" (only FN+AN -> max 2)
        pm = _re.search(r"(\d+)\s*exams?\s*(?:per|a|each)\s*day", pref)
        if not pm:
            pm = _re.search(r"(?:per|each|a)\s*day\s*(?:have|has|with|having)?\s*(\d+)\s*exam", pref)
        asked_per_day = int(pm.group(1)) if pm else 1
        per_day = max(1, min(2, asked_per_day))

        # start month: if a month is named, begin from its first working day
        months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                  "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
        start_from = None
        requested_start = None      # the exact day the admin asked for (before snapping)
        for name, num in months.items():
            if name in pref:
                # specific day? "august 8" or "8 august"
                dm = _re.search(name + r"\s+(\d{1,2})", pref) or _re.search(r"(\d{1,2})\s+" + name, pref)
                month_dates = [d for d in dates if d.month == num]
                if dm and month_dates:
                    day = int(dm.group(1))
                    try:
                        requested_start = datetime.date(month_dates[0].year, num, day)
                        start_from = next((d for d in dates if d >= requested_start), None)
                    except ValueError:
                        start_from = month_dates[0]
                else:
                    start_from = next((d for d in dates if d.month == num), None)
                break

        pool = dates
        if start_from:
            pool = [d for d in dates if d >= start_from]

        # "within N days" or "within N weeks" -> limit the window from the first date
        window_limit = None              # the date the user's window caps at
        wm = _re.search(r"within\s*(\d+)\s*day", pref)
        wwm = _re.search(r"within\s*(\d+)\s*week", pref)
        window_days = None
        if wm:
            window_days = int(wm.group(1))
        elif wwm:
            window_days = int(wwm.group(1)) * 7
        if window_days is not None and pool:
            window_limit = pool[0] + datetime.timedelta(days=window_days)
            pool = [d for d in pool if d <= window_limit]

        if not pool:
            pool = dates  # safety: never empty

        # ---- Option C: honor an explicitly typed gap; auto-fit otherwise ----
        notes = []
        if asked_per_day > 2:
            notes.append(f"Only 2 exams per day are possible (one FN + one AN) — capped from {asked_per_day}.")

        # how many distinct exam-days we need (2 subjects share a day when per_day=2)
        num_exam_days = (len(subjects) + per_day - 1) // per_day
        need = (num_exam_days - 1) * gap + 1     # working days this schedule spans

        if gap_explicit:
            # user typed "N day gap" -> keep it. If it needs more room than the
            # current window, extend the pool with more working days (up to the term end).
            if len(pool) < need:
                start0 = pool[0]
                extended = [d for d in dates if d >= start0][:need]
                if window_limit and extended and extended[-1] > window_limit:
                    notes.append(
                        f"{gap}-day gap needs {len(extended)} working days — "
                        f"the window was extended past your limit to fit all {len(subjects)} exams."
                    )
                pool = extended if extended else pool
        else:
            # no explicit gap -> safe to shrink so everything fits the window
            if len(pool) > 1 and num_exam_days > 1:
                max_gap = max(1, (len(pool) - 1) // (num_exam_days - 1))
                if gap > max_gap:
                    gap = max_gap

        gap_note = " ".join(notes) if notes else None

        # ---------- arrange: AI branch or regex branch ----------
        ai_note = None
        if mode == "ai":
            try:
                raw = _ai_arrange(subjects, pool, preference, session=session)
            except Exception as e:
                # AI failed — fall back to regex so we NEVER return an empty/June draft
                raw = _auto_arrange(subjects, pool, gap=gap, session=session, per_day=per_day)
                ai_note = f"AI unavailable, used auto-arrange. ({e})"
        else:
            raw = _auto_arrange(subjects, pool, gap=gap, session=session, per_day=per_day)

        # ---------- validate against the POOL (not all dates) — blocks June ----------
        valid_ids   = {s.id for s in subjects}
        valid_dates = {d.isoformat() for d in pool}
        rows = []
        for r in raw:
            if r.get("subject") in valid_ids and r.get("exam_date") in valid_dates:
                rows.append({
                    "subject":   r["subject"],
                    "exam_date": r["exam_date"],
                    "session":   r["session"] if r.get("session") in ("FN", "AN") else "FN",
                })

        # if AI dropped/duplicated subjects and left the draft incomplete, redo with regex
        if mode == "ai" and len(rows) < len(subjects):
            raw = _auto_arrange(subjects, pool, gap=gap, session=session, per_day=per_day)
            rows = [{
                "subject": r["subject"],
                "exam_date": r["exam_date"],
                "session": r["session"] if r.get("session") in ("FN", "AN") else "FN",
            } for r in raw if r["subject"] in valid_ids and r["exam_date"] in valid_dates]
            if ai_note is None:
                ai_note = "AI returned an incomplete schedule, used auto-arrange."

        # WAVE 3 PART 2: keep arrear students (and anyone writing papers of another
        # class) from getting two papers in the same date + session
        rows, moved = avoid_clashes(exam_session, rows, pool)
        clash_note = (f"{moved} paper{'' if moved == 1 else 's'} moved so that students who also write "
                      f"another class's paper (arrears) don't get two exams at once.") if moved else None

        actual_start = pool[0] if pool else None
        return Response({
            "clash_note": clash_note,
            "draft": rows,
            "ai_note": ai_note,
            "gap_note": gap_note,
            "requested_start": requested_start.isoformat() if requested_start else None,
            "actual_start": actual_start.isoformat() if actual_start else None,
        })   # NOT saved — just a draft


# ===================== SCHEDULED CLASSES (overview) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scheduled_classes(request):
    """Every class that already has an exam schedule, with counts + date range."""
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    from django.db.models import Count, Min, Max
    # WAVE 3 PART 2: one exam session at a time (the one asked for, or the current one)
    from .exam_sessions import current_session, schedule_rows
    from .models import ExamSession
    sess_id = request.query_params.get("exam_session")
    session = ExamSession.objects.filter(pk=sess_id).first() if sess_id else current_session()
    rows = (
        schedule_rows(session)
        .select_related("subject__year__course")
        .values(
            "semester",
            "subject__year__year_number",
            "subject__year__course_id",
            "subject__year__course__name",
        )
        .annotate(count=Count("id"), first=Min("exam_date"), last=Max("exam_date"))
        .order_by("subject__year__course__name", "subject__year__year_number", "semester")
    )
    data = [{
        "course_id":   r["subject__year__course_id"],
        "course_name": r["subject__year__course__name"],
        "year":        r["subject__year__year_number"],
        "semester":    r["semester"],
        "count":       r["count"],
        "first":       r["first"],
        "last":        r["last"],
    } for r in rows]
    return Response(data)


# ===================== REVALUATION ====================
REVALUATION_FEE_TERM = "Revaluation Fee"


# ---------- ADMIN: open / close the window + set fee ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_revaluation_window(request):
    """
    Admin opens/closes the revaluation window for a semester and sets the fee.
    Body: { semester, is_open, fee_amount }
    """
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    try:
        semester = int(request.data.get("semester"))
    except (TypeError, ValueError):
        return Response({"detail": "semester is required."}, status=400)
    if not 1 <= semester <= 8:
        return Response({"detail": "Semester must be between 1 and 8."}, status=400)

    is_open = bool(request.data.get("is_open", False))

    try:
        fee_amount = Decimal(str(request.data.get("fee_amount") or 0))
    except (InvalidOperation, ValueError):
        return Response({"detail": "Enter a valid fee amount."}, status=400)
    if fee_amount < 0:
        return Response({"detail": "Fee amount cannot be negative."}, status=400)

    # MEETING POINT 4: never open revaluation for an examination nobody can
    # revalue. A semester is eligible only if it is the LATEST published
    # examination for at least one active student - the same rule
    # apply_revaluation enforces per student. Closing is always allowed.
    if is_open:
        from .services import revaluation_eligible_students
        eligible = revaluation_eligible_students(semester)
        if eligible == 0:
            published_any = SemesterResult.objects.filter(
                semester=semester, is_published=True
            ).exists()
            why = (
                f"Semester {semester} results are not the latest examination for any student - "
                f"a later semester has already been published."
                if published_any else
                f"No Semester {semester} results have been published yet."
            )
            return Response(
                {"detail": f"Cannot open revaluation. {why}"},
                status=400,
            )

    window, _ = RevaluationWindow.objects.get_or_create(semester=semester)
    window.is_open = is_open
    window.fee_amount = fee_amount
    if window.is_open:
        window.opened_at = timezone.now()
        window.closed_at = None
    else:
        window.closed_at = timezone.now()
    window.save()

    return Response(RevaluationWindowSerializer(window).data)


# ---------- WINDOW STATUS (admin + student) ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revaluation_window_status(request):
    """ Returns the window for ?semester=. Used by both admin and students. """
    semester = request.query_params.get("semester")
    if not semester:
        return Response({"detail": "semester is required."}, status=400)

    try:
        semester = int(semester)
    except (TypeError, ValueError):
        return Response({"detail": "semester must be a number."}, status=400)

    window = RevaluationWindow.objects.filter(semester=semester).first()
    data = (
        dict(RevaluationWindowSerializer(window).data) if window
        else {"semester": semester, "is_open": False, "fee_amount": None}
    )

    # admin screen: can this semester be opened at all? (meeting point 4)
    if is_exam_admin(request.user):
        from .services import revaluation_eligible_students
        eligible = revaluation_eligible_students(semester)
        data["eligible_students"] = eligible
        data["can_open"] = eligible > 0
    return Response(data)


# ---------- STUDENT: which examination can be revalued ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revaluation_latest(request):
    """
    The student's latest examination - the only one revaluation is open for -
    with its window status. The student screen shows just this semester
    (review item 4.7). { "semester": 3 | null, "window": {...} | null }
    """
    if request.user.role != "student":
        return Response({"detail": "Students only."}, status=403)
    from .services import latest_published_semester
    sem = latest_published_semester(request.user)
    if sem is None:
        return Response({"semester": None, "window": None})
    window = RevaluationWindow.objects.filter(semester=sem).first()
    return Response({
        "semester": sem,
        "window": RevaluationWindowSerializer(window).data if window
        else {"semester": sem, "is_open": False, "fee_amount": None},
    })


# ---------- STUDENT: list own revaluation requests ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_revaluations(request):
    if request.user.role != "student":
        return Response({"detail": "Students only."}, status=403)

    qs = RevaluationRequest.objects.filter(
        student=request.user
    ).select_related("result_entry__subject", "result_entry__result", "fee")

    return Response(RevaluationRequestSerializer(qs, many=True).data)


# ---------- STUDENT: apply for revaluation ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_revaluation(request):
     
    if request.user.role != "student":
        return Response({"detail": "Students only."}, status=403)

    entry_id = request.data.get("result_entry")
    if not entry_id:
        return Response({"detail": "result_entry is required."}, status=400)

    try:
        entry = ResultEntry.objects.select_related("result", "subject").get(id=entry_id)
    except ResultEntry.DoesNotExist:
        return Response({"detail": "Result not found."}, status=404)

    if entry.result.student_id != request.user.id:
        return Response({"detail": "Not your result."}, status=403)

    if not entry.result.is_published:
        return Response({"detail": "Result not published yet."}, status=400)

    if RevaluationRequest.objects.filter(student=request.user, result_entry=entry).exists():
        return Response({"detail": "You already applied for this subject."}, status=400)

    # only the LATEST examination can be revalued (review item 4.6, meeting point 4)
    from .services import latest_published_semester
    latest = latest_published_semester(request.user)
    if entry.result.semester != latest:
        return Response(
            {"detail": f"Revaluation is only for your latest examination (Semester {latest})."},
            status=400
        )

    # window must be open for this semester
    window = RevaluationWindow.objects.filter(semester=entry.result.semester).first()
    if not window or not window.is_open:
        return Response(
            {"detail": "Revaluation portal is not open for this semester."},
            status=400
        )

    # create the fee using the window's amount
    fee = Fee.objects.create(
        student=request.user,
        term=REVALUATION_FEE_TERM,
        amount=window.fee_amount,
        due_date=datetime.date.today(),
        status="pending",
    )

    revreq = RevaluationRequest.objects.create(
        student=request.user,
        result_entry=entry,
        status="pending_payment",
        original_marks=entry.marks_obtained,
        fee=fee,
    )

    return Response(RevaluationRequestSerializer(revreq).data, status=201)


# ---------- STUDENT: confirm payment -> move to review ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_revaluation_payment(request, pk):
    try:
        revreq = RevaluationRequest.objects.select_related("fee").get(id=pk, student=request.user)
    except RevaluationRequest.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    if revreq.fee and revreq.fee.status == "paid" and revreq.status == "pending_payment":
        revreq.status = "pending_review"
        revreq.save()

    return Response(RevaluationRequestSerializer(revreq).data)


# ---------- ADMIN: list requests to review ----------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def revaluation_review_list(request):
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    qs = RevaluationRequest.objects.exclude(
        status="pending_payment"
    ).select_related("result_entry__subject", "result_entry__result", "student", "fee")

    return Response(RevaluationRequestSerializer(qs, many=True).data)


# ---------- ADMIN: process a request ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_revaluation(request, pk):
    
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    try:
        revreq = RevaluationRequest.objects.select_related("result_entry").get(id=pk)
    except RevaluationRequest.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    if revreq.status not in ["pending_review", "revised", "retained"]:
        return Response({"detail": "This request can't be processed yet."}, status=400)

    retain = request.data.get("retain", False)

    if retain:
        revreq.status = "retained"
        revreq.revised_marks = None
        revreq.save()
        return Response(RevaluationRequestSerializer(revreq).data)

    revised = request.data.get("revised_marks")
    if revised is None:
        return Response({"detail": "revised_marks required (or set retain=true)."}, status=400)

    # update the official result entry + recompute grade
    # WAVE 3 PART 1B: graded by the student's regulation. With internal and
    # end-semester marks, revaluation changes the END-SEMESTER part: the
    # revised marks are the new total, the internal mark stays.
    from .grading import GradingError, grade as grade_marks, rules_for
    entry = revreq.result_entry
    try:
        revised = float(revised)
        rules = rules_for(entry.result.student, entry.subject)
        if entry.internal_marks is not None and rules is not None:
            g = grade_marks(rules, internal=entry.internal_marks, end=revised - entry.internal_marks)
        else:
            g = grade_marks(rules, total=revised, max_marks=entry.max_marks)
    except (GradingError, TypeError, ValueError) as e:
        return Response({"detail": str(e) or "revised_marks must be a number."}, status=400)
    entry.marks_obtained = g["marks_obtained"]
    entry.end_marks = g["end_marks"]
    entry.grade = g["grade"]
    entry.is_pass = g["is_pass"]
    entry.grade_points = g["points"]
    entry.outcome = g["outcome"]
    entry.save()

    revreq.revised_marks = revised
    revreq.status = "revised"
    revreq.save()

    return Response(RevaluationRequestSerializer(revreq).data)

# ---------- STUDENT: cancel an unpaid request ----------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_revaluation(request, pk):
    """
    Student cancels their own request — only allowed before payment.
    Deletes the request and its unpaid fee.
    """
    try:
        revreq = RevaluationRequest.objects.select_related("fee").get(
            id=pk, student=request.user
        )
    except RevaluationRequest.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    if revreq.status != "pending_payment":
        return Response(
            {"detail": "Only unpaid requests can be cancelled."},
            status=400
        )

    # remove the unpaid fee too
    if revreq.fee and revreq.fee.status != "paid":
        revreq.fee.delete()

    revreq.delete()
    return Response({"status": "cancelled"})

# ===================== EXAM FEE: ADMIN GENERATE =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_exam_fees(request):
    """
    Raise the semester exam fee for a whole class.

    The term string is built by _exam_fee_term — the SAME helper
    _exam_fee_unpaid reads when deciding whether to block a hall ticket. Typing
    it by hand in the fee screen was one space away from a silent failure: the
    fee would exist, look right, and block nobody.

    Body: {course, year, semester, amount, due_date}
    """
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)

    course = request.data.get("course")
    year = request.data.get("year")
    semester = request.data.get("semester")
    amount = request.data.get("amount")
    due_date = request.data.get("due_date") or None

    if not (course and year and semester and amount):
        return Response(
            {"detail": "course, year, semester and amount are required."},
            status=400,
        )

    # Fee.due_date is NOT NULL. Default to 14 days out, as the fines roster does.
    if not due_date:
        due_date = datetime.date.today() + datetime.timedelta(days=14)

    students = User.objects.filter(
        role="student", course_id=course, year=year, semester=semester,
    )

    term = _exam_fee_term(semester)

    created = 0
    skipped = 0
    for s in students:
        _, was_created = Fee.objects.get_or_create(
            student=s,
            term=term,
            defaults={"amount": amount, "due_date": due_date, "status": "pending"},
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return Response({
        "message": (
            f'{created} exam fee(s) raised as "{term}". '
            f"{skipped} student(s) already had one — their amount was not changed."
        ),
        "term": term,
        "created": created,
        "skipped": skipped,
    })