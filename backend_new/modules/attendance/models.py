from django.db import models
from django.conf import settings
from django.utils import timezone


# ============================================================================
#  Attendance
# ============================================================================


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('duty_leave', 'Duty Leave'),
    ]
    teaching_assignment = models.ForeignKey(
        "courses.TeachingAssignment",
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    student = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    date = models.DateField()
    hour = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    marked_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='attendance_marked'
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['teaching_assignment', 'student', 'date', 'hour'],
                name='unique_attendance_per_hour'
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.date} Hour {self.hour} - {self.status}"


# ============================================================================
#  Student OD (On Duty) requests
# ============================================================================


class ODRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class Stage(models.TextChoices):
        AWAITING_TUTOR = "awaiting_tutor", "Awaiting class advisor"
        AWAITING_HOD = "awaiting_hod", "Awaiting HOD"
        CLOSED = "closed", "Closed"

    class Category(models.TextChoices):
        PAPER = "paper_presentation", "Paper presentation"
        SEMINAR = "seminar", "Seminar / conference"
        PLACEMENT = "placement", "Placement drive"
        SPORTS = "sports", "Sports"
        NSS_NCC = "nss_ncc", "NSS / NCC"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="od_requests",
    )
    from_date = models.DateField()
    to_date = models.DateField()
    category = models.CharField(max_length=32, choices=Category.choices)
    reason = models.TextField()
    proof = models.FileField(upload_to="od_proofs/", null=True, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.AWAITING_TUTOR)

    tutor_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="od_tutor_reviews",
    )
    tutor_remark = models.CharField(max_length=255, blank=True)
    tutor_reviewed_at = models.DateTimeField(null=True, blank=True)

    hod_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="od_hod_reviews",
    )
    hod_remark = models.CharField(max_length=255, blank=True)
    hod_reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} · {self.category} · {self.from_date}→{self.to_date}"


# ============================================================================
#  Student leave requests (WAVE 1)
# ============================================================================


class StudentLeaveRequest(models.Model):
    """
    WAVE 1 - a student asks for leave (sick, personal, family ...).

    Same road as on duty: class in-charge first, then the HOD.
    Approved leave is an EXCUSED absence: the register and the student's own
    attendance show "On leave", but it does not count as present (on duty does).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class Stage(models.TextChoices):
        AWAITING_TUTOR = "awaiting_tutor", "Awaiting class in-charge"
        AWAITING_HOD = "awaiting_hod", "Awaiting HOD"
        CLOSED = "closed", "Closed"

    class LeaveType(models.TextChoices):
        SICK = "sick", "Sick / medical"
        PERSONAL = "personal", "Personal"
        FAMILY = "family", "Family function / emergency"
        OTHER = "other", "Other"

    # sick leave this long or longer needs a medical certificate
    PROOF_REQUIRED_DAYS = 3
    MAX_DAYS = 30
    BACKDATE_DAYS = 7

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_requests",
    )
    leave_type = models.CharField(max_length=16, choices=LeaveType.choices)
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField()
    proof = models.FileField(upload_to="student_leave_proofs/", null=True, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.AWAITING_TUTOR)

    tutor_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leave_tutor_reviews",
    )
    tutor_remark = models.CharField(max_length=255, blank=True)
    tutor_reviewed_at = models.DateTimeField(null=True, blank=True)

    hod_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leave_hod_reviews",
    )
    hod_remark = models.CharField(max_length=255, blank=True)
    hod_reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1

    def __str__(self):
        return f"{self.student} · leave · {self.from_date}->{self.to_date}"


# ============================================================================
#  Staff leave requests
# ============================================================================


class StaffLeaveRequest(models.Model):
    """
    Leave applied for by a teacher, approved or rejected by the HOD of that
    teacher's department. Single approval stage.

    An HOD's own leave (WAVE 2 Part 1b): the HOD names a `backup` teacher who
    handles their work during the leave, and the leave goes to the current
    PRINCIPAL for approval (level = "principal"; `hod` then holds the
    Principal it was routed to). When no Principal is set - or the HOD is the
    Principal - it is saved as RECORDED with no approval, as before.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        RECORDED = "recorded", "Recorded"   # HOD leave with no Principal set: saved, no approval needed

    class Level(models.TextChoices):
        HOD = "hod", "HOD"
        PRINCIPAL = "principal", "Principal"     # WAVE 2 Part 1b: an HOD's own leave

    class LeaveType(models.TextChoices):
        CASUAL = "casual", "Casual leave"
        EARNED = "earned", "Earned leave"            # HRIS PART A
        MEDICAL = "medical", "Medical leave"
        ON_DUTY = "on_duty", "On duty (conference / FDP / workshop)"
        COMPENSATORY = "compensatory", "Compensatory leave"
        OTHER = "other", "Other"

    class Session(models.TextChoices):
        FULL = "full", "Full day"
        FORENOON = "forenoon", "Forenoon"
        AFTERNOON = "afternoon", "Afternoon"

    # Types that cannot be submitted without a supporting document.
    PROOF_REQUIRED = {LeaveType.MEDICAL, LeaveType.ON_DUTY}

    # Types that may be applied for after the dates have passed
    # (you cannot get a medical certificate before falling ill).
    BACKDATED_ALLOWED = {LeaveType.MEDICAL}

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_leave_requests",
        limit_choices_to={"role": "teacher"},
    )

    # Snapshot of the department at the time of applying. Kept so that history
    # stays correct if the teacher is later moved to another department.
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff_leave_requests",
    )

    leave_type = models.CharField(max_length=16, choices=LeaveType.choices)
    from_date = models.DateField()
    to_date = models.DateField()
    session = models.CharField(
        max_length=10, choices=Session.choices, default=Session.FULL
    )

    # Working days in the range, half days included. Calculated on save from
    # the college working calendar — never sent by the client.
    days = models.DecimalField(max_digits=4, decimal_places=1, default=0)

    reason = models.TextField()
    proof = models.FileField(upload_to="staff_leave_proofs/", null=True, blank=True)

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )

    # Who decides: the department HOD, or the Principal for an HOD's own leave.
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.HOD)

    # The approver this request was routed to, resolved when it was created
    # (the HOD; the Principal when level = "principal").
    hod = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff_leave_to_review",
    )
    hod_remark = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff_leave_decisions",
    )

    # HOD leave only: the teacher who handles the HOD's work during the leave.
    backup = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff_leave_covering",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "from_date"]),
            models.Index(fields=["teacher", "status"]),
        ]

    def __str__(self):
        return (
            f"{self.teacher} · {self.get_leave_type_display()} · "
            f"{self.from_date}→{self.to_date} ({self.status})"
        )

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def is_open(self):
        """Still blocks an overlapping request."""
        return self.status in (
            self.Status.PENDING, self.Status.APPROVED, self.Status.RECORDED
        )

    @property
    def needs_proof(self):
        return self.leave_type in self.PROOF_REQUIRED


