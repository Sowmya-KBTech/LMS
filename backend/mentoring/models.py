# backend/mentoring/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone


# ================= GRADE BAND =================
BAND_CHOICES = (
    ("A", "Grade A"),
    ("B", "Grade B"),
    ("C", "Grade C"),
)


# ================= MENTORING SETTINGS (per department) =================
class MentoringSetting(models.Model):
    """One row per department. Created on demand by MentoringSetting.for_department()."""

    department = models.OneToOneField(
        "users.Department",
        on_delete=models.CASCADE,
        related_name="mentoring_setting",
    )

    # capacity is a WARNING, never a hard block
    max_students_per_mentor = models.PositiveIntegerField(default=25)

    # grade band thresholds, on a 10-point scale
    band_a_min = models.FloatField(default=8.0)
    band_b_min = models.FloatField(default=6.5)

    # every mentor group should hold A, B and C students
    require_all_bands = models.BooleanField(default=True)

    # class advisor proposes, HOD approves. False = HOD allocates directly.
    route_via_advisor = models.BooleanField(default=True)

    # Many colleges only start mentoring from second year, because a first year
    # has no published result to compute a grade from. Students below this year
    # are left out of the allocation screens entirely.
    allocate_from_year = models.PositiveSmallIntegerField(
        default=2,
        choices=((1, "I Year onwards"), (2, "II Year onwards"),
                 (3, "III Year onwards"), (4, "IV Year only")),
    )

    # only applies when allocate_from_year is 1
    FIRST_YEAR_CHOICES = (
        ("defer", "Allocate only after semester 1 results"),
        ("band_b", "Assign all first years band B"),
    )
    first_year_rule = models.CharField(
        max_length=10, choices=FIRST_YEAR_CHOICES, default="defer"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mentoring setting"

    def __str__(self):
        return f"Mentoring settings — {self.department.name}"

    @classmethod
    def for_department(cls, department):
        obj, _ = cls.objects.get_or_create(department=department)
        return obj


# ================= MENTOR ALLOCATION =================
class MentorAllocation(models.Model):
    """
    One row per student per academic year per mentor.

    Nothing is ever deleted. Removing or reassigning closes the row
    (is_active=False, end_date set) and, for a reassign, opens a new one.
    That is what makes the history page possible.
    """

    STATUS_CHOICES = (
        ("pending", "Awaiting HOD approval"),   # proposed by a class advisor
        ("active", "Active"),
        ("closed", "Closed"),                   # removed, reassigned or year rollover
        ("rejected", "Proposal rejected"),      # HOD said no to an advisor proposal
    )

    SOURCE_CHOICES = (
        ("advisor", "Class advisor proposal"),
        ("hod", "Assigned directly by the HOD"),
        ("auto", "Auto-distributed"),
        ("request", "Change request approved"),
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_allocations",
        limit_choices_to={"role": "student"},
    )

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mentee_allocations",
        limit_choices_to={"role": "teacher"},
    )

    department = models.ForeignKey(
        "users.Department",
        on_delete=models.CASCADE,
        related_name="mentor_allocations",
    )

    # "2026-2027"
    academic_year = models.CharField(max_length=9)

    # frozen at allocation time so later results never rewrite history
    grade_band = models.CharField(max_length=1, choices=BAND_CHOICES, blank=True)
    cgpa_at_allocation = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="hod")

    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="proposed_allocations",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_allocations",
    )

    # set when this row replaces an earlier one, so history reads "old -> new"
    previous_mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    # the best-fit mentor the system suggested, when it was not the one chosen
    suggested_mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    reason = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)

    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            # one live mentor per student per year. Many closed rows are fine.
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                condition=models.Q(is_active=True),
                name="one_active_mentor_per_student_per_year",
            ),
            # a student cannot have two proposals waiting at once either
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                condition=models.Q(status="pending"),
                name="one_pending_proposal_per_student_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["department", "academic_year", "status"]),
            models.Index(fields=["mentor", "is_active"]),
        ]

    def __str__(self):
        return f"{self.student} -> {self.mentor} ({self.academic_year})"

    # ---------- state changes ----------
    def approve(self, by_user):
        self.status = "active"
        self.is_active = True
        self.approved_by = by_user
        self.save(update_fields=["status", "is_active", "approved_by", "updated_at"])

    def close(self, reason="", by_user=None):
        self.status = "closed"
        self.is_active = False
        self.end_date = timezone.localdate()
        if reason:
            self.reason = reason
        self.save(update_fields=["status", "is_active", "end_date", "reason", "updated_at"])


# ================= MENTOR BROADCAST =================
class MentorBroadcast(models.Model):
    """
    A group announcement, recorded as its own row.

    An earlier version guessed at broadcasts by looking for the same text
    sent to several students at once. That silently failed for a mentor with
    one or two mentees, so the batch is stored explicitly now.
    """

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_broadcasts",
    )
    department = models.ForeignKey(
        "users.Department", on_delete=models.CASCADE, related_name="+"
    )
    academic_year = models.CharField(max_length=9)

    # "all", "year-3", "low-attendance"
    group_key = models.CharField(max_length=40, default="all")
    # the label the MENTOR saw. Never shown to a student — a performance
    # group name must not be readable by the person in it.
    group_label = models.CharField(max_length=120, blank=True)

    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.mentor} -> {self.group_label} ({self.created_at:%d %b})"


