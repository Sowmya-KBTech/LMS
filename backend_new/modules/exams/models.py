from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


# ===================== INTERNAL ASSESSMENT =====================
class InternalAssessment(models.Model):
    """
    One IA slot (IA1 / IA2 / IA3) for a given teaching assignment.
    The teacher enters marks; the admin reviews and locks to declare.
    """

    IA_CHOICES = [
        (1, "IA 1"),
        (2, "IA 2"),
        (3, "IA 3"),
    ]

    teaching_assignment = models.ForeignKey(
        "courses.TeachingAssignment",
        on_delete=models.CASCADE,
        related_name="internal_assessments"
    )

    number = models.IntegerField(
        choices=IA_CHOICES
    )

    max_marks = models.IntegerField(
        default=50
    )

    # Admin locks after review -> declared & visible to students
    is_locked = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["teaching_assignment", "number"],
                name="unique_ia_per_assignment"
            )
        ]

    def __str__(self):
        return (
            f"IA {self.number} - "
            f"{self.teaching_assignment.subject.name}"
        )


# ===================== IA MARK =====================
class IAMark(models.Model):
    """
    A single student's mark for one IA slot.
    """

    assessment = models.ForeignKey(
        InternalAssessment,
        on_delete=models.CASCADE,
        related_name="marks"
    )

    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="ia_marks",
        limit_choices_to={"role": "student"}
    )

    marks_obtained = models.FloatField(
        null=True,
        blank=True
    )

    is_absent = models.BooleanField(
        default=False
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"],
                name="unique_ia_mark_per_student"
            )
        ]

    def __str__(self):
        return (
            f"{self.student} - "
            f"IA {self.assessment.number} - "
            f"{self.marks_obtained}"
        )
    
# ===================== SEMESTER RESULT =====================
class SemesterResult(models.Model):
    """
    A student's result for one semester. Groups all subject entries.
    Admin enters marks, then publishes to release to the student.
    """

    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="semester_results",
        limit_choices_to={"role": "student"},
    )

    semester = models.IntegerField()

    is_published = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    class Meta:
        ordering = ["-semester"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "semester"],
                name="unique_semester_result_per_student",
            )
        ]

    def __str__(self):
        return f"{self.student} - Semester {self.semester}"


# ===================== RESULT ENTRY =====================
class ResultEntry(models.Model):
    """
    One subject's mark inside a semester result.
    Grade + pass/fail are computed on save from scored/max.
    """

    result = models.ForeignKey(
        SemesterResult,
        on_delete=models.CASCADE,
        related_name="entries",
    )

    subject = models.ForeignKey(
        "courses.Subject",
        on_delete=models.CASCADE,
    )

    max_marks = models.IntegerField(
        default=100
    )

    marks_obtained = models.FloatField(
        null=True,
        blank=True
    )

    grade = models.CharField(
        max_length=4,           # WAVE 3: regulation grades such as "RA", "A+"
        blank=True
    )

    is_pass = models.BooleanField(
        default=False
    )

    # ===== WAVE 3 PART 1B (CBCS): marks split, grade points, attempts =====
    # marks_obtained / max_marks stay the TOTAL (rank lists and reports use them).
    internal_marks = models.FloatField(null=True, blank=True)
    end_marks = models.FloatField(null=True, blank=True)
    # the grade points and outcome the regulation gave when this was graded -
    # published results keep them even if the regulation changes later
    grade_points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    outcome = models.CharField(max_length=10, blank=True, default="")   # pass / fail / arrear / excluded
    attempt = models.PositiveSmallIntegerField(default=1)
    exam_session = models.CharField(max_length=30, blank=True, default="")   # "Nov/Dec 2025"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["result", "subject"],
                name="unique_result_entry_per_subject",
            )
        ]

    def __str__(self):
        return f"{self.result.student} - {self.subject.name} - {self.grade}"


