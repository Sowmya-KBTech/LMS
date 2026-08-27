# ===================== IMPORTS =====================
import os
import json
import re
import requests
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models
from decimal import Decimal, InvalidOperation

from rest_framework import viewsets
from rest_framework.decorators import (  api_view, permission_classes, action)
from rest_framework.permissions import ( IsAuthenticated, BasePermission, SAFE_METHODS)
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework import status

from attendance.models import Attendance
from .models import (
    Course,
    Year,
    Subject,
    TeachingAssignment,
    Enrollment,
    Lecture,
    Assignment,
    Submission,
    Quiz,
    Question,
    QuizAttempt,
    StudyMaterial,
    Notification,
    DiscussionMessage,
    Feedback,
    MaterialFolder,
    Fee,
)

from .serializers import (
    CourseSerializer,
    YearSerializer,
    SubjectSerializer,
    TeachingAssignmentSerializer,
    EnrollmentSerializer,
    LectureSerializer,
    AssignmentSerializer,
    SubmissionSerializer,
    QuizSerializer,
    QuestionSerializer,
    QuestionAdminSerializer,
    QuizAttemptSerializer,
    StudyMaterialSerializer,
    NotificationSerializer,
    DiscussionMessageSerializer,
    FeedbackSerializer,
    MaterialFolderSerializer,
    FeeSerializer,
)

User = get_user_model()

def get_parent_children(user):
    from users.models import ParentProfile

    try:
        profile = ParentProfile.objects.prefetch_related(
            "children"
        ).get(user=user)

        return profile.children.all()

    except ParentProfile.DoesNotExist:
        return User.objects.none()

# ===================== PERMISSION =====================
class IsAdminOrTeacherOrReadOnly(BasePermission):

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated

        return (
            request.user.is_authenticated
            and request.user.role in ['teacher', 'admin']
        )

# ===================== HELPER =====================
def get_enrolled_ta_ids(user):
    """Return the teaching_assignment IDs the student is enrolled in."""
    return Enrollment.objects.filter(
        student=user
    ).values_list("teaching_assignment_id", flat=True)

# ===================== STUDENT PROGRESS HELPER =====================
def calculate_student_progress(student, ta):

    # ================= ATTENDANCE =================
    total_attendance = Attendance.objects.filter(
        student=student,
        teaching_assignment=ta
    ).count()

    present_attendance = Attendance.objects.filter(
        student=student,
        teaching_assignment=ta,
        status="present"
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
    attempts = QuizAttempt.objects.filter(
        student=student,
        quiz__teaching_assignment=ta
    )

    avg_quiz_score = (
        round(
            sum(a.score for a in attempts) / attempts.count(),
            1
        )
        if attempts.exists()
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
        teaching_assignment=ta
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
        teaching_assignment=ta
    ).count()

    if total_quizzes > 0:
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
        "overall_progress": overall_progress,
        "pending_activities": (
            pending_assignments +
            pending_quizzes
        )
    }

# ===================== ADMIN DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard(request):
    if request.user.role != "admin":
        return Response({"error": "Unauthorized"}, status=403)

    return Response({
        "total_users": User.objects.count(),
        "total_students": User.objects.filter(role="student").count(),
        "total_teachers": User.objects.filter(role="teacher").count(),
        "total_parents": User.objects.filter(role="parent").count(),
        "total_courses": Course.objects.count(),
        "total_enrollments": Enrollment.objects.count(),
    })


# ===================== TEACHER DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_dashboard(request):
    if request.user.role != "teacher":
        return Response({"error": "Unauthorized"}, status=403)

    tas = TeachingAssignment.objects.filter(teacher=request.user)

    total_students = Enrollment.objects.filter(
        teaching_assignment__teacher=request.user
    ).count()

    return Response({
        "subjects": tas.count(),
        "students": total_students,
        "assignments": Assignment.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "lectures": Lecture.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "quizzes": Quiz.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "materials": StudyMaterial.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
    })


# ===================== COURSE =====================
class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by("name")
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated]


# ===================== YEAR =====================
class YearViewSet(viewsets.ModelViewSet):
    serializer_class = YearSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Year.objects.all()

        course = self.request.query_params.get("course")
        if course:
            queryset = queryset.filter(course_id=course)

        return queryset.select_related("course").order_by("year_number")


