from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


# ===================== PLACEMENT COORDINATOR =====================
class PlacementCoordinator(models.Model):
    """
    A faculty member who also handles placement work for their department.

    Modelled as an ASSIGNMENT ROW, not a role -- exactly like YearTutor.
    The teacher keeps role='teacher', so every existing permission check that
    asks "is this a teacher?" keeps working. Making coordinator a role value
    would silently strip their subject access the moment they were assigned.
    """

    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='placement_coordinator_roles',
    )

    department = models.ForeignKey(
        'users.Department',
        on_delete=models.CASCADE,
        related_name='placement_coordinators',
    )

    # Assignments are ended by clearing this flag, never by deleting the row --
    # so "who coordinated last year" stays answerable.
    is_active = models.BooleanField(default=True)

    assigned_at = models.DateTimeField(default=timezone.now)

    assigned_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='placement_coordinators_assigned',
    )

    class Meta:
        ordering = ['department__name', '-assigned_at']
        constraints = [
            # One ACTIVE coordinator per department. Past assignments are
            # exempt because is_active is False, which is what lets history
            # accumulate without blocking a new assignment.
            models.UniqueConstraint(
                fields=['department'],
                condition=models.Q(is_active=True),
                name='unique_active_coordinator_per_department',
            ),
        ]

    def __str__(self):
        state = "active" if self.is_active else "past"
        return f"{self.teacher.username} -> {self.department.name} ({state})"