# ===================== RESULT ATTEMPT (WAVE 3 PART 1B) =====================
class ResultAttempt(models.Model):
    """An EARLIER attempt at a subject, kept when an arrear is written again.
    The latest attempt always lives on the ResultEntry itself."""

    entry = models.ForeignKey(ResultEntry, on_delete=models.CASCADE, related_name="attempts")
    attempt = models.PositiveSmallIntegerField()
    exam_session = models.CharField(max_length=30, blank=True, default="")
    internal_marks = models.FloatField(null=True, blank=True)
    end_marks = models.FloatField(null=True, blank=True)
    marks_obtained = models.FloatField(null=True, blank=True)
    max_marks = models.IntegerField(default=100)
    grade = models.CharField(max_length=4, blank=True)
    grade_points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    is_pass = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attempt"]
        constraints = [models.UniqueConstraint(fields=["entry", "attempt"], name="unique_attempt_per_entry")]
    
# ===================== EXAM SCHEDULE =====================
class ExamSchedule(models.Model):
    """
    One exam slot: a subject's exam date + session (FN/AN) for a semester.
    Admin enters these; the hall ticket reads them.
    """

    SESSION_CHOICES = [
        ("FN", "Forenoon"),
        ("AN", "Afternoon"),
    ]

    subject = models.ForeignKey(
        "courses.Subject",
        on_delete=models.CASCADE,
        related_name="exam_schedules",
    )

    semester = models.IntegerField()

    exam_date = models.DateField()

    session = models.CharField(
        max_length=2,
        choices=SESSION_CHOICES,
        default="FN",
    )

    # WAVE 3 PART 2: which exam session (Nov/Dec 2026 ...) this slot belongs to.
    # Empty only on a college that has never set up an exam session.
    exam_session = models.ForeignKey(
        "ExamSession",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    class Meta:
        ordering = ["exam_date", "session"]
        constraints = [
            # one slot per subject in each exam session
            models.UniqueConstraint(
                fields=["exam_session", "subject"],
                condition=models.Q(exam_session__isnull=False),
                name="unique_exam_per_session_subject",
            ),
            # before any session exists: one slot per subject per semester (old rule)
            models.UniqueConstraint(
                fields=["subject", "semester"],
                condition=models.Q(exam_session__isnull=True),
                name="unique_exam_per_subject_semester",
            ),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.exam_date} ({self.session})"

# ===================== REVALUATION REQUEST =====================
class RevaluationRequest(models.Model):
    """
    A student's request to re-evaluate one published subject mark.
    Flow: pending_payment -> pending_review -> revised | retained
    """

    STATUS_CHOICES = [
        ("pending_payment", "Pending Payment"),
        ("pending_review", "Pending Review"),
        ("revised", "Revised"),
        ("retained", "Retained"),
    ]

    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="revaluation_requests",
        limit_choices_to={"role": "student"},
    )

    # the published subject mark being challenged
    result_entry = models.ForeignKey(
        "ResultEntry",
        on_delete=models.CASCADE,
        related_name="revaluation_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending_payment",
    )

    # snapshot of the mark at apply time + the revised mark after review
    original_marks = models.FloatField(
        null=True,
        blank=True,
    )

    revised_marks = models.FloatField(
        null=True,
        blank=True,
    )

    # the fee the student pays for this request
    fee = models.ForeignKey(
        "fees.Fee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revaluation_requests",
    )

    created_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "result_entry"],
                name="unique_revaluation_per_entry",
            )
        ]

    def __str__(self):
        return f"{self.student.username} - {self.result_entry} ({self.status})"
    
# ===================== REVALUATION WINDOW =====================
class RevaluationWindow(models.Model):
    """
    Controls when the revaluation portal is open for a semester,
    and the fee that applies while it's open. Admin opens/closes it.
    """

    semester = models.IntegerField(unique=True)

    is_open = models.BooleanField(default=False)

    fee_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        state = "Open" if self.is_open else "Closed"
        return f"Semester {self.semester} Revaluation - {state}"