# ===================== SUBJECT =====================
class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Subject.objects.all()

        year = self.request.query_params.get("year")
        semester = self.request.query_params.get("semester")

        if year:
            queryset = queryset.filter(year_id=year)
        if semester:
            queryset = queryset.filter(semester=semester)

        return queryset.select_related(
            "year", "year__course"
        ).order_by("name")


# ===================== TEACHING ASSIGNMENT =====================
class TeachingAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = TeachingAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TeachingAssignment.objects.all()

        course = self.request.query_params.get("course")
        year = self.request.query_params.get("year")
        teacher = self.request.query_params.get("teacher")
        my = self.request.query_params.get("my")

        if course:
            queryset = queryset.filter(course_id=course)
        if year:
            queryset = queryset.filter(year_id=year)
        if teacher:
            queryset = queryset.filter(teacher_id=teacher)

        # only the logged-in teacher's own assignments
        if my == "true" and self.request.user.role == "teacher":
            queryset = queryset.filter(teacher=self.request.user)

        return queryset.select_related(
            "course", "year", "subject", "teacher"
        ).order_by("year__year_number")

    def perform_create(self, serializer):
        serializer.save()
        

# ===================== ENROLLMENT =====================
class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = Enrollment.objects.select_related(
            'student',
            'teaching_assignment',
            'teaching_assignment__teacher',
            'teaching_assignment__course',
            'teaching_assignment__year',
            'teaching_assignment__subject',
        )

        # role-based visibility (narrow, don't return yet)
        if user.role in ("admin", "academic_admin"):
            pass
        elif user.role == "teacher":
            queryset = queryset.filter(teaching_assignment__teacher=user)
        elif user.role == "student":
            queryset = queryset.filter(student=user)
        else:
            return Enrollment.objects.none()

        # filter by the selected class (THE FIX)
        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)

        return queryset

    def perform_create(self, serializer):
        serializer.save()


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
        from .signals import notify_parents
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

        submission = serializer.save()

        if submission.marks is not None:

            submission.status = "evaluated"

            submission.graded_at = timezone.now()

            submission.save()

            # STUDENT NOTIFICATION
            Notification.objects.create(
                recipient=submission.student,
                title="Marks Published",
                message=f"Marks have been published for {submission.assignment.title}.",
                notification_type="assignment",
                teaching_assignment=submission.assignment.teaching_assignment
            )

            # PARENT NOTIFICATION
            from .signals import notify_parents
            notify_parents(
                submission.student,
                "Marks Published for your child",
                f"Marks published for {submission.assignment.title}.",
                'marks',
                submission.assignment.teaching_assignment
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
        timeout=45,
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
                teaching_assignment_id__in=get_enrolled_ta_ids(user)
            )

        elif user.role == "parent":
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
                message=f"{quiz.title} is available now",
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

        quiz = self.request.query_params.get(
            "quiz"
        )

        if quiz:

            queryset = queryset.filter(
                quiz_id=quiz
            )

        return queryset.order_by("id")
    
# ===================== QUIZ ATTEMPT =====================
class QuizAttemptViewSet(viewsets.ModelViewSet):

    serializer_class = QuizAttemptSerializer

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
 
        user = self.request.user
        queryset = QuizAttempt.objects.select_related("quiz", "student")
 
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

    # ================= CREATE =================
    def perform_create(self, serializer):

        material = serializer.save(
            uploaded_by=self.request.user
        )

        students = Enrollment.objects.filter(
            teaching_assignment=
            material.teaching_assignment
        )

        # ================= STUDENT NOTIFICATIONS =================
        from .signals import notify_parents
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

# ===================== NOTIFICATION =====================
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(
            recipient=self.request.user
        )

        unread = self.request.query_params.get("unread")
        if unread == "true":
            queryset = queryset.filter(is_read=False)

        return queryset.order_by("-created_at")

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"message": "Notification marked as read"})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({"message": "All notifications marked as read"})
    

    # ================= GENERATE ENROLLMENTS =================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_enrollments(request):

    if request.user.role not in ("admin", "academic_admin"):
        return Response(
            {
                "error": "Only admin or academic admin can generate enrollments"
            },
            status=403
        )

    from courses.services import enroll_student

    created_count = 0

    for student in User.objects.filter(role='student'):
        created_count += enroll_student(student)

    return Response(
        {
            "message": "Enrollments generated successfully",
            "created": created_count
        },
        status=status.HTTP_200_OK
    )