# ===================== COMPANY =====================
class Company(models.Model):
    """
    A recruiting company.

    Kept deliberately thin. Everything about a specific visit belongs on
    Drive, and everything about a specific position on JobRole. A company
    that recruits three years running is ONE row with three drives.
    """

    CATEGORY_CHOICES = [
        ('product', 'Product'),
        ('service', 'Service'),
        ('core', 'Core'),
        ('startup', 'Startup'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200, unique=True)

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='other',
    )

    website = models.URLField(blank=True)
    about = models.TextField(blank=True)

    contact_person = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)

    
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='companies_created',
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Companies"

    def save(self, *args, **kwargs):
        # Stripped so " Zoho" and "Zoho " cannot both exist and defeat the
        # unique constraint.
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ===================== DRIVE =====================
class Drive(models.Model):
    """
    One company's recruitment visit.

    ROUNDS ARE OPTIONAL. Companies run their tests on their own platforms,
    so the college does not test anyone. What it can do is RECORD the
    shortlist each round produces (usually emailed by the company) -- see
    DriveRound below. A role with no rounds works exactly as before:
    attendance, then offers.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),            # being set up, students cannot see it
        ('published', 'Published'),    # open for applications
        ('closed', 'Closed'),          # deadline passed
        ('completed', 'Completed'),    # offers released
        ('cancelled', 'Cancelled'),    # company withdrew
    ]

    company = models.ForeignKey(
        'placement.Company',
        on_delete=models.PROTECT,
        related_name='drives',
    )

    # A label for the visit, e.g. "2026 Campus Drive". Optional -- falls back
    # to the company name in __str__.
    title = models.CharField(max_length=200, blank=True)

    description = models.TextField(blank=True)

    # DateTime, not Date: "closes on the 14th" is ambiguous about whether the
    # 14th counts, and students will apply at 11pm.
    application_deadline = models.DateTimeField(null=True, blank=True)

    drive_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
    )

    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drives_created',
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_open(self):
        """
        Whether a student may apply right now.

        Computed from status and deadline together -- never stored. A stored
        flag would need a scheduled job to flip it at the deadline, and would
        be wrong in the window before that job ran.
        """
        if self.status != 'published':
            return False
        if self.application_deadline and timezone.now() > self.application_deadline:
            return False
        return True

    def __str__(self):
        return self.title or f"{self.company.name} drive"


# ===================== JOB ROLE =====================
class JobRole(models.Model):
    """
    One position within a drive.

    Split out of Drive because a single visit can open several roles at
    different packages -- "Software Engineer at 7 LPA" and "Support Engineer
    at 4 LPA" from the same company on the same day.

    ELIGIBILITY ATTACHES HERE, NOT TO THE DRIVE. That is the point of the
    split: those two roles will usually have different CGPA cutoffs, and a
    rule on the drive would force them to share one.
    """

    drive = models.ForeignKey(
        Drive,
        on_delete=models.CASCADE,
        related_name='job_roles',
    )

    title = models.CharField(max_length=200)

    # Decimal, not Float -- packages are summed and averaged for reports, and
    # float drift would show up in numbers a college publishes.
    package_lpa = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    job_location = models.CharField(max_length=200, blank=True)
    bond_details = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    # How many the company intends to hire. Null = not stated.
    openings = models.PositiveIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['drive', '-package_lpa', 'title']
        constraints = [
            models.UniqueConstraint(
                fields=['drive', 'title'],
                name='unique_role_title_per_drive',
            ),
        ]

    @property
    def is_open(self):
        """A role is open only if its drive is open AND the role is active."""
        return self.is_active and self.drive.is_open

    def __str__(self):
        return f"{self.drive.company.name} - {self.title}"


# ===================== ELIGIBILITY RULE =====================
class EligibilityRule(models.Model):
    """
    What a student must meet to apply for one JOB ROLE.

    OneToOne with JobRole, not Drive. Two roles in the same visit routinely
    have different cutoffs, and a rule on the drive would collapse them into
    one -- silently letting a 6.0 student into a 7.0 role.

    NOTHING here is a copy of student data. CGPA, arrears and passing year are
    read live from exams/services.py at check time; 10th and 12th come from
    PriorAcademics.

    Every field is nullable, and null means "no limit on this" -- a min_cgpa
    of 0 and an unset min_cgpa are different rules.
    """

    job_role = models.OneToOneField(
        JobRole,
        on_delete=models.CASCADE,
        related_name='eligibility',
    )

    min_cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # 0 means "no standing arrears allowed". null means the company does not
    # care. Different rules, so this must stay nullable.
    max_arrears = models.PositiveIntegerField(null=True, blank=True)

    min_tenth_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Compared against PriorAcademics.qualifying_percent -- 12th for a regular
    # student, diploma for a lateral entry one. That rule lives in the
    # property alone, so it cannot drift.
    min_twelfth_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Empty means every department. A M2M rather than a list of codes, so a
    # renamed department cannot break an existing rule.
    allowed_departments = models.ManyToManyField(
        'users.Department',
        blank=True,
        related_name='eligible_job_roles',
    )

    passing_year = models.IntegerField(null=True, blank=True)

    allow_lateral_entry = models.BooleanField(default=True)


    placed_package_cap = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True)

    # Used by placement/eligibility.py. Here rather than in the service so
    # "empty means all branches" has one definition.

    def allowed_department_ids(self):
        # .all() uses prefetch_related data when present (values_list never does)
        return [d.id for d in self.allowed_departments.all()]

    def allowed_department_names(self):
        names = [d.name for d in self.allowed_departments.all()]
        return ", ".join(names) if names else "All branches"

    def __str__(self):
        return f"Eligibility for {self.job_role}"


# ===================== APPLICATION =====================
class Application(models.Model):
    """
    A student's decision about one JOB ROLE.

    Applications attach to the role, not the drive: a student may apply for
    Support Engineer and skip Software Engineer at the same company.

    THREE STATES, ONLY TWO STORED. "Applied" and "opted out" are rows.
    "No response" is the ABSENCE of a row -- every eligible student who has
    not decided yet. Storing a row per non-response would mean generating
    thousands of rows nobody created, and every one of them would need
    updating whenever eligibility changed.
    """

    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('opted_out', 'Not interested'),
        ('withdrawn', 'Withdrawn'),
    ]

    student = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='placement_applications',
    )

    job_role = models.ForeignKey(
        JobRole,
        on_delete=models.CASCADE,
        related_name='applications',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='applied',
    )

    # Required when opting out, enforced in the serializer. A skipped drive
    # with no reason tells the placement cell nothing -- and chasing students
    # who quietly ignored a drive is most of the job.
    opt_out_reason = models.TextField(blank=True)

    # A SNAPSHOT of why the student was allowed to apply, taken at apply time.
    # This is the one place a snapshot is right: it records what was true when
    # the decision was made. Live eligibility answers "can they apply now",
    # which is a different question once results change afterwards.
    eligibility_snapshot = models.JSONField(null=True, blank=True)

    applied_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-applied_at']
        constraints = [
            # One decision per student per role. Changing their mind updates
            # this row rather than adding a second one, so the history stays
            # readable and the counts cannot double.
            models.UniqueConstraint(
                fields=['student', 'job_role'],
                name='unique_application_per_student_role',
            ),
        ]

    @property
    def is_active(self):
        """Applied and not withdrawn -- the students a company will see."""
        return self.status == 'applied'

    def __str__(self):
        return f"{self.student.username} -> {self.job_role} ({self.status})"


# ===================== DRIVE ATTENDANCE =====================
class DriveAttendance(models.Model):


    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
    ]

    application = models.OneToOneField(
        'placement.Application',
        on_delete=models.CASCADE,
        related_name='drive_attendance',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='present',
    )

    remarks = models.CharField(max_length=255, blank=True)

    # The OD this created. Nullable for three real cases: the student was
    # marked absent, the drive has no date so no OD is possible, or the row
    # predates OD creation. Keeping the link means re-marking updates one OD
    # instead of leaving a trail of them.
    od_request = models.ForeignKey(
        'attendance.ODRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drive_attendances',
    )

    marked_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drive_attendance_marked',
    )

    marked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-marked_at']

    def __str__(self):
        return f"{self.application.student.username} - {self.status}"


# ===================== OFFER =====================
class Offer(models.Model):
    
    STATUS_CHOICES = [
        ('offered', 'Offered'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    application = models.OneToOneField(
        'placement.Application',
        on_delete=models.CASCADE,
        related_name='offer',
    )

    # Copied from JobRole at offer time rather than read live. The role's
    # advertised package can be edited afterwards, and an offer must record
    # what was actually offered -- a historical fact, not a lookup.
    package_lpa = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    offer_letter = models.FileField(
        upload_to='offer_letters/',
        null=True,
        blank=True,
    )

    joining_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='offered',
    )

    remarks = models.CharField(max_length=255, blank=True)

    offered_on = models.DateField(default=timezone.localdate)   # date, not datetime

    # When the STUDENT accepted or declined. Null while undecided, which is a
    # real state -- an offer nobody has answered yet.
    decided_at = models.DateTimeField(null=True, blank=True)

    recorded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='offers_recorded',
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-offered_on']

    def __str__(self):
        return (
            f"{self.application.student.username} - "
            f"{self.application.job_role} ({self.status})"
        )

# ===================== DRIVE ROUNDS (optional) =====================
class DriveRound(models.Model):
    """
    One selection step for a JOB ROLE: online test, group discussion,
    technical interview, HR...

    The college does not run these. The placement office only records who
    CLEARED each round, from the shortlist the company sends back.

    Who is IN a round is derived, never stored:
      first round  -> everyone with an active application for the role
      later rounds -> everyone marked 'cleared' in the previous round
    so deleting or re-marking a round can never leave stale rosters behind.
    """

    TYPE_CHOICES = [
        ('aptitude', 'Online / aptitude test'),
        ('gd', 'Group discussion'),
        ('technical', 'Technical interview'),
        ('hr', 'HR interview'),
        ('other', 'Other'),
    ]

    job_role = models.ForeignKey(
        JobRole,
        on_delete=models.CASCADE,
        related_name='rounds',
    )
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=120)
    round_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    round_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['job_role', 'order']
        constraints = [
            models.UniqueConstraint(
                fields=['job_role', 'order'],
                name='unique_round_order_per_role',
            ),
        ]

    def __str__(self):
        return f"{self.job_role} - {self.name}"


class RoundResult(models.Model):
    """One student's outcome in one round. No row = not marked yet."""

    STATUS_CHOICES = [
        ('cleared', 'Cleared'),
        ('not_cleared', 'Not cleared'),
        ('absent', 'Absent'),
    ]

    round = models.ForeignKey(
        DriveRound,
        on_delete=models.CASCADE,
        related_name='results',
    )
    application = models.ForeignKey(
        'placement.Application',
        on_delete=models.CASCADE,
        related_name='round_results',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    remarks = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='round_results_marked',
    )
    marked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['round', 'application'],
                name='unique_result_per_round_application',
            ),
        ]

    def __str__(self):
        return f"{self.application.student.username} - {self.round.name}: {self.status}"