# ===================== EXAM ELIGIBILITY RULES (#41) =====================
class EligibilitySetting(models.Model):
    """
    ELIGIBILITY RULES: the college's own hall-ticket attendance rules.

    One row for the whole college (this LMS is one college per installation).
    Before this, 75% and "a paid fine always unlocks" were fixed in the code.
    Now the admin changes them on Admin > Results > Hall Ticket.

    When the LMS becomes multi-college (SaaS), this table gets a college link
    and each college reads its own row. The eligibility check only ever calls
    EligibilitySetting.current(), so that is the one place to change.
    """

    min_attendance = models.PositiveSmallIntegerField(
        default=75,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum attendance % needed for a hall ticket.",
    )

    fine_unlocks = models.BooleanField(
        default=True,
        help_text="If on, paying the attendance shortage fine makes a student eligible.",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Eligibility setting"

    @classmethod
    def current(cls):
        """The college's rules. Created with the defaults (75%, fine on) the first time."""
        obj = cls.objects.order_by("id").first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    def __str__(self):
        return f"Min attendance {self.min_attendance}% · fine {'on' if self.fine_unlocks else 'off'}"


# ===================== ELIGIBILITY OVERRIDE (#41 Part B) =====================
class EligibilityOverride(models.Model):
    """
    ELIGIBILITY OVERRIDE: authorized staff unblock ONE student's hall ticket
    for ONE semester, despite an attendance shortage, with a written reason.

    This table IS the audit log. A row is never edited or deleted:
      - created_by / created_at / reason      = the override event
      - revoked_by / revoked_at / revoke_reason = the revoke event (filled once)
    A revoked override stays in the table forever. A new override for the
    same student is a new row.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eligibility_overrides",
    )
    semester = models.PositiveSmallIntegerField()
    reason = models.TextField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Eligibility override"

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        state = "active" if self.is_active else "revoked"
        return f"Override {self.student} · Sem {self.semester} · {state}"


# ===================== EXAM SESSION (WAVE 3 PART 2) =====================
class ExamSession(models.Model):
    """One exam season - "Nov/Dec 2026". Registration, the timetable, hall
    tickets (and in Part 2b seating and invigilation) all belong to one.
    Exactly one session is the CURRENT one: students register for it and the
    hall ticket reads its timetable."""

    KIND_CHOICES = [
        ("regular", "Regular + arrear"),
        ("supplementary", "Supplementary (arrears only)"),
    ]

    name = models.CharField(max_length=30, unique=True)
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default="regular")
    exam_start = models.DateField(null=True, blank=True)
    exam_end = models.DateField(null=True, blank=True)

    # registration window; late registration (with the late fee) runs until late_until
    registration_required = models.BooleanField(default=True)
    reg_opens = models.DateField(null=True, blank=True)
    reg_closes = models.DateField(null=True, blank=True)
    late_until = models.DateField(null=True, blank=True)
    registration_closed = models.BooleanField(default=False)   # closed by hand early

    # semesters whose students write regular papers ([] = every semester)
    semesters = models.JSONField(default=list, blank=True)
    students_pick_arrears = models.BooleanField(default=True)
    fee_required = models.BooleanField(default=True)
    regular_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)   # per paper
    arrear_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)    # per paper
    late_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)      # once

    is_current = models.BooleanField(default=False)
    timetable_published = models.BooleanField(default=False)
    hall_tickets_released = models.BooleanField(default=False)

    # WAVE 3 PART 2b: how seats and invigilation duties are given
    SEATING_CHOICES = [
        ("alternate", "Alternate papers on each bench"),
        ("spaced", "One student per bench"),
    ]
    seating_mode = models.CharField(max_length=10, choices=SEATING_CHOICES, default="alternate")
    two_invigilators_above = models.PositiveSmallIntegerField(default=40)   # 0 = always two
    relief_per_sitting = models.PositiveSmallIntegerField(default=1)        # relief / flying squad
    skip_own_subject = models.BooleanField(default=True)
    one_duty_per_day = models.BooleanField(default=True)
    include_hods = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.name


class ExamRegistration(models.Model):
    """A student's registration for one exam session: the papers they write
    (this semester's subjects + the arrears they picked) and the fee."""

    STATUS_CHOICES = [("draft", "Saved"), ("submitted", "Submitted")]

    exam_session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_registrations")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    is_late = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    fee = models.ForeignKey("fees.Fee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam_session", "student"], name="unique_registration_per_session")]

    def __str__(self):
        return f"{self.student} - {self.exam_session}"


class ExamRegistrationPaper(models.Model):
    KIND_CHOICES = [("regular", "Regular"), ("arrear", "Arrear")]

    registration = models.ForeignKey(ExamRegistration, on_delete=models.CASCADE, related_name="papers")
    subject = models.ForeignKey("courses.Subject", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=7, choices=KIND_CHOICES, default="regular")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["registration", "subject"], name="unique_paper_per_registration")]


