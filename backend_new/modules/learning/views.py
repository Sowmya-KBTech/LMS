# ===================== IMPORTS =====================
import os
import json
import re
import requests
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import viewsets
from rest_framework.decorators import (  api_view, permission_classes, action)
from rest_framework.permissions import ( IsAuthenticated)
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied

from config.module_registry import optional_model
from core.academics.models import TeachingAssignment, Enrollment
from modules.learning.models import (
    Lecture,
    Assignment,
    Submission,
    Quiz,
    Question,
    QuizAttempt,
    StudyMaterial,
    DiscussionMessage,
    Feedback,
    MaterialFolder,
)
from core.notifications.models import Notification

from modules.learning.serializers import (
    LectureSerializer,
    AssignmentSerializer,
    SubmissionSerializer,
    QuizSerializer,
    QuestionSerializer,
    QuestionAdminSerializer,
    QuizAttemptSerializer,
    StudyMaterialSerializer,
    DiscussionMessageSerializer,
    FeedbackSerializer,
    MaterialFolderSerializer,
)
from core.academics.helpers import get_parent_children, get_enrolled_ta_ids, IsAdminOrTeacherOrReadOnly
from core.permissions import is_college_admin          # PHASE 5
from django.db.models import Q


def _my_teaching_assignment_ids(user):
    """PHASE 5 PART 3: the subject-classes this user belongs to, or None = all (admin).
    Teacher: the ones they teach, plus their department's as HOD. Student: the ones
    they are enrolled in. Anyone else: none."""
    if is_college_admin(user):
        return None
    role = getattr(user, "role", None)
    if role == "teacher":
        from core.users.acting_hod import hod_department_ids
        q = Q(teacher=user)
        dept_ids = hod_department_ids(user)
        if dept_ids:
            q |= Q(subject__department_id__in=dept_ids)
        return set(TeachingAssignment.objects.filter(q).values_list("id", flat=True))
    if role == "student":
        return set(Enrollment.objects.filter(student=user)
                   .values_list("teaching_assignment_id", flat=True))
    return set()


def _teaches(user, teaching_assignment):
    """PHASE 5: is this user the teacher of that subject-class (or an admin)?"""
    if is_college_admin(user):
        return True
    return (teaching_assignment is not None
            and getattr(user, "role", None) == "teacher"
            and teaching_assignment.teacher_id == user.id)

User = get_user_model()

# Attendance is optional: when it is switched off, progress shows 0% attendance.
Attendance = optional_model("attendance", "attendance", "Attendance")


# ===================== STUDENT PROGRESS HELPER =====================
def calculate_student_progress(student, ta):

    # ================= ATTENDANCE =================
    total_attendance = Attendance.objects.filter(
        student=student,
        teaching_assignment=ta
    ).count()

    # FIX #37: approved on-duty counts as present, the same rule the
    # Attendance page and the 75% hall-ticket check already use
    present_attendance = Attendance.objects.filter(
        student=student,
        teaching_assignment=ta,
        status__in=("present", "duty_leave")
    ).count()

    attendance_percent = (
        round((present_attendance / total_attendance) * 100, 1)
        if total_attendance > 0
        else 0
    )

    # ================= ASSIGNMENTS =================
    total_assignments = Assignment.objects.filter(
        teaching_assignment=ta
    ).count()

    submitted_assignments = Submission.objects.filter(
        student=student,
        assignment__teaching_assignment=ta
    ).count()

    assignment_percent = (
        round((submitted_assignments / total_assignments) * 100, 1)
        if total_assignments > 0
        else 0
    )

    # ================= QUIZ AVERAGE =================
    # FIX #6: QuizAttempt.score is RAW marks (3 out of 3), but this value is
    # shown as a percentage, so 3/3 used to appear as "3%". Each attempt is now
    # turned into a percentage of that quiz's total marks first, then averaged
    # (every quiz counts equally, whatever its size).
    # Quizzes not attempted are NOT counted here; they appear in
    # pending_activities instead.
    from django.db.models import Sum
    attempts = (
        QuizAttempt.objects
        .filter(student=student, quiz__teaching_assignment=ta, status="submitted")   # WAVE 3 PART 3
        .select_related("quiz")
    )
    # WAVE 3 PART 3: the test's own total (online tests have no old-style questions)
    quiz_totals = dict(
        Quiz.objects.filter(teaching_assignment=ta).values_list("id", "total_marks")
    )
    quiz_pcts = []
    for a in attempts:
        total = quiz_totals.get(a.quiz_id) or 0
        if total > 0:
            quiz_pcts.append(min(a.score / total, 1) * 100)

    avg_quiz_score = (
        round(sum(quiz_pcts) / len(quiz_pcts), 1)
        if quiz_pcts
        else 0
    )

    # ================= PENDING ASSIGNMENTS =================
    pending_assignments = []

    submitted_ids = Submission.objects.filter(
        student=student,
        assignment__teaching_assignment=ta
    ).values_list(
        "assignment_id",
        flat=True
    )

    for assignment in Assignment.objects.filter(
        teaching_assignment=ta
    ).exclude(id__in=submitted_ids):

        pending_assignments.append({
            "type": "assignment",
            "title": assignment.title,
            "due_date": assignment.due_date
        })

    # ================= PENDING QUIZZES =================
    pending_quizzes = []

    attempted_ids = QuizAttempt.objects.filter(
        student=student,
        quiz__teaching_assignment=ta
    ).values_list(
        "quiz_id",
        flat=True
    )

    for quiz in Quiz.objects.filter(
        teaching_assignment=ta, is_published=True
    ).exclude(id__in=attempted_ids):

        pending_quizzes.append({
            "type": "quiz",
            "title": quiz.title,
            "due_date": quiz.due_date
        })

    # ================= OVERALL PROGRESS =================
    scores = []

    if total_attendance > 0:
        scores.append(attendance_percent)

    if total_assignments > 0:
        scores.append(assignment_percent)

    total_quizzes = Quiz.objects.filter(
        teaching_assignment=ta, is_published=True
    ).count()

    # FIX #6: only count the quiz part once the student has attempted one;
    # a 0 here would mean "nothing attempted yet", not "scored zero"
    if total_quizzes > 0 and quiz_pcts:
        scores.append(avg_quiz_score)

    overall_progress = (
        round(sum(scores) / len(scores), 1)
        if scores
        else 0
    )

    return {
        "attendance_percent": attendance_percent,
        "assignment_percent": assignment_percent,
        "quiz_average": avg_quiz_score,
        "quizzes_attempted": len(quiz_pcts),   # FIX #6: e.g. "1 of 3 attempted"
        "quizzes_total": total_quizzes,
        "overall_progress": overall_progress,
        # FIX #18: tell the screen which parts have any data yet, so a subject
        # with no classes / work shows "No data yet" instead of a misleading 0%
        "has_attendance": total_attendance > 0,
        "has_assignments": total_assignments > 0,
        "has_quizzes": bool(quiz_pcts),
        "has_data": bool(scores),
        "pending_activities": (
            pending_assignments +
            pending_quizzes
        )
    }