# ===================== OFFER POLICY (dream / super dream) =====================
class PlacementPolicy(models.Model):
    """
    College-wide offer tiers. ONE row (pk=1) -- use PlacementPolicy.current().

    With tiers on, a role's tier comes from its package:
        package >= super_dream_min_lpa -> Super dream
        package >= dream_min_lpa       -> Dream
        anything else                  -> Regular
    A student holding an ACCEPTED offer may only apply to roles in a HIGHER
    tier (regular -> dream -> super dream). This works alongside each role's
    own placed_package_cap; both are checked in eligibility.py.
    """

    tiers_enabled = models.BooleanField(default=False)

    # COLLEGE RULES (checked for every role in eligibility.py)
    # Placement is for the final year: Year 4 of a 4-year course, Year 2 of
    # a 2-year course - worked out from the course, never typed per role.
    final_year_only = models.BooleanField(default=True)
    # A student holding an ACCEPTED offer may apply only to roles paying the
    # SAME OR MORE than their best accepted package. Offers not yet accepted
    # don't count - the student hasn't decided.
    higher_package_only = models.BooleanField(default=True)
    dream_min_lpa = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    super_dream_min_lpa = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    updated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Placement offer policy"


# ===================== HIGHER STUDIES (for NIRF / NAAC) =====================
class HigherStudies(models.Model):
    """
    A student who went for higher studies instead of (or as well as) a job.
    NIRF and NAAC both ask for this count next to the placement numbers.
    """

    student = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='higher_studies',
    )
    institution = models.CharField(max_length=200)
    programme = models.CharField(max_length=150, blank=True)   # M.E., MBA, MS...
    admission_year = models.IntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = 'Higher studies'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} - {self.institution}"


