from django.db import models
from django.conf import settings
from django.utils import timezone


# =====================================================
#  TIME SLOT  — the fixed daily periods (bell schedule)
#  Defined once for the whole college.
# =====================================================
class TimeSlot(models.Model):

    period_no = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Order of this period in the day (1, 2, 3 ...). "
                  "Use a high number like 99 for breaks if you want them last in ordering."
    )

    start_time = models.TimeField()
    end_time = models.TimeField()

    # e.g. "Break", "Lunch" — leave blank for normal class periods
    label = models.CharField(
        max_length=40,
        blank=True
    )

    # non-teaching slot (break / lunch) — shown as a band, never filled with a subject
    is_break = models.BooleanField(
        default=False
    )

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        tag = self.label or f"Period {self.period_no}"
        return f"{tag} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"


# =====================================================
#  TIMETABLE ENTRY  — one cell of a weekly grid
#  A TeachingAssignment placed on a day + period.
#  The assignment already carries course / year / subject / teacher,
#  and the semester comes through subject.semester.
# =====================================================
class TimetableEntry(models.Model):

    # ================= DAYS =================
    MON, TUE, WED, THU, FRI, SAT = range(6)

    DAY_CHOICES = [
        (MON, "Monday"),
        (TUE, "Tuesday"),
        (WED, "Wednesday"),
        (THU, "Thursday"),
        (FRI, "Friday"),
        (SAT, "Saturday"),
    ]

    # links to the existing courses app (no data duplicated).
    # NULL when this entry is an ACTIVITY (mentor, library, sports) — an
    # activity has no subject and no teaching assignment behind it.
    assignment = models.ForeignKey(
        'courses.TeachingAssignment',
        on_delete=models.CASCADE,
        related_name="timetable_entries",
        null=True, blank=True,
    )

    # is this cell a lecture, or a non-teaching activity?
    class Kind(models.TextChoices):
        CLASS    = "class",    "Class"
        ACTIVITY = "activity", "Activity"

    kind = models.CharField(
        max_length=12,
        choices=Kind.choices,
        default=Kind.CLASS,
    )

    # set only when kind == ACTIVITY
    class_activity = models.ForeignKey(
        "ClassActivity",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="entries",
    )

    day_of_week = models.PositiveSmallIntegerField(
        choices=DAY_CHOICES
    )

    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="entries"
    )

    # which physical room this class sits in.
    # quoted because Room is defined further down this file.
    room = models.ForeignKey(
        "Room",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="entries",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['day_of_week', 'time_slot__period_no']

        # A class (year + that subject's semester) can't have the same subject's
        # assignment placed twice in the same day+slot. The richer clash rules
        # (class clash by year+semester, teacher clash) are enforced in the view,
        # because they depend on related fields.
        constraints = [
            # Only for CLASS entries. `assignment` is NULL on activities, and in
            # SQL, NULL never equals NULL — so this constraint would silently
            # allow ten activities in one cell. The condition excludes them; the
            # one-thing-per-cell rule is enforced in the view for both kinds.
            models.UniqueConstraint(
                fields=['assignment', 'day_of_week', 'time_slot'],
                condition=models.Q(assignment__isnull=False),
                name='unique_entry_per_assignment_slot',
            )
        ]

    # ---- convenience accessors (survive `assignment` being None) ----
    @property
    def teacher(self):
        if self.assignment_id:
            return self.assignment.teacher
        return self.class_activity.teacher if self.class_activity_id else None

    @property
    def year(self):
        if self.assignment_id:
            return self.assignment.year
        return self.class_activity.year if self.class_activity_id else None

    @property
    def semester(self):
        if self.assignment_id:
            return self.assignment.subject.semester
        return self.class_activity.semester if self.class_activity_id else None

    def __str__(self):
        if self.assignment_id:
            what = self.assignment.subject.name
        elif self.class_activity_id:
            what = self.class_activity.activity.name
        else:
            what = "—"
        return f"{self.get_day_of_week_display()} P{self.time_slot.period_no} - {what}"


#=======================SEMESTER=======================#
class Semester(models.Model):

    name = models.CharField(max_length=100)        # e.g. "Even Semester 2026"
    start_date = models.DateField()
    end_date = models.DateField()

    # mark the term currently in use; the views read the active one
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"


# =====================================================
#  HOLIDAY  — a single date that overrides classes
#  (Sports Day, Independence Day, etc.)
# =====================================================
class Holiday(models.Model):

    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} - {self.name}"