# ===================== LECTURE =====================
class LectureViewSet(viewsets.ModelViewSet):

    serializer_class = LectureSerializer
    permission_classes = [IsAdminOrTeacherOrReadOnly]

    def get_queryset(self):

        user = self.request.user

        queryset = Lecture.objects.select_related(
            "teaching_assignment",
            "created_by"
        )

        if user.role == "admin":
            pass

        elif user.role == "teacher":
            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )

        elif user.role == "student":
            queryset = queryset.filter(
                teaching_assignment_id__in=get_enrolled_ta_ids(user)
            )

        else:
            return Lecture.objects.none()
        ta = self.request.query_params.get(
            "teaching_assignment"
        )

        if ta:
            queryset = queryset.filter(
                teaching_assignment_id=ta
            )

        return queryset.order_by(
            "-created_at"
        )

    def perform_create(self, serializer):
        lecture = serializer.save(
            created_by=self.request.user
        )

        students = Enrollment.objects.filter(
            teaching_assignment=
            lecture.teaching_assignment
        )

# ================= STUDENT + PARENT NOTIFICATIONS =================
        from core.notifications.services import notify_parents
        for e in students:
             Notification.objects.create(
                recipient=e.student,
                title="New Lecture Uploaded",
                message=f"{lecture.title} has been uploaded",
                notification_type='lecture',
                teaching_assignment=lecture.teaching_assignment
            )
             notify_parents(
                e.student,
                "New Lecture for your child",
                f"{lecture.title} has been uploaded",
                'lecture',
                lecture.teaching_assignment
            )
       

# ================= TEACHER NOTIFICATION =================
        Notification.objects.create(
            recipient=lecture.teaching_assignment.teacher,
            title="Lecture Uploaded Successfully",
            message=f"You uploaded {lecture.title}",
            notification_type='lecture',
            teaching_assignment=lecture.teaching_assignment
        )


# ===================== ASSIGNMENT =====================
class AssignmentViewSet(viewsets.ModelViewSet):

    serializer_class = AssignmentSerializer
    permission_classes = [IsAdminOrTeacherOrReadOnly]
    def get_queryset(self):
 
        user = self.request.user
        queryset = Assignment.objects.select_related(
            "teaching_assignment",
            "created_by",
        )
 
        if user.role == "admin":
            pass
 
        elif user.role == "teacher":
            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )
 
        elif user.role == "student":
            queryset = queryset.filter(
                teaching_assignment_id__in=get_enrolled_ta_ids(user)
            )
 
        elif user.role == "parent":
            children = get_parent_children(user)
            child = self.request.query_params.get("child")
            if child:
                children = children.filter(id=child)
            child_ta_ids = Enrollment.objects.filter(
                student__in=children
            ).values_list("teaching_assignment_id", flat=True)
            queryset = queryset.filter(
                teaching_assignment_id__in=child_ta_ids
            )
 
        else:
            return Assignment.objects.none()
 
        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)
 
        return queryset.order_by("-created_at")
 
    # ================= CREATE =================
    def perform_create(self, serializer):

        assignment = serializer.save(
            created_by=self.request.user
        )

        students = Enrollment.objects.filter(
            teaching_assignment=
            assignment.teaching_assignment
        )

        # ================= STUDENT NOTIFICATIONS =================
        for e in students:

            Notification.objects.create(
                recipient=e.student,
                title="New Assignment",
                message=f"{assignment.title} has been uploaded",
                notification_type='assignment',
                teaching_assignment=assignment.teaching_assignment
            )

        # ================= TEACHER NOTIFICATION =================
        Notification.objects.create(
            recipient=assignment.teaching_assignment.teacher,
            title="Assignment Uploaded Successfully",
            message=f"You uploaded {assignment.title}",
            notification_type='assignment',
            teaching_assignment=assignment.teaching_assignment
        )