# ===================== SAVED ELIGIBILITY (meeting point 10) =====================
class PlacementEligibility(models.Model):
    """
    The SAVED answer of eligibility.check_eligibility() for one student and
    one job role - so lists and counts read one row instead of recomputing
    every rule for every student on every page load.

    This table never DECIDES anything. check_eligibility() is the only place
    the rules live; eligibility_store.py writes its answer here whenever
    something it depends on changes (drive published, rule edited, results
    published, marks verified, offer accepted, policy changed) and once a
    night as a safety net. Applying still runs the live check, so a stale row
    can never let an ineligible student in.
    """

    student = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='placement_eligibility',
    )
    job_role = models.ForeignKey(
        JobRole,
        on_delete=models.CASCADE,
        related_name='eligibility_results',
    )
    eligible = models.BooleanField(default=False)
    blockers = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)
    checks = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)
    checked_at = models.DateTimeField(auto_now=True)

    # set when the "you're eligible" notice went out on publish - once per
    # student per role, so re-publishing never sends it twice
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'job_role'], name='unique_eligibility_per_student_role'),
        ]
        indexes = [models.Index(fields=['job_role', 'eligible'])]

    def __str__(self):
        return f"{self.student.username} - {self.job_role} ({'eligible' if self.eligible else 'not eligible'})"

