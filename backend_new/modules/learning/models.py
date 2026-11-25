
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.academics.models import (
    TeachingAssignment,
)
    
# ===================== FILE CLEANUP SIGNAL =====================
from django.db.models.signals import post_delete
from django.dispatch import receiver

User = get_user_model()


# ===================== LECTURE =====================
class Lecture(models.Model):

    # ================= BASIC =================
    title = models.CharField(
        max_length=200
    )
    
    description = models.TextField(
        blank=True,
        null=True
    )

    chapter = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    # ================= SUBJECT =================
    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="lectures"
    )

    # ================= VIDEO =================
    video = models.FileField(
        upload_to='lectures/',
        blank=True,
        null=True
    )

    # ================= LIVE CLASS =================
    is_live = models.BooleanField(
        default=False
    )

    meeting_link = models.URLField(
        blank=True,
        null=True
    )

    scheduled_time = models.DateTimeField(
        blank=True,
        null=True
    )

    # ================= CREATED =================
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def __str__(self):

        lecture_type = (
            "Live"
            if self.is_live
            else "Recorded"
        )

        return (
            f"{self.title} "
            f"({lecture_type})"
        )

    class Meta:
        db_table = 'courses_lecture'  # table kept from the old 'courses' app


# ===================== ASSIGNMENT =====================
class Assignment(models.Model):

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="assignments"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    file = models.FileField(
        upload_to='assignments/',
        blank=True,
        null=True
    )

    due_date = models.DateTimeField(
        blank=True,
        null=True
    )

    total_marks = models.IntegerField(
        default=100
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'courses_assignment'  # table kept from the old 'courses' app


# ===================== SUBMISSION =====================

class Submission(models.Model):

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions"
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    file = models.FileField(
        upload_to='submissions/'
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True
    )

    # ================= MARKS =================
    marks = models.FloatField(
        blank=True,
        null=True
    )

    # ================= FEEDBACK =================
    feedback = models.TextField(
        blank=True,
        null=True
    )

    # ================= GRADED TIME =================
    graded_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # ================= STATUS =================
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('evaluated', 'Evaluated'),
        ('late', 'Late'),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    class Meta:
        db_table = 'courses_submission'  # table kept from the old 'courses' app
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'assignment',
                    'student'
                ],
                name='unique_submission'
            )
        ]

    # ================= LATE SUBMISSION CHECK =================
    def save(self, *args, **kwargs):

        if (
            self.assignment.due_date
            and not self.pk
        ):

            if timezone.now() > self.assignment.due_date:

                self.status = 'late'

        super().save(*args, **kwargs)

    def __str__(self):

        return (
            f"{self.student} → "
            f"{self.assignment}"
        )


# ===================== QUIZ =====================
class Quiz(models.Model):

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="quizzes"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    duration = models.IntegerField(
        default=10
    )

    # NEW FIELD
    due_date = models.DateTimeField(
        blank=True,
        null=True
    )

    total_marks = models.IntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    # ===== WAVE 3 PART 3: online tests (the quiz, upgraded) =====
    # due_date above is when the test CLOSES (no new starts after it);
    # duration is the minutes each student gets once they start.
    opens_at = models.DateTimeField(null=True, blank=True)        # empty = open once published
    is_published = models.BooleanField(default=True)              # new tests start as drafts
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    negative_marking = models.BooleanField(default=False)
    show_answers = models.BooleanField(default=False)             # students review answers after results
    results_released = models.BooleanField(default=True)          # Part 3b: teacher releases written marks

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'courses_quiz'  # table kept from the old 'courses' app


    
# ===================== QUESTION =====================
class Question(models.Model):

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    text = models.TextField()

    option1 = models.CharField(
        max_length=200
    )

    option2 = models.CharField(
        max_length=200
    )

    option3 = models.CharField(
        max_length=200
    )

    option4 = models.CharField(
        max_length=200
    )

    correct_answer = models.IntegerField()

    marks = models.IntegerField(
        default=1
    )

    def __str__(self):
        return self.text

    class Meta:
        db_table = 'courses_question'  # table kept from the old 'courses' app


# ===================== QUIZ ATTEMPT =====================
class QuizAttempt(models.Model):

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    # WAVE 3 PART 3: a float, so half marks and negative marks add up
    score = models.FloatField(
        default=0
    )

    submitted_at = models.DateTimeField(
        default=timezone.now,
        null=True,
        blank=True,
    )

    # ===== WAVE 3 PART 3: one sitting of an online test =====
    STATUS_CHOICES = [("in_progress", "Writing"), ("submitted", "Submitted")]
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="submitted")
    started_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)          # started_at + duration
    # this student's paper: [{"q": bank id, "s": section, "m": marks, "o": [option order]}]
    paper = models.JSONField(default=list, blank=True)
    answers = models.JSONField(default=dict, blank=True)           # {bank id: answer}
    flagged = models.JSONField(default=list, blank=True)           # marked for review
    awarded = models.JSONField(default=dict, blank=True)           # {bank id: marks, or null = not marked yet}
    tab_leaves = models.PositiveIntegerField(default=0)
    written_pending = models.BooleanField(default=False)           # written answers still to mark
    feedback = models.JSONField(default=dict, blank=True)          # WAVE 3 PART 3b: {bank id: teacher's comment}

    class Meta:
        db_table = 'courses_quizattempt'  # table kept from the old 'courses' app
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'quiz',
                    'student'
                ],
                name='unique_quiz_attempt'
            )
        ]

    def __str__(self):
        return (
            f"{self.student} → "
            f"{self.quiz}"
        )


    