# ===================== SUBMISSION =====================
class SubmissionViewSet(viewsets.ModelViewSet):
 
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated]
 
    def get_queryset(self):
 
        user = self.request.user
 
        queryset = Submission.objects.select_related(
            "assignment",
            "assignment__teaching_assignment",
            "assignment__teaching_assignment__subject",
            "assignment__teaching_assignment__course",
            "assignment__teaching_assignment__year",
            "student",
        )
 
        if user.role == "admin":
            pass
 
        elif user.role == "teacher":
            queryset = queryset.filter(
                assignment__teaching_assignment__teacher=user
            )
 
        elif user.role == "student":
            queryset = queryset.filter(student=user)
 
        elif user.role == "parent":
            children = get_parent_children(user)
            child = self.request.query_params.get("child")
            if child:
                children = children.filter(id=child)
            queryset = queryset.filter(student__in=children)
 
        else:
            return Submission.objects.none()
 
        assignment = self.request.query_params.get("assignment")
        if assignment:
            queryset = queryset.filter(assignment_id=assignment)
 
        return queryset.order_by("-submitted_at")
 
    
    # ================= CREATE / RESUBMIT =================
    def perform_create(self, serializer):

        assignment = serializer.validated_data.get(
            "assignment"
        )

        existing = Submission.objects.filter(
            student=self.request.user,
            assignment=assignment
        ).first()

        teacher = assignment.teaching_assignment.teacher

        # ================= RESUBMISSION =================
        if existing:

            existing.file = serializer.validated_data.get(
                "file"
            )

            existing.submitted_at = timezone.now()
            existing.marks = None
            existing.feedback = ""
            existing.graded_at = None

            if (
                assignment.due_date
                and timezone.now() > assignment.due_date
            ):

                existing.status = "late"

                # STUDENT NOTIFICATION
                Notification.objects.create(
                    recipient=self.request.user,
                    title="Late Assignment Resubmitted",
                    message=f"You resubmitted {assignment.title} after the deadline.",
                    notification_type="assignment",
                    teaching_assignment=assignment.teaching_assignment
                )

                # TEACHER NOTIFICATION
                Notification.objects.create(
                    recipient=teacher,
                    title="Late Resubmission Received",
                    message=f"{self.request.user.username} resubmitted {assignment.title} after the due date.",
                    notification_type="assignment",
                    teaching_assignment=assignment.teaching_assignment
                )

            else:

                existing.status = "pending"

            existing.save()

            # TEACHER NOTIFICATION
            Notification.objects.create(
                recipient=teacher,
                title="Assignment Resubmitted",
                message=f"{self.request.user.username} resubmitted {assignment.title}",
                notification_type="assignment",
                teaching_assignment=assignment.teaching_assignment
            )

            return

        # ================= NEW SUBMISSION =================
        submission = serializer.save(
            student=self.request.user
        )

        if (
            assignment.due_date
            and timezone.now() > assignment.due_date
        ):

            submission.status = "late"
            submission.save()

            # STUDENT NOTIFICATION
            Notification.objects.create(
                recipient=self.request.user,
                title="Late Assignment Submitted",
                message=f"You submitted {assignment.title} after the deadline.",
                notification_type="assignment",
                teaching_assignment=assignment.teaching_assignment
            )

            # TEACHER NOTIFICATION
            Notification.objects.create(
                recipient=teacher,
                title="Late Submission Received",
                message=f"{self.request.user.username} submitted {assignment.title} after the due date.",
                notification_type="assignment",
                teaching_assignment=assignment.teaching_assignment
            )

        # NORMAL TEACHER NOTIFICATION
        Notification.objects.create(
            recipient=teacher,
            title="New Assignment Submission",
            message=f"{self.request.user.username} submitted {assignment.title}",
            notification_type="assignment",
            teaching_assignment=assignment.teaching_assignment
        )

    # ================= UPDATE GRADING =================
    def perform_update(self, serializer):

        # FIX #24: remember the marks BEFORE this save, so we only notify when
        # marks are given for the first time or actually change. Saving only
        # the feedback (or saving twice) used to send "Marks Published" again.
        old_marks = serializer.instance.marks

        submission = serializer.save()

        if submission.marks is not None:

            submission.status = "evaluated"

            submission.graded_at = timezone.now()

            submission.save()

            if old_marks != submission.marks:
                assignment = submission.assignment
                total = assignment.total_marks
                first_time = old_marks is None
                title = "Marks Published" if first_time else "Marks updated"
                m = submission.marks
                m_txt = int(m) if float(m).is_integer() else m          # 7.0 -> 7
                score = f"{m_txt}/{total}" if total else f"{m_txt}"

                # STUDENT NOTIFICATION
                # FIX #24: type 'marks' (was 'assignment'), so it shows under the
                # Marks tab and opens Grades
                Notification.objects.create(
                    recipient=submission.student,
                    title=title,
                    message=f"{assignment.title}: you scored {score}.",
                    notification_type="marks",
                    teaching_assignment=assignment.teaching_assignment
                )

                # PARENT NOTIFICATION
                from core.notifications.services import notify_parents
                notify_parents(
                    submission.student,
                    f"{title} for your child",
                    f"{submission.student.username} – {assignment.title}: {score}.",
                    'marks',
                    assignment.teaching_assignment
                )


        
