
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
    
# ===================== FILE CLEANUP SIGNAL =====================

User = get_user_model()


# ===================== COURSE =====================
class Course(models.Model):
    name = models.CharField(max_length=100,unique=True)

    def __str__(self):
        return self.name


# ===================== YEAR =====================
class Year(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="years"
    )

    year_number = models.IntegerField()

    class Meta:
        ordering = ['year_number']

        constraints = [
            models.UniqueConstraint(
                fields=['course', 'year_number'],
                name='unique_course_year'
            )
        ]

    def __str__(self):
        return f"{self.course.name} - Year {self.year_number}"


# ===================== SUBJECT =====================
class Subject(models.Model):

    SEMESTER_CHOICES = (
        (1, "Semester 1"),
        (2, "Semester 2"),
        (3, "Semester 3"),
        (4, "Semester 4"),
        (5, "Semester 5"),
        (6, "Semester 6"),
        (7, "Semester 7"),
        (8, "Semester 8"),
    )

    # ================= SUBJECT NAME =================
    name = models.CharField(
        max_length=100
    )

   # ================= SUBJECT CODE =================
    code = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    # ================= YEAR =================
    year = models.ForeignKey(
        Year,
        on_delete=models.CASCADE,
        related_name="subjects"
    )

    # ================= SEMESTER =================
    semester = models.IntegerField(
        choices=SEMESTER_CHOICES,
        default=1
    )

    # ================= CREDITS =================
    # credits for this subject (e.g. 3, 4, or 1.5 - WAVE 3: half credits allowed).
    # defaults to 0 so existing rows stay valid until set.
    credits = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0
    )

    # ================= CBCS (WAVE 3 PART 1A) =================
    # Which regulation this subject belongs to (empty = the default regulation),
    # its course category (PCC, BSC ...), its type (sets the pass rule) and
    # its weekly L-T-P hours.
    regulation = models.ForeignKey(
        'courses.Regulation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects'
    )
    category = models.ForeignKey(
        'courses.CourseCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects'
    )
    kind = models.CharField(
        max_length=10,
        choices=[("theory", "Theory"), ("practical", "Practical"), ("project", "Project")],
        default="theory"
    )
    lecture_hours = models.PositiveSmallIntegerField(default=0)
    tutorial_hours = models.PositiveSmallIntegerField(default=0)
    practical_hours = models.PositiveSmallIntegerField(default=0)

    weekly_hours = models.IntegerField(
        default=0
    )

    is_elective = models.BooleanField(
        default=False
    )
    # ================= DEPARTMENT (owner) =================
    department = models.ForeignKey(
        'users.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects'
    )

    class Meta:

        # Alphabetical ordering
        ordering = ['name']

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'name',
                    'year',
                    'semester'
                ],
                name='unique_subject_per_semester'
            )
        ]

    def __str__(self):

        return (
            f"{self.name} "
            f"(Year {self.year.year_number} "
            f"- Semester {self.semester})"
        )


    

# ===================== TEACHING ASSIGNMENT =====================
class TeachingAssignment(models.Model):

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'}
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE
    )

    year = models.ForeignKey(
        Year,
        on_delete=models.CASCADE
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'teacher',
                    'course',
                    'year',
                    'subject'
                ],
                name='unique_teaching_assignment'
            )
        ]

    # ================= VALIDATION =================
    def clean(self):

        if self.year.course != self.course:
            raise ValueError(
                "Selected year does not belong to this course"
            )

        if self.subject.year != self.year:
            raise ValueError(
                "Selected subject does not belong to this year"
            )

    def __str__(self):
        return (
            f"{self.teacher} → "
            f"{self.subject.name}"
        )


# ===================== ENROLLMENT =====================
class Enrollment(models.Model):

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'}
    )

    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        related_name="enrollments"
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'student',
                    'teaching_assignment'
                ],
                name='unique_student_subject_enrollment'
            )
        ]

    def __str__(self):
        return (
            f"{self.student} → "
            f"{self.teaching_assignment.subject.name}"
        )


    
# ===================== YEAR TUTOR =====================
class YearTutor(models.Model):
    """One tutor per year of a course. No sections."""
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='tutor_years'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='year_tutors'
    )
    year = models.ForeignKey(
        Year,
        on_delete=models.CASCADE,
        related_name='year_tutors'
    )
    assigned_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['year'],
                name='unique_tutor_per_year'
            )
        ]

    def __str__(self):
        return f"{self.teacher} → {self.course.name} Year {self.year.year_number}"


# ===================== LEGACY PLACEHOLDER (do not use) =====================
class Fee(models.Model):
    """
    Empty placeholder. The real Fee model is modules/fees/models.py (fees.Fee).

    Old exams migrations (written before the module split) point at
    'courses.Fee'. Keeping this unmanaged, field-less placeholder in the
    migration history lets a college add the Exams module LATER without
    migrate failing. managed=False means Django never creates, changes or
    deletes any table for it. Never import or query this class.
    """

    class Meta:
        managed = False


# ELECTIVES (meeting point 9) - kept in their own file, registered here so
# Django finds them as part of this app.
from .models_electives import (  # noqa: E402,F401
    ElectiveChange, ElectiveGroup, ElectiveOption, ElectiveSetting,
)

# CBCS (WAVE 3 PART 1A) - regulations, categories, credit requirements.
from .models_regulations import (  # noqa: E402,F401
    CourseCategory, CreditRequirement, DegreeClass, GradeBand, PassRule, Regulation, RegulationBatch,
)