# ===================== ELECTIVE SELF-ENROLLMENT =====================
# A student sees the electives offered for their own course + year + semester,
# and enrols / un-enrols themselves. Core subjects are auto-enrolled elsewhere;
# ONLY subjects with is_elective=True are self-serve, and a student can only
# ever touch electives in their OWN class.

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_electives(request):
    """
    GET /my-electives/
    The electives offered to THIS student (their course/year/semester), each
    flagged with whether they're already enrolled.
    """
    user = request.user
    if getattr(user, "role", None) != "student":
        return Response({"detail": "Only students have electives."}, status=403)

    if not user.course or not user.year or not user.semester:
        return Response([])

    # every elective teaching-assignment for this student's exact class
    assignments = (
        TeachingAssignment.objects
        .filter(
            course=user.course,
            year__year_number=user.year,
            subject__semester=user.semester,
            subject__is_elective=True,
        )
        .select_related("subject", "teacher")
        .order_by("subject__name")
    )

    # which of them this student is already in
    mine = set(
        Enrollment.objects
        .filter(student=user, teaching_assignment__in=assignments)
        .values_list("teaching_assignment_id", flat=True)
    )

    data = [
        {
            "teaching_assignment": a.id,
            "subject": a.subject.name,
            "code": a.subject.code or "",
            "credits": a.subject.credits,
            "teacher_name": (a.teacher.get_full_name() or "").strip() or a.teacher.username,
            "enrolled": a.id in mine,
        }
        for a in assignments
    ]
    return Response(data)


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def elective_enroll(request):
    """
    POST   /elective-enroll/   body { "teaching_assignment": <id> }  -> enrol
    DELETE /elective-enroll/   body { "teaching_assignment": <id> }  -> un-enrol

    Guardrails: the target must be an ELECTIVE in the student's OWN
    course/year/semester. A student can't self-enrol into a core subject,
    another class, or someone else's elective.
    """
    user = request.user
    if getattr(user, "role", None) != "student":
        return Response({"detail": "Only students can choose electives."}, status=403)

    ta_id = request.data.get("teaching_assignment")
    if not ta_id:
        return Response({"detail": "teaching_assignment is required."}, status=400)

    # the TA must be an elective in EXACTLY this student's class
    ta = (
        TeachingAssignment.objects
        .filter(
            id=ta_id,
            course=user.course,
            year__year_number=user.year,
            subject__semester=user.semester,
            subject__is_elective=True,
        )
        .first()
    )
    if not ta:
        return Response(
            {"detail": "That elective is not available for your class."},
            status=404,
        )

    if request.method == "POST":
        _, created = Enrollment.objects.get_or_create(
            student=user,
            teaching_assignment=ta,
        )
        return Response(
            {"detail": "Enrolled.", "teaching_assignment": ta.id, "enrolled": True},
            status=201 if created else 200,
        )

    # DELETE -> drop it
    Enrollment.objects.filter(student=user, teaching_assignment=ta).delete()
    return Response(
        {"detail": "Removed.", "teaching_assignment": ta.id, "enrolled": False}
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

        return queryset.order_by(
            "created_at"
        )

    def perform_create(
        self,
        serializer
    ):

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

        return queryset.order_by("-created_at")

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

            student = serializer.validated_data.get(
                "student"
            )

            serializer.save(
                teacher=user,
                student=student,
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

# ===================== FEE =====================
class FeeViewSet(viewsets.ModelViewSet):
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        if user.role in ('admin', 'accounts_admin'):
            return Fee.objects.all().select_related('student')
        if user.role == 'parent':
            from users.models import ParentProfile
            try:
                profile = ParentProfile.objects.get(user=user)
                ids = profile.children.values_list('id', flat=True)
                return Fee.objects.filter(student_id__in=ids)
            except ParentProfile.DoesNotExist:
                return Fee.objects.none()
        if user.role == 'student':
            return Fee.objects.filter(student=user)
        return Fee.objects.none()

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        fee = self.get_object()   # already scoped to the parent's children / student's own fees

        if request.user.role not in ('parent', 'student'):
            return Response({'detail': 'Only a parent or student can pay.'}, status=403)

        try:
            pay_amt = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'detail': 'Enter a valid amount.'}, status=400)

        if pay_amt <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        remaining = fee.amount - fee.paid_amount
        if pay_amt > remaining:
            return Response({'detail': f'You can pay at most ₹{remaining:.0f}.'}, status=400)

        fee.paid_amount += pay_amt
        if fee.paid_amount >= fee.amount:
            fee.status = 'paid'
            fee.paid_date = timezone.now().date()
        else:
            fee.status = 'partial'
        fee.save()
        return Response(FeeSerializer(fee).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_fees(request):
    if request.user.role not in ('admin', 'accounts_admin'):
        return Response({'detail': 'Only admin or accounts admin can generate fees.'}, status=403)

    course_id = request.data.get('course')
    year = request.data.get('year')
    fee_type = (request.data.get('fee_type') or '').strip()
    amount = request.data.get('amount')
    due_date = request.data.get('due_date') or None

    if not course_id or not year or not fee_type or not amount:
        return Response(
            {'detail': 'course, year, fee_type and amount are all required.'},
            status=400,
        )

    students = User.objects.filter(
        role='student',
        course_id=course_id,
        year=year,
    )

    created = 0
    skipped = 0
    for s in students:
        obj, was_created = Fee.objects.get_or_create(
            student=s,
            term=fee_type,
            defaults={
                'amount': amount,
                'due_date': due_date,
                'status': 'pending',
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return Response({
        'message': f'{created} fee(s) created, {skipped} already existed.',
        'created': created,
        'skipped': skipped,
    })

# ===================== PARENT DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_dashboard(request):
    user = request.user
    if user.role != 'parent':
        return Response({'detail': 'Not a parent.'}, status=403)
    from users.models import ParentProfile
    try:
        profile = ParentProfile.objects.prefetch_related(
            'children').get(user=user)
    except ParentProfile.DoesNotExist:
        return Response({'detail': 'No profile.'}, status=404)
    children = profile.children.all()
    fees = Fee.objects.filter(student__in=children)
    pending_fees = sum(
        (f.amount - f.paid_amount) for f in fees if f.paid_amount < f.amount)
    enrolled_ta_ids = Enrollment.objects.filter(
        student__in=children
    ).values_list('teaching_assignment_id', flat=True)
    submitted_ids = Submission.objects.filter(
        student__in=children
    ).values_list('assignment_id', flat=True)
    pending_assignments = Assignment.objects.filter(
        teaching_assignment_id__in=enrolled_ta_ids
    ).exclude(id__in=submitted_ids).count()
    att_data = {}
    for child in children:
        recs = Attendance.objects.filter(student=child)
        total = recs.count()
        present = recs.filter(status='present').count()
        att_data[child.username] = {
            'total': total, 'present': present,
            'percentage': round(present/total*100,1) if total else 0
        }
    avg = round(sum(v['percentage'] for v in att_data.values())
                / len(att_data), 1) if att_data else 0
    notifs = Notification.objects.filter(
        recipient=user).order_by('-created_at')[:10]
    return Response({
        'children_enrolled': children.count(),
        'pending_fees': float(pending_fees),
        'avg_attendance': avg,
        'pending_assignments': pending_assignments,
        'attendance_per_child': att_data,
        'children': [{'id': c.id, 'username': c.username} for c in children],
        'recent_notifications': [
            {'id':n.id,'title':n.title,'message':n.message,
             'is_read':n.is_read,'created_at':n.created_at}
            for n in notifs],
    })

def parent_display_name(parent_user, student_ids=None):
    """'Ravi (Aarthi.R)' - parent name plus the child they belong to.

    student_ids limits the children shown to those in the caller's own classes.

    SINGLE SOURCE OF TRUTH: message_contacts() and chat_contacts() both use this.
    """
    from users.models import ParentProfile
    profile = ParentProfile.objects.filter(user=parent_user).first()
    if not profile:
        return parent_user.username
    kids = profile.children.all()
    if student_ids is not None:
        kids = kids.filter(id__in=student_ids)
    names = list(kids.values_list('username', flat=True))
    if not names:
        return parent_user.username
    return f"{parent_user.username} ({', '.join(names)})"


# ===================== PARENT MESSAGES =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_contacts(request):
    """Who the current user can message."""
    from .models import ParentMessage
    user = request.user

    if user.role == 'parent':
        children = get_parent_children(user)
        ta_ids = Enrollment.objects.filter(
            student__in=children
        ).values_list('teaching_assignment_id', flat=True)
        teachers = User.objects.filter(
            id__in=TeachingAssignment.objects.filter(
                id__in=ta_ids
            ).values_list('teacher_id', flat=True)
        )
        data = []
        for t in teachers:
            subjects = TeachingAssignment.objects.filter(
                id__in=ta_ids, teacher=t
            ).values_list('subject__name', flat=True)
            data.append({
                'id': t.id, 'username': t.username,
                'subject': ', '.join(set(subjects)),
            })
        return Response(data)

    if user.role == 'teacher':
        ta_ids = TeachingAssignment.objects.filter(
            teacher=user
        ).values_list('id', flat=True)
        student_ids = Enrollment.objects.filter(
            teaching_assignment_id__in=ta_ids
        ).values_list('student_id', flat=True)
        from users.models import ParentProfile
        parents = User.objects.filter(
            id__in=ParentProfile.objects.filter(
                children__id__in=student_ids
            ).values_list('user_id', flat=True)
        ).distinct()
        return Response([{'id': p.id, 'username': parent_display_name(p, student_ids), 'subject': 'Parent'} for p in parents])

    return Response([])


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def messages_with(request, user_id):
    """GET = all messages between me and user_id. POST = send one."""
    from .models import ParentMessage
    from .serializers import ParentMessageSerializer
    me = request.user

    if request.method == 'GET':
        msgs = ParentMessage.objects.filter(
            sender_id__in=[me.id, user_id],
            receiver_id__in=[me.id, user_id],
        ).order_by('created_at')
        ParentMessage.objects.filter(sender_id=user_id, receiver=me, is_read=False).update(is_read=True)
        return Response(ParentMessageSerializer(msgs, many=True).data)

    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'detail': 'Message cannot be empty.'}, status=400)
    msg = ParentMessage.objects.create(sender=me, receiver_id=user_id, text=text)
    Notification.objects.create(
        recipient_id=user_id,
        title="New message",
        message=f"{me.username}: {text[:50]}",
        notification_type='announcement',
    )
    return Response(ParentMessageSerializer(msg).data, status=201)


# ===================== TEACHER BROADCAST TO PARENTS =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def broadcast_to_parents(request):
    if request.user.role != 'teacher':
        return Response({'detail': 'Only teachers can broadcast.'}, status=403)

    from .models import ParentMessage
    from users.models import ParentProfile

    ta_id = request.data.get('teaching_assignment')
    text = (request.data.get('text') or '').strip()
    if not ta_id or not text:
        return Response({'detail': 'Subject and message are required.'}, status=400)

    student_ids = Enrollment.objects.filter(
        teaching_assignment_id=ta_id
    ).values_list('student_id', flat=True)

    parent_user_ids = ParentProfile.objects.filter(
        children__id__in=student_ids
    ).values_list('user_id', flat=True).distinct()

    count = 0
    for pid in parent_user_ids:
        ParentMessage.objects.create(sender=request.user, receiver_id=pid, text=text)
        Notification.objects.create(
            recipient_id=pid,
            title="Message from teacher",
            message=f"{request.user.username}: {text[:60]}",
            notification_type='announcement',
        )
        count += 1

    return Response({'message': f'Sent to {count} parent(s).'})

# ===================== CHAT: CONTACTS =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chat_contacts(request):
    from .models import ConversationMessage
    from users.models import ParentProfile
    user = request.user

    if user.role == 'parent':
        children = get_parent_children(user)
        ta_ids = Enrollment.objects.filter(
            student__in=children
        ).values_list('teaching_assignment_id', flat=True)
        teacher_ids = TeachingAssignment.objects.filter(
            id__in=ta_ids
        ).values_list('teacher_id', flat=True)
        teachers = User.objects.filter(id__in=teacher_ids).distinct()
        data = []
        for t in teachers:
            subjects = TeachingAssignment.objects.filter(
                id__in=ta_ids, teacher=t
            ).values_list('subject__name', flat=True)
            data.append({'id': t.id, 'username': t.username,
                         'subject': ', '.join(set(subjects))})
        return Response(data)

    if user.role == 'teacher':
        ta_ids = TeachingAssignment.objects.filter(
            teacher=user
        ).values_list('id', flat=True)
        student_ids = Enrollment.objects.filter(
            teaching_assignment_id__in=ta_ids
        ).values_list('student_id', flat=True)
        parent_ids = ParentProfile.objects.filter(
            children__id__in=student_ids
        ).values_list('user_id', flat=True).distinct()
        parents = User.objects.filter(id__in=parent_ids)
        return Response([{'id': p.id, 'username': parent_display_name(p, student_ids), 'subject': 'Parent'}
                         for p in parents])

    return Response([])


# ===================== CHAT: MESSAGES =====================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def chat_with(request, user_id):
    from .models import ConversationMessage
    from .serializers import ConversationMessageSerializer
    me = request.user

    if request.method == 'GET':
        msgs = ConversationMessage.objects.filter(
            sender_id__in=[me.id, user_id],
            receiver_id__in=[me.id, user_id],
        ).order_by('created_at')
        ConversationMessage.objects.filter(
            sender_id=user_id, receiver=me, is_read=False
        ).update(is_read=True)
        return Response(ConversationMessageSerializer(msgs, many=True).data)

    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'detail': 'Message cannot be empty.'}, status=400)
    msg = ConversationMessage.objects.create(
        sender=me, receiver_id=user_id, text=text)
    Notification.objects.create(
        recipient_id=user_id,
        title="New message",
        message=f"{me.username}: {text[:50]}",
        notification_type='announcement',
    )
    return Response(ConversationMessageSerializer(msg).data, status=201)