# ===================== QUIZ AI =====================
# correct_answer is 1-BASED: 1 -> option1 ... 4 -> option4.
# Confirmed against live data. Do not change without also changing the grading
# comparison in the quiz submit action.
OPTION_COUNT = 4


MIN_CORRECT = 1


MAX_CORRECT = OPTION_COUNT


OPTION_MAX_LEN = 200          # Question.option1..4 are CharField(max_length=200)


MAX_GENERATE = 30


def _quiz_ai_generate(subject_name, notes, count):
    """
    Ask Gemini for `count` MCQs from the teacher's pasted notes.
    Sends ONLY subject name + notes + count. No student data — the Gemini free
    tier may train on prompts.
    Does NOT validate content; that is save_questions' job.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    prompt = (
        f"Write {count} multiple-choice questions for a college subject "
        f"called \"{subject_name}\", based ONLY on the notes below.\n\n"
        "NOTES:\n" + notes + "\n\n"
        "Rules:\n"
        f"- Exactly {OPTION_COUNT} options per question.\n"
        "- Exactly ONE option is correct.\n"
        "- correct_answer is the 1-based position of the correct option "
        "(1 = first option, 4 = fourth option).\n"
        f"- Keep every option under {OPTION_MAX_LEN} characters.\n"
        "- Do not repeat a question.\n\n"
        "Return ONLY a JSON array, no markdown, no explanation:\n"
        '[{"text": "...", "option1": "...", "option2": "...", '
        '"option3": "...", "option4": "...", "correct_answer": 1}]'
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-flash-latest:generateContent?key=" + key
    )
    r = requests.post(
        url,
        headers={"content-type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=90,
    )
    data = r.json()
    if "candidates" not in data:
        raise ValueError(f"Gemini error: {data}")

    text = data["candidates"][0]["content"]["parts"][0]["text"]

    text = re.sub(r"```(?:json)?", "", text).strip()
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError(f"No JSON array in reply: {text[:300]}")

    parsed = json.loads(m.group(0))
    if not isinstance(parsed, list):
        raise ValueError("Gemini did not return a JSON array.")
    return parsed


def _clean_draft_row(row):
    """
    Shape one AI row for the draft grid. Best-effort: a bad row is dropped from
    the DRAFT, never saved silently. Real enforcement is in _validate_question.
    """
    if not isinstance(row, dict):
        return None

    text = str(row.get("text") or "").strip()
    if not text:
        return None

    options = []
    for i in range(1, OPTION_COUNT + 1):
        opt = str(row.get(f"option{i}") or "").strip()
        if not opt:
            return None
        options.append(opt[:OPTION_MAX_LEN])

    try:
        correct = int(row.get("correct_answer"))
    except (TypeError, ValueError):
        return None
    if not (MIN_CORRECT <= correct <= MAX_CORRECT):
        return None

    return {
        "text": text,
        "option1": options[0],
        "option2": options[1],
        "option3": options[2],
        "option4": options[3],
        "correct_answer": correct,
        "marks": 1,
    }


def _validate_question(row, index):
    """
    THE GATE. Every question that reaches the database passes through here —
    AI-generated or hand-edited by the teacher. A human having looked at a draft
    is not validation: a teacher can delete the wrong option just as easily as
    the model can.
    Returns (cleaned_dict, error_string) — exactly one of the two is None.
    """
    label = f"Question {index}"

    if not isinstance(row, dict):
        return None, f"{label}: not a valid question."

    text = str(row.get("text") or "").strip()
    if not text:
        return None, f"{label}: question text is empty."

    options = []
    for i in range(1, OPTION_COUNT + 1):
        opt = str(row.get(f"option{i}") or "").strip()
        if not opt:
            return None, f"{label}: option {i} is empty."
        if len(opt) > OPTION_MAX_LEN:
            return None, (
                f"{label}: option {i} is {len(opt)} characters "
                f"(max {OPTION_MAX_LEN})."
            )
        options.append(opt)

    try:
        correct = int(row.get("correct_answer"))
    except (TypeError, ValueError):
        return None, f"{label}: correct answer must be a number from 1 to {MAX_CORRECT}."
    if not (MIN_CORRECT <= correct <= MAX_CORRECT):
        return None, (
            f"{label}: correct answer is {correct}, "
            f"must be from {MIN_CORRECT} to {MAX_CORRECT}."
        )

    try:
        marks = int(row.get("marks", 1))
    except (TypeError, ValueError):
        return None, f"{label}: marks must be a whole number."
    if marks < 1:
        return None, f"{label}: marks must be at least 1."

    return {
        "text": text,
        "option1": options[0],
        "option2": options[1],
        "option3": options[2],
        "option4": options[3],
        "correct_answer": correct,
        "marks": marks,
    }, None


# ===================== QUIZ =====================
class QuizViewSet(viewsets.ModelViewSet):

    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        queryset = Quiz.objects.prefetch_related(
            "questions"
        ).select_related(
            "teaching_assignment",
            "created_by",
        )

        if user.role == "admin":
            pass

        elif user.role == "teacher":
            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )

        elif user.role == "student":
            queryset = queryset.filter(
                teaching_assignment_id__in=get_enrolled_ta_ids(user),
                is_published=True,          # WAVE 3 PART 3: drafts stay with the teacher
            )

        elif user.role == "parent":
            queryset = queryset.filter(is_published=True)    # WAVE 3 PART 3
            # quizzes for the teaching assignments the parent's children
            # are enrolled in (Quiz has no student field — scope by TA)
            children = get_parent_children(user)
            child_ta_ids = Enrollment.objects.filter(
                student__in=children
            ).values_list("teaching_assignment_id", flat=True)
            queryset = queryset.filter(
                teaching_assignment_id__in=child_ta_ids
            )

        else:
            return Quiz.objects.none()

        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)

        return queryset.order_by("-created_at")

    # ================= CREATE QUIZ =================
    def perform_create(self, serializer):

        if self.request.user.role not in [
            "teacher",
            "admin"
        ]:

            raise ValidationError(
                "Only teachers can create quizzes"
            )

        quiz = serializer.save(
            created_by=self.request.user
        )

        students = Enrollment.objects.filter(
            teaching_assignment=
            quiz.teaching_assignment
        )

        # ================= STUDENT NOTIFICATIONS =================
        for e in students:

            Notification.objects.create(
                recipient=e.student,
                title="New Quiz Added",
                # FIX #3: tell students the closing time
                message=(f"{quiz.title} is available now · closes "
                         f"{timezone.localtime(quiz.due_date):%d %b %Y, %I:%M %p}"
                         if quiz.due_date else f"{quiz.title} is available now"),
                notification_type='quiz',
                teaching_assignment=quiz.teaching_assignment
            )

        # ================= TEACHER NOTIFICATION =================
        Notification.objects.create(
            recipient=quiz.teaching_assignment.teacher,
            title="Quiz Created Successfully",
            message=f"You created {quiz.title}",
            notification_type='quiz',
            teaching_assignment=quiz.teaching_assignment
        )
    # ================= DELETE QUIZ =================
    def destroy(self, request, *args, **kwargs):

        if request.user.role not in [
            "teacher",
            "admin"
        ]:

            return Response(
                {
                    "error":
                    "Only teachers can delete quizzes"
                },
                status=403
            )

        return super().destroy(
            request,
            *args,
            **kwargs
        )

    # ================= SUBMIT QUIZ =================
    @action(detail=False, methods=['post'])
    def submit(self, request):

        quiz_id = request.data.get("quiz")

        answers = request.data.get(
            "answers",
            {}
        )

        try:

            quiz = Quiz.objects.prefetch_related(
                "questions"
            ).get(id=quiz_id)

        except Quiz.DoesNotExist:

            return Response(
                {"error": "Quiz not found"},
                status=404
            )

        already_attempted = QuizAttempt.objects.filter(
            quiz=quiz,
            student=request.user
        ).exists()

        if already_attempted:

            return Response(
                {
                    "error":
                    "You already attended this quiz"
                },
                status=400
            )

        # FIX #3: no answers after the closing time. A student who started just
        # before it gets the quiz's own duration as grace to finish.
        if quiz.due_date:
            from datetime import timedelta
            grace = timedelta(minutes=quiz.duration or 0)
            if timezone.now() > quiz.due_date + grace:
                return Response(
                    {"error": "This quiz is closed. The last time to attempt it has passed."},
                    status=400
                )

        score = 0

        for q in quiz.questions.all():

            selected_answer = answers.get(
                str(q.id)
            )

            if selected_answer is not None:

                try:

                    if int(selected_answer) == int(q.correct_answer):

                        score += q.marks

                except (ValueError, TypeError):

                    pass

        # ================= SAVE QUIZ ATTEMPT =================
        QuizAttempt.objects.create(

            quiz=quiz,
            student=request.user,
            score=score
        )

        # ================= TEACHER NOTIFICATION =================
        teacher = quiz.teaching_assignment.teacher

        Notification.objects.create(

            recipient=teacher,
            title="Quiz Submitted",
            message=f"{request.user.username} completed {quiz.title}",
            notification_type="quiz",
            teaching_assignment=quiz.teaching_assignment
        )

        return Response({

            "message": "Quiz submitted successfully",
            "score": score,
            "total_marks": quiz.total_marks
        })
    
    # ================= AI: GENERATE DRAFT QUESTIONS =================
    @action(detail=True, methods=["post"], url_path="generate-questions")
    def generate_questions(self, request, pk=None):
        """
        Teacher pastes notes -> Gemini proposes questions -> returned as a DRAFT.
        NOTHING IS SAVED HERE. Only save_questions writes rows.

        Ownership comes free from get_queryset (a teacher's queryset is filtered
        to teaching_assignment__teacher=user), so get_object() cannot return
        another teacher's quiz. No second ownership rule is defined here.
        """
        quiz = self.get_object()

        if request.user.role not in ("teacher", "admin"):
            raise PermissionDenied("Only teachers can generate questions.")

        notes = (request.data.get("notes") or "").strip()
        if not notes:
            raise ValidationError("Paste the notes to generate questions from.")

        try:
            count = int(request.data.get("count", 10))
        except (TypeError, ValueError):
            count = 10
        count = max(1, min(MAX_GENERATE, count))

        subject_name = quiz.teaching_assignment.subject.name

        try:
            raw = _quiz_ai_generate(subject_name, notes, count)
        except Exception as e:
            # Surface it. A silent empty draft is exactly the bug that hides for weeks.
            return Response(
                {"detail": f"Could not generate questions: {e}"},
                status=502,
            )

        draft = [c for c in (_clean_draft_row(r) for r in raw) if c]

        note = None
        if len(draft) < count:
            note = (
                f"AI returned {len(draft)} usable question(s) out of {count} "
                "requested. Review them, then add more if you need them."
            )

        return Response({
            "draft": draft,          # NOT saved — the teacher reviews this first
            "requested": count,
            "note": note,
        })

    # ================= SAVE REVIEWED QUESTIONS =================
    @action(detail=True, methods=["post"], url_path="save-questions")
    def save_questions(self, request, pk=None):
        """
        The teacher submits the reviewed/edited draft. This is the ONLY path that
        creates Question rows, and every row is validated here first.

        All-or-nothing: if any question fails, none are saved. A half-written quiz
        is worse than a rejected one — a student would sit it and be graded on the
        half that landed.

        Questions are APPENDED. Existing (including hand-written) ones are untouched.
        """
        quiz = self.get_object()

        if request.user.role not in ("teacher", "admin"):
            raise PermissionDenied("Only teachers can save questions.")

        questions = request.data.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValidationError("Send at least one question to save.")

        cleaned, errors = [], []
        for i, row in enumerate(questions, start=1):
            ok, err = _validate_question(row, i)
            if err:
                errors.append(err)
            else:
                cleaned.append(ok)

        if errors:
            return Response(
                {"detail": "No questions were saved. Fix these first:", "errors": errors},
                status=400,
            )

        created = [Question.objects.create(quiz=quiz, **row) for row in cleaned]

        # get_queryset uses prefetch_related("questions"), so quiz.questions.all()
        # is a CACHE captured before these rows existed — it would sum to zero.
        # Query the table directly for the real, current set.
        all_questions = Question.objects.filter(quiz=quiz)

        # total_marks is DERIVED, never taken from the client.
        quiz.total_marks = sum(q.marks for q in all_questions)
        quiz.save(update_fields=["total_marks"])

        return Response({
            "message": f"{len(created)} question(s) saved.",
            "created": len(created),
            "total_questions": all_questions.count(),
            "total_marks": quiz.total_marks,
        })


# ===================== QUESTION =====================
class QuestionViewSet(viewsets.ModelViewSet):

    permission_classes = [
        IsAdminOrTeacherOrReadOnly
    ]

    # teachers/admins get the full serializer (with answer);
    # students get the safe one (no answer)
    def get_serializer_class(self):

        user = self.request.user

        if (
            user.is_authenticated
            and user.role in ['teacher', 'admin']
        ):
            return QuestionAdminSerializer

        return QuestionSerializer

    def get_queryset(self):

        queryset = Question.objects.all()

        # PHASE 5 PART 3: only questions of quizzes in this user's own subject-classes
        # (teacher: theirs; student: enrolled; parents and others: none)
        allowed = _my_teaching_assignment_ids(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(
                Q(quiz__teaching_assignment_id__in=allowed) | Q(quiz__created_by=self.request.user))

        quiz = self.request.query_params.get(
            "quiz"
        )

        if quiz:

            queryset = queryset.filter(
                quiz_id=quiz
            )

        return queryset.order_by("id")

    # PHASE 5: a teacher may change questions only in their OWN quizzes
    def _require_quiz_owner(self, quiz):
        user = self.request.user
        if quiz is None or not (_teaches(user, quiz.teaching_assignment)
                                or quiz.created_by_id == user.id):
            raise PermissionDenied("You can only change questions in your own quizzes.")

    def perform_create(self, serializer):
        self._require_quiz_owner(serializer.validated_data.get("quiz"))
        serializer.save()

    def perform_update(self, serializer):
        self._require_quiz_owner(serializer.instance.quiz)
        if "quiz" in serializer.validated_data:
            self._require_quiz_owner(serializer.validated_data["quiz"])
        serializer.save()

    def perform_destroy(self, instance):
        self._require_quiz_owner(instance.quiz)
        instance.delete()


    
# ===================== QUIZ ATTEMPT =====================
class QuizAttemptViewSet(viewsets.ModelViewSet):

    serializer_class = QuizAttemptSerializer

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
 
        user = self.request.user
        # WAVE 3 PART 3: a test still being written is not a result yet
        queryset = QuizAttempt.objects.select_related("quiz", "student").filter(status="submitted")
 
        if user.role == "admin":
            pass
 
        elif user.role == "teacher":
            queryset = queryset.filter(
                quiz__teaching_assignment__teacher=user
            )
 
        elif user.role == "student":
            queryset = queryset.filter(student=user)
 
        elif user.role == "parent":
            children = get_parent_children(user)
            child = self.request.query_params.get("child")
            if child:
                children = children.filter(id=child)
            queryset = queryset.filter(student__in=children)
 
        else:
            return QuizAttempt.objects.none()
 
        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
 
        return queryset.order_by("-submitted_at")

    def perform_create(self, serializer):

        raise ValidationError(
            "Use the quiz submit endpoint to attempt a quiz."
        )


# ===================== STUDY MATERIAL =====================
class StudyMaterialViewSet(viewsets.ModelViewSet):

    serializer_class = StudyMaterialSerializer

    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        queryset = StudyMaterial.objects.select_related(
            "uploaded_by",
            "teaching_assignment",
            "teaching_assignment__teacher",
            "teaching_assignment__subject",
            "teaching_assignment__course",
            "teaching_assignment__year",
        )

        if user.role == "admin":
            pass

        elif user.role == "teacher":

            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )

        elif user.role == "student":

            queryset = queryset.filter(
                teaching_assignment_id__in=
                get_enrolled_ta_ids(user)
            )

        else:
            return StudyMaterial.objects.none()

        ta = self.request.query_params.get(
            "teaching_assignment"
        )

        if ta:
            queryset = queryset.filter(
                teaching_assignment_id=ta
            )

        folder = self.request.query_params.get("folder")
        if folder:
            queryset = queryset.filter(folder_id=folder)

        return queryset.order_by(
            "-created_at"
        )

    # PHASE 5: only the teacher of that subject (or an admin) may add, edit or
    # delete its materials - students and parents only read them.
    def perform_update(self, serializer):
        if not _teaches(self.request.user, serializer.instance.teaching_assignment):
            raise PermissionDenied("Only the subject's teacher can change this material.")
        ta = serializer.validated_data.get("teaching_assignment")
        if ta is not None and not _teaches(self.request.user, ta):
            raise PermissionDenied("You can only add materials to your own subjects.")
        serializer.save()

    def perform_destroy(self, instance):
        if not _teaches(self.request.user, instance.teaching_assignment):
            raise PermissionDenied("Only the subject's teacher can delete this material.")
        instance.delete()

    # ================= CREATE =================
    def perform_create(self, serializer):

        if not _teaches(self.request.user, serializer.validated_data.get("teaching_assignment")):
            raise PermissionDenied("You can only add materials to your own subjects.")

        material = serializer.save(
            uploaded_by=self.request.user
        )

        students = Enrollment.objects.filter(
            teaching_assignment=
            material.teaching_assignment
        )

        # ================= STUDENT NOTIFICATIONS =================
        from core.notifications.services import notify_parents
        for e in students:
            Notification.objects.create(
                recipient=e.student,
                title="New Study Material",
                message=f"{material.title} has been uploaded",
                notification_type='material',
                teaching_assignment=material.teaching_assignment
            )
            notify_parents(
                e.student,
                "New Study Material for your child",
                f"{material.title} has been uploaded",
                'material',
                material.teaching_assignment
            )

        # ================= TEACHER NOTIFICATION =================
        Notification.objects.create(
            recipient=material.teaching_assignment.teacher,
            title="Material Uploaded Successfully",
            message=f"You uploaded {material.title}",
            notification_type='material',
            teaching_assignment=material.teaching_assignment
        )


# ===================== DISCUSSION MESSAGE =====================
class DiscussionMessageViewSet(viewsets.ModelViewSet):

    serializer_class = (
        DiscussionMessageSerializer
    )

    permission_classes = [
        IsAuthenticated
    ]

    def get_queryset(self):

        queryset = (
            DiscussionMessage.objects
            .select_related(
                "user",
                "teaching_assignment"
            )
        )

        ta_id = (
            self.request.query_params.get(
                "teaching_assignment"
            )
        )

        if ta_id:

            queryset = queryset.filter(
                teaching_assignment_id=ta_id
            )

        # PHASE 5 PART 3: only discussions of this user's own subject-classes
        allowed = _my_teaching_assignment_ids(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(teaching_assignment_id__in=allowed)

        return queryset.order_by(
            "created_at"
        )

    # PHASE 5: a message may be edited only by its author, and deleted by its
    # author, the subject's teacher (moderation) or an admin.
    def perform_update(self, serializer):
        if serializer.instance.user_id != self.request.user.id:
            raise PermissionDenied("You can only edit your own messages.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.user_id != user.id and not _teaches(user, instance.teaching_assignment):
            raise PermissionDenied("You can only delete your own messages.")
        instance.delete()

    def perform_create(
        self,
        serializer
    ):

        # PHASE 5 PART 3: post only into a discussion you belong to
        ta = serializer.validated_data.get("teaching_assignment")
        allowed = _my_teaching_assignment_ids(self.request.user)
        if ta is None or (allowed is not None and ta.id not in allowed):
            raise PermissionDenied("You can only post in your own subjects' discussions.")

        discussion = serializer.save(
            user=self.request.user
        )

        ta = discussion.teaching_assignment

        # ================= TEACHER POSTS =================
        if self.request.user.role == "teacher":

            students = Enrollment.objects.filter(teaching_assignment=ta)

            for e in students:

                Notification.objects.create(
                    recipient=e.student,
                    title="New Discussion Message",

                    message=(
                        f"{self.request.user.username} "
                        f"posted in "
                        f"{ta.subject.name}"
                    ),

                    notification_type="discussion",
                    teaching_assignment=ta
                )

        # ================= STUDENT POSTS =================
        elif self.request.user.role == "student":

            Notification.objects.create(
                recipient=ta.teacher,
                title="New Discussion Message",
                message=(
                    f"{self.request.user.username} "
                    f"posted in "
                    f"{ta.subject.name}"
                ),

                notification_type="discussion",
                teaching_assignment=ta
            )


# ===================== FEEDBACK =====================
class FeedbackViewSet(viewsets.ModelViewSet):

    serializer_class = FeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        queryset = Feedback.objects.select_related(
            "student",
            "teacher",
            "teaching_assignment",
            "teaching_assignment__subject"
        )

        if user.role == "teacher":

            return queryset.filter(
                teacher=user
            ).order_by("-created_at")

        elif user.role == "student":

            return queryset.filter(
                student=user
            ).order_by("-created_at")

        # PHASE 5: admins see all feedback; parents and other roles see none
        if is_college_admin(user):
            return queryset.order_by("-created_at")
        return queryset.none()

    def _is_author(self, fb):
        user = self.request.user
        if is_college_admin(user):
            return True
        if fb.direction == "s2t":
            return fb.student_id == user.id
        return fb.teacher_id == user.id

    def perform_update(self, serializer):
        if not self._is_author(serializer.instance):
            raise PermissionDenied("You can only change feedback you wrote.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self._is_author(instance):
            raise PermissionDenied("You can only delete feedback you wrote.")
        instance.delete()

    def perform_create(self, serializer):

        user = self.request.user

        teaching_assignment = serializer.validated_data.get(
            "teaching_assignment"
        )

        # ================= STUDENT → TEACHER =================
        if user.role == "student":

            serializer.save(
                student=user,
                teacher=teaching_assignment.teacher,
                direction="s2t"
            )

        # ================= TEACHER → STUDENT =================
        elif user.role == "teacher":

            # FIX #10: "student" is read-only in the serializer, so it never
            # reached validated_data and every teacher feedback was saved with
            # student = None. Read it from the request and check it here.
            if teaching_assignment.teacher_id != user.id:
                raise PermissionDenied("You can only give feedback in your own subjects.")

            student_id = self.request.data.get("student")
            if not student_id:
                raise ValidationError({"student": "Please select a student."})

            enrolment = Enrollment.objects.filter(
                teaching_assignment=teaching_assignment,
                student_id=student_id,
            ).select_related("student").first()
            if not enrolment:
                raise ValidationError({"student": "This student is not in your class for this subject."})

            serializer.save(
                teacher=user,
                student=enrolment.student,
                direction="t2s"
            )


# ===================== MATERIAL FOLDER =====================
class MaterialFolderViewSet(viewsets.ModelViewSet):
 
    serializer_class = MaterialFolderSerializer
    permission_classes = [IsAdminOrTeacherOrReadOnly]
 
    def get_queryset(self):
 
        user = self.request.user
 
        queryset = MaterialFolder.objects.select_related(
            "teaching_assignment", "created_by"
        )
 
        # role-based visibility (same pattern as your other modules)
        if user.role == "admin":
            pass
        elif user.role == "teacher":
            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )
        elif user.role == "student":
            queryset = queryset.filter(
                teaching_assignment_id__in=get_enrolled_ta_ids(user)
            )
        else:
            return MaterialFolder.objects.none()
 
        # always scoped to one subject's tab
        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)
 
        return queryset.order_by("name")
 
    def perform_create(self, serializer):
        if self.request.user.role not in ["teacher", "admin"]:
            raise ValidationError("Only teachers can create folders.")
        serializer.save(created_by=self.request.user)


# ===================== MY PROGRESS =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_progress(request):

    user = request.user

    enrollments = Enrollment.objects.filter(
        student=user
    ).select_related(
        'teaching_assignment',
        'teaching_assignment__subject',
        'teaching_assignment__course'
    )

    data = []

    for enrollment in enrollments:

        ta = enrollment.teaching_assignment

        progress = calculate_student_progress(
            user,
            ta
        )

        data.append({
            "subject": ta.subject.name,
            "course": ta.course.name,
            **progress
        })

    return Response(data)


# ================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def class_progress(request):

    if request.user.role != "teacher":
        return Response(
            {"error": "Only teachers can view class progress"},
            status=403
        )

    ta_id = request.query_params.get("teaching_assignment")

    if not ta_id:
        return Response(
            {"error": "teaching_assignment is required"},
            status=400
        )

    # Verify this class belongs to the logged-in teacher
    ta = TeachingAssignment.objects.filter(
        id=ta_id,
        teacher=request.user
    ).first()

    if not ta:
        return Response(
            {"error": "Class not found"},
            status=404
        )

    enrollments = Enrollment.objects.filter(
        teaching_assignment=ta
    ).select_related("student")

    data = []

    for enrollment in enrollments:

        progress = calculate_student_progress(
            enrollment.student,
            ta
        )

        data.append({
            "student_id": enrollment.student.id,
            "student_name": enrollment.student.username,
            **progress
        })

    return Response(data)