# =====================================================
#  TIMETABLE APPROVAL  — one row per class (year + semester)
#  Tracks the HOD-submit -> admin-approve workflow.
#
#  status:
#    draft      -> HOD is still building (default)
#    submitted  -> HOD sent it to the admin for review (locked from editing)
#    approved   -> admin approved; ONLY approved classes are shown to
#                  students / teachers in their timetable view
#    rejected   -> admin sent it back with a remark; HOD can edit + resubmit
#
#  A class is identified by (year, semester). The course is stored too,
#  for display on the admin's approvals list.
# =====================================================
class TimetableApproval(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name="timetable_approvals",
        null=True, blank=True,
    )
    year = models.ForeignKey(
        'courses.Year',
        on_delete=models.CASCADE,
        related_name="timetable_approvals",
    )
    semester = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="timetable_submissions",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="timetable_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    remark = models.TextField(blank=True)

    last_active = models.DateTimeField(default=timezone.now)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["year", "semester"],
                name="unique_timetable_approval_per_class",
            )
        ]

    def __str__(self):
        yn = self.year.year_number if self.year else "?"
        return f"Year {yn} · Sem {self.semester} — {self.status}"


# =====================================================
#  ROOM — a physical space a class can be held in.
#  Rooms are college-wide; two departments must never
#  book the same room in the same period.
# =====================================================
class Room(models.Model):
    class Kind(models.TextChoices):
        CLASSROOM = "classroom", "Classroom"
        LAB       = "lab", "Lab"
        SEMINAR   = "seminar", "Seminar hall"

    name = models.CharField(max_length=40, unique=True)      # "R301", "Lab 2"
    kind = models.CharField(max_length=12, choices=Kind.choices,
                            default=Kind.CLASSROOM)
    capacity = models.PositiveSmallIntegerField(default=60)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# =====================================================
#  ACTIVITIES — non-teaching periods.
#
#  Mentor, Library, Sports, NSS, Placement Training. They occupy a cell in the
#  grid but they are not subjects: no syllabus, no weekly-hours target, and
#  usually no teacher.
#
#  Every preference below is SOFT — a weight in the solver's objective, never a
#  hard constraint. A mentor period stuck mid-day is a worse timetable; a solver
#  that returns INFEASIBLE is no timetable at all.
# =====================================================
class ActivityType(models.Model):

    class Position(models.TextChoices):
        ANY           = "any",          "Any period"
        FIRST         = "first",        "First period"
        LAST          = "last",         "Last period"
        FIRST_OR_LAST = "first_last",   "First or last period"
        BEFORE_LUNCH  = "before_lunch", "Before lunch"
        AFTER_LUNCH   = "after_lunch",  "After lunch"

    name = models.CharField(max_length=60, unique=True)

    # WHERE in the day it prefers to sit
    preferred_position = models.CharField(
        max_length=20,
        choices=Position.choices,
        default=Position.ANY,
    )

    # HOW its periods relate to each other — a separate axis from position, so
    # Placement Training can be "after lunch" AND "consecutive" at the same time.
    prefer_consecutive = models.BooleanField(default=False)

    colour = models.CharField(
        max_length=7,
        default="#94a3b8",
        help_text="Hex colour for the grid, e.g. #94a3b8",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClassActivity(models.Model):
    """One class's use of an activity: 'ECE Y2 Sem 3 has Library, 1/week'."""

    activity = models.ForeignKey(
        ActivityType,
        on_delete=models.CASCADE,
        related_name="class_activities",
    )
    year = models.ForeignKey(
        'courses.Year',
        on_delete=models.CASCADE,
        related_name="class_activities",
    )
    semester = models.PositiveSmallIntegerField()

    periods_per_week = models.PositiveSmallIntegerField(default=1)

    # Optional. NULL -> nobody supervises it, so it clashes with nothing.
    # Set   -> it blocks that teacher exactly like a lecture would.
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="class_activities",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "year", "semester"],
                name="uniq_class_activity",
            )
        ]
        ordering = ["activity__name"]

    def __str__(self):
        return f"{self.activity.name} — {self.year} Sem {self.semester}"