# ===================== MANAGE PARENTS (ADMIN) =====================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def manage_parents(request):
    if request.user.role != 'admin':
        return Response({'detail': 'Only admin can manage parents.'}, status=403)

    from users.models import ParentProfile

    if request.method == 'GET':
        parents = []
        for p in ParentProfile.objects.select_related('user').prefetch_related('children'):
            parents.append({
                'profile_id': p.id,
                'username': p.user.username,
                'children': [{'id': c.id, 'username': c.username} for c in p.children.all()],
            })
        students = list(
            User.objects.filter(role='student')
            .order_by('course__name', 'username')
            .values('id', 'username', course_name=models.F('course__name'))
        )
        return Response({'parents': parents, 'students': students})

    username = (request.data.get('username') or '').strip()
    password = request.data.get('password') or ''
    child_ids = request.data.get('children', [])

    if not username or not password:
        return Response({'detail': 'Username and password are required.'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'detail': 'That username already exists.'}, status=400)

    parent = User(username=username, role='parent')
    parent.set_password(password)
    parent.save()

    profile = ParentProfile.objects.create(user=parent)
    if child_ids:
        profile.children.set(User.objects.filter(id__in=child_ids, role='student'))

    return Response({'message': 'Parent created successfully.', 'profile_id': profile.id}, status=201)


# ===================== UPDATE A PARENT (ADMIN) =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_parent_children(request, profile_id):
    if request.user.role != 'admin':
        return Response({'detail': 'Only admin can manage parents.'}, status=403)

    from users.models import ParentProfile
    try:
        profile = ParentProfile.objects.select_related('user').get(id=profile_id)
    except ParentProfile.DoesNotExist:
        return Response({'detail': 'Parent profile not found.'}, status=404)

    parent = profile.user

    # ----- update username (if provided and changed) -----
    username = (request.data.get('username') or '').strip()
    if username and username != parent.username:
        if User.objects.filter(username=username).exclude(id=parent.id).exists():
            return Response({'detail': 'That username already exists.'}, status=400)
        parent.username = username

    # ----- update password (only if a new one is sent) -----
    password = request.data.get('password') or ''
    if password:
        parent.set_password(password)

    parent.save()

    # ----- update children (if the list is sent) -----
    if 'children' in request.data:
        child_ids = request.data.get('children', [])
        profile.children.set(User.objects.filter(id__in=child_ids, role='student'))

    return Response({'message': 'Parent updated.'})