# ===================== STUDY MATERIAL =====================
class StudyMaterial(models.Model):

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    file = models.FileField(
        upload_to='study_materials/'
    )

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="study_materials"
    )

    folder = models.ForeignKey(
        "MaterialFolder",
        on_delete=models.CASCADE,
        related_name="materials",
        null=True,
        blank=True
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def __str__(self):

        return self.title

    class Meta:
        db_table = 'courses_studymaterial'  # table kept from the old 'courses' app


    
# ================= DISCUSSION MESSAGE =================
class DiscussionMessage(models.Model):

    teaching_assignment = models.ForeignKey(
    TeachingAssignment,
    on_delete=models.CASCADE,
    related_name="discussions",
    null=True,
    blank=True
)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    message = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )
       

    class Meta:
        db_table = 'courses_discussionmessage'  # table kept from the old 'courses' app
        ordering = ["created_at"]

    def __str__(self):

        return (
            f"{self.user.username}"
            f" - "
            f"{self.teaching_assignment.subject.name}"
        )


# ===================== FEEDBACK =====================
class Feedback(models.Model):

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="feedbacks"
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="feedback_given",
        null=True,
        blank=True
    )

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="feedback_received",
        null=True,
        blank=True
    )

    direction = models.CharField(
        max_length=3,
        choices=[
            ("t2s", "Teacher to Student"),
            ("s2t", "Student to Teacher"),
        ]
    )

    message = models.TextField()

    rating = models.IntegerField(
        null=True,
        blank=True
    )

    is_anonymous = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.direction} - "
            f"{self.teaching_assignment.subject.name}"
        )

    class Meta:
        db_table = 'courses_feedback'  # table kept from the old 'courses' app


# ===================== MATERIAL FOLDER =====================
class MaterialFolder(models.Model):
    """
    A teacher-created folder inside a subject's Study Materials,
    e.g. "Question Bank", "Unit 1 Notes".
    """

    name = models.CharField(max_length=120)

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="material_folders"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="material_folders"
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'courses_materialfolder'  # table kept from the old 'courses' app
        ordering = ["name"]
        unique_together = ("name", "teaching_assignment")

    def __str__(self):
        return f"{self.name} ({self.teaching_assignment})"


@receiver(post_delete, sender=StudyMaterial)
def delete_studymaterial_file(sender, instance, **kwargs):
    # remove the physical file from disk when a StudyMaterial row is deleted
    if instance.file:
        instance.file.delete(save=False)


# ===================== WAVE 3 PART 3: QUESTION BANK + TEST SECTIONS =====================
class BankQuestion(models.Model):
    """One question in a subject's bank, shared by every teacher of the subject.
    answer: mcq -> [index]; multi -> [index, ...]; tf -> true/false;
            short / long -> null (marked by hand against model_answer)."""
    KIND_CHOICES = [
        ("mcq", "MCQ - one answer"),
        ("multi", "MCQ - more than one answer"),
        ("tf", "True / false"),
        ("short", "Short answer"),
        ("long", "Long answer"),
    ]
    DIFFICULTY_CHOICES = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]

    subject = models.ForeignKey("courses.Subject", on_delete=models.CASCADE, related_name="bank_questions")
    kind = models.CharField(max_length=6, choices=KIND_CHOICES, default="mcq")
    text = models.TextField()
    options = models.JSONField(default=list, blank=True)
    answer = models.JSONField(null=True, blank=True)
    model_answer = models.TextField(blank=True, default="")
    marks = models.PositiveSmallIntegerField(default=1)
    negative_marks = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    unit = models.PositiveSmallIntegerField(null=True, blank=True)
    outcome = models.ForeignKey("teachingplan.CourseOutcome", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="bank_questions")
    bloom = models.CharField(max_length=12, blank=True, default="")
    difficulty = models.CharField(max_length=6, choices=DIFFICULTY_CHOICES, default="medium")
    explanation = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)          # archived instead of deleted once used
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["unit", "id"]

    @property
    def is_written(self):
        return self.kind in ("short", "long")

    def __str__(self):
        return self.text[:60]


class QuizSection(models.Model):
    """A part of a test's paper: questions picked at random from the bank by
    rules, or questions the teacher chose."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="sections")
    order = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=100, blank=True, default="")
    pick = models.CharField(max_length=6, choices=[("random", "At random"), ("fixed", "Chosen")], default="fixed")
    count = models.PositiveSmallIntegerField(default=0)               # random: how many
    units = models.JSONField(default=list, blank=True)                 # random: [] = every unit
    kinds = models.JSONField(default=list, blank=True)                 # random: [] = every type
    easy = models.PositiveSmallIntegerField(default=0)                 # random: difficulty mix (all 0 = any)
    medium = models.PositiveSmallIntegerField(default=0)
    hard = models.PositiveSmallIntegerField(default=0)
    question_ids = models.JSONField(default=list, blank=True)          # fixed: bank ids, in order
    marks_each = models.PositiveSmallIntegerField(default=0)           # 0 = each question's own marks

    class Meta:
        ordering = ["order", "id"]