# ===================== HALLS, SEATING, INVIGILATION (WAVE 3 PART 2b) =====================
SITTING_CHOICES = [("FN", "Forenoon"), ("AN", "Afternoon")]


class ExamHall(models.Model):
    """A room used for exams. Exam seats are usually fewer than class seats."""
    name = models.CharField(max_length=40, unique=True)
    seats = models.PositiveSmallIntegerField(default=30)
    per_bench = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class SeatAllotment(models.Model):
    """One student's seat for one sitting (a date + FN/AN) of a session."""
    exam_session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="allotments")
    exam_date = models.DateField()
    sitting = models.CharField(max_length=2, choices=SITTING_CHOICES)
    hall = models.ForeignKey(ExamHall, on_delete=models.CASCADE, related_name="allotments")
    seat_no = models.PositiveSmallIntegerField()
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_seats")
    subject = models.ForeignKey("courses.Subject", on_delete=models.CASCADE, related_name="+")

    class Meta:
        ordering = ["exam_date", "sitting", "hall__order", "hall__name", "seat_no"]
        constraints = [
            models.UniqueConstraint(fields=["exam_session", "exam_date", "sitting", "student"], name="one_seat_per_student_sitting"),
            models.UniqueConstraint(fields=["exam_session", "exam_date", "sitting", "hall", "seat_no"], name="one_student_per_seat"),
        ]


class InvigilationDuty(models.Model):
    """A staff member on duty in one hall (or as relief, hall empty) for one sitting."""
    exam_session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="duties")
    exam_date = models.DateField()
    sitting = models.CharField(max_length=2, choices=SITTING_CHOICES)
    hall = models.ForeignKey(ExamHall, on_delete=models.CASCADE, null=True, blank=True, related_name="duties")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_duties")

    class Meta:
        ordering = ["exam_date", "sitting", "hall__order", "hall__name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["exam_session", "exam_date", "sitting", "staff"], name="one_duty_per_staff_sitting"),
        ]


# ======================================================================
# CO-PO PART B - IA question paper, marks by question, CO action plans
#   IAQuestion        one question of an IA paper (Q1, Q4a ...) with its marks
#                     and the course outcome it tests
#   IAQuestionMark    one student's marks for one question. When an IA has a
#                     paper, IAMark.marks_obtained is the sum of these (saved
#                     together), so everything that reads IA totals is unchanged
#   COActionPlan      what the teacher will do about a CO below target
# The rules and API live in modules/exams/co_marks.py.
# ======================================================================
class IAQuestion(models.Model):
    BLOOM = [("", "-"), ("remember", "Remember"), ("understand", "Understand"), ("apply", "Apply"),
             ("analyse", "Analyse"), ("evaluate", "Evaluate"), ("create", "Create")]

    assessment = models.ForeignKey(InternalAssessment, on_delete=models.CASCADE, related_name="questions")
    label = models.CharField(max_length=10)                         # "Q1", "Q4a"
    max_marks = models.DecimalField(max_digits=5, decimal_places=1)
    outcome = models.ForeignKey("teachingplan.CourseOutcome", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="ia_questions")
    bloom = models.CharField(max_length=12, choices=BLOOM, blank=True, default="")
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["assessment", "label"], name="unique_ia_question_label")]


class IAQuestionMark(models.Model):
    question = models.ForeignKey(IAQuestion, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="ia_question_marks")
    marks = models.DecimalField(max_digits=5, decimal_places=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["question", "student"], name="one_mark_per_question")]


class COActionPlan(models.Model):
    teaching_assignment = models.ForeignKey("courses.TeachingAssignment", on_delete=models.CASCADE,
                                            related_name="co_action_plans")
    outcome = models.ForeignKey("teachingplan.CourseOutcome", on_delete=models.CASCADE, related_name="action_plans")
    text = models.TextField()
    updated_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["teaching_assignment", "outcome"],
                                               name="one_action_plan_per_co")]
