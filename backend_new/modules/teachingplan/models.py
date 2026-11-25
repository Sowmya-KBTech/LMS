# backend/teaching_plans/models.py
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# ============================================================
# CONFIG — point these three strings at YOUR existing models.
# Format is "app_label.ModelName". Check each app's models.py.
# ============================================================
SUBJECT_MODEL = "courses.Subject"     # your Subject lives in the courses app
DEPARTMENT_MODEL = "users.Department"  # your Department lives in the users app (its hod FK already matches)
# (User comes from settings.AUTH_USER_MODEL automatically.)
# ============================================================


class TeachingPlan(models.Model):
    STATUS = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teaching_plans"
    )
    subject = models.ForeignKey(
        SUBJECT_MODEL, on_delete=models.CASCADE, related_name="teaching_plans"
    )
    department = models.ForeignKey(
        DEPARTMENT_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teaching_plans"
    )
    # If you have a Section/Class model, you can later swap this CharField for an FK.
    class_section = models.CharField(max_length=100)   # e.g. "CSE 3rd year - A"
    semester = models.CharField(max_length=50)         # e.g. "Odd semester 2026"
    allotted_hours = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    hod_comment = models.TextField(blank=True, default="")

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_plans"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # One plan per teacher+subject+class+semester (a teacher can't submit two for the same class).
        unique_together = ("teacher", "subject", "class_section", "semester")

    def __str__(self):
        return f"{self.subject} · {self.class_section} ({self.get_status_display()})"

    # ---- progress helpers (used by the HOD department view) ----
    @property
    def total_units(self):
        return self.units.count()

    @property
    def done_units(self):
        # COURSE PLAN (Part B): a session counts as done once the teacher records
        # that it was held (as planned, partly, or with a different topic).
        return self.deliveries.filter(status__in=HELD_STATUSES).count()

    def unrecorded_past_sessions(self, today=None):
        """Planned sessions before today with nothing recorded yet."""
        from datetime import date as _date
        today = today or _date.today()
        recorded = {(d.date, d.period_no) for d in self.deliveries.all()}
        return [u for u in self.units.all()
                if u.complete_by and u.complete_by < today and (u.complete_by, u.period_no) not in recorded]


# ============================================================
# COURSE PLAN (upgrade): what each session is about and how it is taught.
# The lists are deliberately short; "other" covers the rest. Blank = not chosen.
# ============================================================
MAX_UNITS = 10

TEACHING_MODES = [
    ("lecture", "Lecture"),
    ("tutorial", "Tutorial"),
    ("lab", "Lab / practical"),
    ("online", "Online class"),
    ("seminar", "Seminar"),
    ("revision", "Revision"),
    ("assessment", "Test / assessment"),
]
TEACHING_METHODS = [
    ("chalk_talk", "Chalk and talk"),
    ("presentation", "Presentation (PPT)"),
    ("demonstration", "Demonstration"),
    ("discussion", "Discussion"),
    ("case_study", "Case study"),
    ("problem_solving", "Problem solving"),
    ("flipped", "Flipped class"),
    ("activity", "Activity-based"),
    ("project", "Project-based"),
    ("video", "Video / animation"),
    ("other", "Other"),
]
CLASS_ACTIVITIES = [
    ("quiz", "Quiz"),
    ("assignment", "Assignment"),
    ("worksheet", "Worksheet"),
    ("presentation", "Student presentation"),
    ("group_work", "Group work"),
    ("lab_record", "Lab record"),
    ("other", "Other"),
]
BEYOND_ACTIVITIES = [
    ("industrial_visit", "Industrial visit"),
    ("guest_lecture", "Guest lecture"),
    ("workshop", "Workshop"),
    ("seminar", "Seminar"),
    ("field_work", "Field work"),
    ("competition", "Competition / hackathon"),
    ("mooc", "MOOC / NPTEL"),
    ("other", "Other"),
]


# ============================================================
# COURSE PLAN (Part B): course outcomes and what was actually delivered.
# ============================================================
BLOOM_LEVELS = [
    ("remember", "Remember"),
    ("understand", "Understand"),
    ("apply", "Apply"),
    ("analyse", "Analyse"),
    ("evaluate", "Evaluate"),
    ("create", "Create"),
]
MAX_OUTCOMES = 12
LOW_COVERAGE = 3          # an outcome taught in fewer sessions than this gets a warning

DELIVERY_STATUSES = [
    ("as_planned", "As planned"),
    ("partly", "Partly covered"),
    ("different", "Different topic"),
    ("not_held", "Class not held"),
]
HELD_STATUSES = ("as_planned", "partly", "different")


class CourseOutcome(models.Model):
    """What students should be able to do after the course (CO1, CO2 ...).
    Belongs to the SUBJECT, so every section and teacher of the subject shares it."""
    subject = models.ForeignKey(SUBJECT_MODEL, on_delete=models.CASCADE, related_name="course_outcomes")
    code = models.CharField(max_length=10)                      # "CO1"
    text = models.CharField(max_length=300)
    level = models.CharField(max_length=12, choices=BLOOM_LEVELS, blank=True, default="")
    order = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["subject", "order", "id"]
        constraints = [models.UniqueConstraint(fields=["subject", "code"], name="unique_co_code_per_subject")]

    def __str__(self):
        return f"{self.code} {self.text[:40]}"