class MentorBroadcastRecipient(models.Model):
    """One row per student who received a broadcast."""

    broadcast = models.ForeignKey(
        MentorBroadcast, on_delete=models.CASCADE, related_name="recipients"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_broadcasts",
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-broadcast__created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["broadcast", "student"], name="one_row_per_student_per_broadcast"
            )
        ]

    def __str__(self):
        return f"{self.student} <- broadcast {self.broadcast_id}"

    

# ================= MENTOR CHANGE REQUEST =================
class MentorChangeRequest(models.Model):
    """
    A student or a mentor asking for a different allocation.

    Three routes, decided by who raised it and why:
      student, normal reason  -> class advisor -> HOD
      student, sensitive      -> HOD only, the advisor never sees it
      mentor                  -> HOD only, there is no advisor step

    The current mentor is never shown the request. Nothing changes until
    the HOD approves, and approving goes through MentorAllocation so the
    Allocation History page keeps working unchanged.
    """

    REASON_CHOICES = (
        ("timing",       "Free periods never match"),
        ("subject",      "Mentor works in a different subject area"),
        ("availability", "Mentor has not been available"),
        ("language",     "Language preference"),
        ("comfort",      "Not comfortable with the current mentor"),
        ("gender",       "Prefer a mentor of a particular gender"),
        ("capacity",     "Mentor is carrying too many students"),
        ("leave",        "Mentor is going on long leave"),
        ("other",        "Other"),
    )

    # these skip the class advisor entirely
    CONFIDENTIAL_REASONS = ("comfort", "gender")
    # only a mentor may pick these
    STAFF_ONLY_REASONS = ("capacity", "leave")

    ROLE_CHOICES = (
        ("student", "Raised by the student"),
        ("mentor", "Raised by the mentor"),
    )

    STATUS_CHOICES = (
        ("advisor",   "With the class advisor"),
        ("hod",       "With the HOD"),
        ("approved",  "Approved — student moved"),
        ("rejected",  "Rejected by the HOD"),
        ("resolved",  "Resolved by the class advisor"),
        ("withdrawn", "Withdrawn"),
    )
    OPEN_STATUSES = ("advisor", "hod")

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_change_requests",
        limit_choices_to={"role": "student"},
    )
    current_mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="change_requests_against",
        limit_choices_to={"role": "teacher"},
    )
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.CASCADE,
        related_name="mentor_change_requests",
    )
    academic_year = models.CharField(max_length=9)

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True,
        related_name="raised_change_requests",
    )
    raised_role = models.CharField(max_length=8, choices=ROLE_CHOICES, default="student")

    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    detail = models.TextField(blank=True)

    # set in save() from the reason. Never a checkbox the caller controls.
    is_confidential = models.BooleanField(default=False)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="hod")

    # ---- class advisor step ----
    advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="advised_change_requests",
    )
    advisor_note = models.TextField(blank=True)
    advisor_acted_at = models.DateTimeField(null=True, blank=True)

    # ---- HOD decision ----
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="decided_change_requests",
    )
    decision_note = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    new_mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    # the allocation row approving this request created
    new_allocation = models.ForeignKey(
        "mentoring.MentorAllocation",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # one open request per student per year. Closed ones are unlimited.
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                condition=models.Q(status__in=("advisor", "hod")),
                name="one_open_change_request_per_student_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["department", "academic_year", "status"]),
            models.Index(fields=["advisor", "status"]),
        ]

    def __str__(self):
        return f"{self.student} wants off {self.current_mentor} ({self.get_status_display()})"

    # ---------- routing ----------
    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def resolve_route(self, setting):
        """
        Work out the first stop and fill in self.advisor. Called before the
        first save(). Sets status to 'advisor' or 'hod'.

        The advisor step is dropped when the reason is sensitive, when a
        mentor raised it, when the department turned advisor routing off,
        when the class has no YearTutor, or when the class advisor IS the
        mentor being complained about. Nobody reviews a complaint about
        themselves.
        """
        from .utils import advisor_for_student

        if self.reason in self.CONFIDENTIAL_REASONS or self.raised_role == "mentor":
            self.advisor = None
            self.status = "hod"
            return self.status

        if not setting.route_via_advisor:
            self.advisor = None
            self.status = "hod"
            return self.status

        advisor = advisor_for_student(self.student)
        if advisor is None or advisor.id == self.current_mentor_id:
            self.advisor = None
            self.status = "hod"
        else:
            self.advisor = advisor
            self.status = "advisor"
        return self.status

    def save(self, *args, **kwargs):
        # the reason decides confidentiality, always — not the caller
        self.is_confidential = self.reason in self.CONFIDENTIAL_REASONS
        super().save(*args, **kwargs)