# ============================================================================
#  ATTENDANCE CORRECTION (#43 Change 2)
# ============================================================================
class AttendanceCorrection(models.Model):
    """
    ATTENDANCE CORRECTION: the class tutor (or main admin) changes a past
    attendance record, with a reason. Meeting point 6: past attendance is
    corrected only by the tutor, and every manual change is traceable.

    This table IS the audit log. A row is never edited or deleted. The
    student / subject / date / period are copied here so the history stays
    readable even if the attendance row changes again later.
    """

    CORRECTED_AS = [
        ("class_tutor", "Class tutor"),
        ("admin", "Admin"),
        ("subject_teacher", "Subject teacher"),   # #46 Part 2: change inside the window
    ]

    attendance = models.ForeignKey(
        Attendance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="corrections",
    )
    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="+",
    )
    teaching_assignment = models.ForeignKey(
        "courses.TeachingAssignment",
        on_delete=models.CASCADE,
        related_name="+",
    )
    date = models.DateField()
    hour = models.IntegerField()
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    reason = models.TextField()

    corrected_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    corrected_as = models.CharField(max_length=20, choices=CORRECTED_AS)
    corrected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-corrected_at"]
        verbose_name = "Attendance correction"

    def __str__(self):
        return (f"{self.student} {self.date} P{self.hour}: "
                f"{self.old_status} -> {self.new_status}")


# ============================================================================
#  ATTENDANCE LOCK (#46 Part 3)
# ============================================================================
class AttendanceLock(models.Model):
    """
    A period (subject + date + period) closed BEFORE its correction window
    ends: either the subject teacher clicked "Lock attendance", or the class
    tutor entered a very late period. There is no unlock — after this only the
    class tutor can correct it, with a reason.
    """

    REASONS = [
        ("teacher_lock", "Locked by the subject teacher"),
        ("tutor_late_entry", "Entered late by the class tutor"),
    ]

    teaching_assignment = models.ForeignKey(
        "courses.TeachingAssignment",
        on_delete=models.CASCADE,
        related_name="+",
    )
    date = models.DateField()
    hour = models.IntegerField()
    kind = models.CharField(max_length=20, choices=REASONS, default="teacher_lock")
    locked_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    locked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["teaching_assignment", "date", "hour"],
                name="unique_attendance_lock_per_period",
            )
        ]

    def __str__(self):
        return f"Lock {self.teaching_assignment_id} {self.date} P{self.hour}"