class SessionDelivery(models.Model):
    """What actually happened in one planned session (date + period).
    Kept apart from PlanUnit because a draft plan's sessions are rebuilt on every save."""
    plan = models.ForeignKey(TeachingPlan, on_delete=models.CASCADE, related_name="deliveries")
    date = models.DateField()
    period_no = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=DELIVERY_STATUSES)
    covered = models.CharField(max_length=200, blank=True, default="")    # what was actually taught
    remarks = models.TextField(blank=True, default="")
    carried_to = models.DateField(null=True, blank=True)                 # unfinished topic moved to this date
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "period_no"]
        constraints = [models.UniqueConstraint(fields=["plan", "date", "period_no"],
                                               name="unique_delivery_per_session")]

    def __str__(self):
        return f"{self.plan_id} {self.date} P{self.period_no} {self.status}"


class PlanUnit(models.Model):
    """One class SESSION of the plan (a date + period), despite the old name."""
    plan = models.ForeignKey(TeachingPlan, on_delete=models.CASCADE, related_name="units")
    topic = models.CharField(max_length=200)
    hours = models.PositiveIntegerField(default=0)
    # Planned deadline — auto-filled from the timetable on the frontend, stored here.
    complete_by = models.DateField(null=True, blank=True)
    sequence_no = models.PositiveIntegerField(default=1)

    # Which period of the day this class hour is (1, 2, 3...).
    # A subject can meet more than once on the same date, so complete_by alone does
    # not identify a class — the pair (complete_by, period_no) does. Without this, a
    # topic's period can only be guessed by counting its position in the class-day
    # list, and that count shifts the moment a holiday is added.
    # null=True because rows written before this migration have no period yet.
    period_no = models.PositiveIntegerField(null=True, blank=True)

    # COURSE PLAN (upgrade): unit of the syllabus, notes and how it is taught.
    # Unit and teaching mode are required when the plan is sent to the HOD.
    unit_no = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(MAX_UNITS)])
    notes = models.TextField(blank=True, default="")
    mode = models.CharField(max_length=20, choices=TEACHING_MODES, blank=True, default="")
    method = models.CharField(max_length=30, choices=TEACHING_METHODS, blank=True, default="")
    class_activity = models.CharField(max_length=30, choices=CLASS_ACTIVITIES, blank=True, default="")
    beyond_activity = models.CharField(max_length=30, choices=BEYOND_ACTIVITIES, blank=True, default="")
    # COURSE PLAN (Part B): which course outcomes this session teaches
    outcomes = models.ManyToManyField(CourseOutcome, blank=True, related_name="sessions")

    # Filled in after the plan is approved, as the teacher logs progress.
    is_completed = models.BooleanField(default=False)
    actual_completed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["sequence_no"]

    def __str__(self):
        return f"{self.topic} ({self.hours}h)"


# ======================================================================
# CO-PO PART A - programme outcomes, CO-PO mapping, attainment rules
#   ProgramOutcome   PO1..PO12 for the whole college (course empty) and each
#                    course's own PSOs (course set)
#   COPOMap          how strongly a course outcome supports a PO / PSO: 1, 2, 3
#   AttainmentRule   the numbers attainment is worked out with - one for the
#                    college (department empty), optionally one per department
# The rules and API live in modules/teachingplan/outcomes.py.
# ======================================================================
class ProgramOutcome(models.Model):
    PO = "po"
    PSO = "pso"
    KINDS = [(PO, "Programme outcome"), (PSO, "Programme specific outcome")]

    course = models.ForeignKey("courses.Course", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="program_outcomes")
    kind = models.CharField(max_length=3, choices=KINDS, default=PO)
    code = models.CharField(max_length=10)                      # "PO1", "PSO2"
    text = models.CharField(max_length=300)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["kind", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["course", "code"], name="unique_po_code_per_course"),
            models.UniqueConstraint(fields=["code"], condition=models.Q(course__isnull=True),
                                    name="unique_college_po_code"),
        ]

    def __str__(self):
        return self.code


class COPOMap(models.Model):
    outcome = models.ForeignKey(CourseOutcome, on_delete=models.CASCADE, related_name="po_links")
    program_outcome = models.ForeignKey(ProgramOutcome, on_delete=models.CASCADE, related_name="co_links")
    strength = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(3)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["outcome", "program_outcome"], name="one_link_per_co_po")]


class AttainmentRule(models.Model):
    department = models.OneToOneField(DEPARTMENT_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                      related_name="attainment_rule")
    student_target_pct = models.PositiveSmallIntegerField(default=60)   # a student reaches a CO at this %
    level3_pct = models.PositiveSmallIntegerField(default=70)           # % of students for level 3
    level2_pct = models.PositiveSmallIntegerField(default=60)
    level1_pct = models.PositiveSmallIntegerField(default=50)
    internal_share = models.PositiveSmallIntegerField(default=30)       # direct = int x% + end (100-x)%
    direct_share = models.PositiveSmallIntegerField(default=80)         # final = direct x% + survey (100-x)%
    co_target = models.DecimalField(max_digits=3, decimal_places=2, default=2)
    po_target = models.DecimalField(max_digits=3, decimal_places=2, default=2)
    use_ia = models.BooleanField(default=True)
    use_online_tests = models.BooleanField(default=True)
    use_assignments = models.BooleanField(default=False)
    survey_min_pct = models.PositiveSmallIntegerField(default=50)       # responses needed to count the survey
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["department"], condition=models.Q(department__isnull=True),
                                    name="one_college_attainment_rule"),
        ]
