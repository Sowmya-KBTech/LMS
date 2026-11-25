# backend/mentoring/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property


# ================= GRADE BAND =================
BAND_CHOICES = (
    ("A", "Grade A"),
    ("B", "Grade B"),
    ("C", "Grade C"),
)


def _current_academic_year():
    """
    June to May. Mirrors utils.current_academic_year.

    Duplicated deliberately: utils imports models, so models importing utils
    back would be a cycle. Four lines is cheaper than restructuring both.
    """
    today = timezone.localdate()
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{start + 1}"


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

    # NOTE: require_all_bands used to be a column here. It said the same thing
    # as MentorRule.grade_mix and nothing kept the two in step, so a HOD could
    # turn the rule off in Settings and watch team formation carry on enforcing
    # it. MentorRule is now the single source of truth and this is derived from
    # it — see the cached_property at the bottom of this class.

    # the tutor proposes, HOD approves. False = HOD allocates directly.
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

    @cached_property
    def require_all_bands(self):
        """
        Does this department's mentor groups need a mix of A, B and C?

        Derived from MentorRule.grade_mix for the CURRENT academic year, which
        is the only place the policy is set. Kept under the old field name so
        fit_score, group_balance and why_best_fit read it unchanged.

        cached_property matters: fit_score runs once per mentor per student
        inside suggest_split, and an uncached lookup would be a query each time.

        A past academic year on a read-only screen sees the current year's
        policy. The composition rule does not change year to year in practice,
        and the alternative is threading an academic_year through five call
        sites for a historical view nobody edits.
        """
        rule = MentorRule.objects.filter(
            department_id=self.department_id,
            academic_year=_current_academic_year(),
        ).first()
        # No rule row yet means nothing has been configured, and MentorRule's
        # own default is "abc" — so the answer is the same either way.
        return rule.grade_mix == "abc" if rule else True


# ================= MENTOR ALLOCATION =================
class MentorAllocation(models.Model):
    """
    One row per student per academic year per mentor.

    Nothing is ever deleted. Removing or reassigning closes the row
    (is_active=False, end_date set) and, for a reassign, opens a new one.
    That is what makes the history page possible.
    """

    STATUS_CHOICES = (
        ("pending", "Awaiting HOD approval"),   # proposed by a tutor
        ("active", "Active"),
        ("closed", "Closed"),                   # removed, reassigned or year rollover
        ("rejected", "Proposal rejected"),      # HOD said no to a tutor proposal
    )

    SOURCE_CHOICES = (
        ("advisor", "Tutor proposal"),
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
      student, normal reason  -> tutor -> HOD
      student, sensitive      -> HOD only, the tutor never sees it
      mentor                  -> HOD only, there is no tutor step

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

    # these skip the tutor entirely
    CONFIDENTIAL_REASONS = ("comfort", "gender")
    # only a mentor may pick these
    STAFF_ONLY_REASONS = ("capacity", "leave")

    ROLE_CHOICES = (
        ("student", "Raised by the student"),
        ("mentor", "Raised by the mentor"),
    )

    STATUS_CHOICES = (
        ("advisor",   "With the tutor"),
        ("hod",       "With the HOD"),
        ("approved",  "Approved — student moved"),
        ("rejected",  "Rejected by the HOD"),
        ("resolved",  "Resolved by the tutor"),
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

    # ---- tutor step ----
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

        The tutor step is dropped when the reason is sensitive, when a
        mentor raised it, when the department turned tutor routing off,
        when the class has no YearTutor, or when the tutor IS the
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


# ================= TEAM-BASED ALLOCATION =================
class MentorRule(models.Model):
    """
    One row per department + academic year. Read by student, tutor and HOD.

    grade_mix is the SINGLE source of truth for the composition rule.
    MentoringSetting.require_all_bands reads it rather than storing its own
    copy, so the two can no longer disagree.
    """

    GRADE_MIX = (("abc", "One A, one B, one C"), ("none", "No grade rule"))
    FALLBACK = (
        ("extra_member", "Allow an extra student from another band"),
        ("leave_short", "Leave those teams one short"),
    )

    department = models.ForeignKey(
        "users.Department", on_delete=models.CASCADE, related_name="mentor_rules"
    )
    academic_year = models.CharField(max_length=9)

    team_size = models.PositiveSmallIntegerField(default=3)
    grade_mix = models.CharField(max_length=5, choices=GRADE_MIX, default="abc")
    fallback = models.CharField(max_length=14, choices=FALLBACK, default="extra_member")

    skip_last_year_mentors = models.BooleanField(default=True)
    skip_class_advisors = models.BooleanField(default=False)
    tiebreak_fewest_mentees = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("department", "academic_year")]

    def __str__(self):
        return f"{self.department} · {self.academic_year}"


class MentorTeam(models.Model):
    """A team of students in one class that shares a mentor."""

    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="mentor_teams"
    )
    year = models.PositiveSmallIntegerField()
    academic_year = models.CharField(max_length=9)
    number = models.PositiveSmallIntegerField()

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        limit_choices_to={"role": "teacher"},
        related_name="mentor_teams",
    )
    mentor_was_suggested = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    is_closed = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="proposed_teams",
    )

    class Meta:
        unique_together = [("course", "year", "academic_year", "number")]
        ordering = ["number"]

    def __str__(self):
        return f"Team {self.number} · {self.course} Y{self.year}"


class MentorTeamMember(models.Model):
    """A student in a team. Join table so the fallback can add a fourth."""

    team = models.ForeignKey(
        MentorTeam, on_delete=models.CASCADE, related_name="members"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "student"},
        related_name="team_memberships",
    )

    # Copied from team.academic_year in save(). Denormalised deliberately: a
    # constraint cannot reach across the FK, and "one team per student per
    # year" is the rule that matters. Without it two simultaneous joins both
    # pass the Python check and the student lands in two teams at once.
    academic_year = models.CharField(max_length=9, blank=True, db_index=True)

    band = models.CharField(max_length=1, blank=True)
    is_extra = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("team", "student")]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                name="one_team_per_student_per_year",
            ),
        ]

    def save(self, *args, **kwargs):
        # Never set by a caller — always taken from the team, so the two can
        # never disagree.
        if self.team_id:
            self.academic_year = self.team.academic_year
        super().save(*args, **kwargs)


class UnplacedStudent(models.Model):
    """
    A student the tutor has deliberately left out of a team.

    Only needed when the department rule is 'leave_short': the fallback is off,
    nobody can take the student, and formation still has to close. Marking is
    explicit so nothing is silently dropped — the row records who decided and
    why, and disappears the moment the student is placed.
    """

    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="unplaced_students"
    )
    year = models.PositiveSmallIntegerField()
    academic_year = models.CharField(max_length=9)

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "student"},
        related_name="unplaced_marks",
    )
    band = models.CharField(max_length=1, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    marked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("student", "academic_year")]

    def __str__(self):
        return f"{self.student} left unplaced ({self.academic_year})"


class MentoringRecord(models.Model):
    """
    WAVE 1 - one mentoring / guidance session, recorded by the mentor.

    Category says what kind of guidance it was (the professor's feedback:
    academic, personal and psychological, competitive exams ...).

    Who sees what (record_views.py):
      summary, action points, follow-up  -> the student, their mentor(s), the HOD
      private_note                       -> ONLY the mentor who wrote it and the HOD
    Parents and admins never see private notes.
    """

    CATEGORY_CHOICES = (
        ("academic", "Academic"),
        ("personal", "Personal & psychological"),
        ("competitive", "Competitive exams"),
        ("career", "Career & placement"),
        ("other", "Other"),
    )
    MODE_CHOICES = (
        ("one_to_one", "One-to-one"),
        ("group", "Group"),
        ("phone", "Phone / online"),
        ("parent", "With parent"),
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="mentoring_records", limit_choices_to={"role": "student"},
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="mentoring_records_written",
    )
    department = models.ForeignKey(
        "users.Department", on_delete=models.CASCADE, related_name="mentoring_records",
    )
    academic_year = models.CharField(max_length=9, db_index=True)

    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, db_index=True)
    mode = models.CharField(max_length=12, choices=MODE_CHOICES, default="one_to_one")
    summary = models.TextField()
    action_points = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    private_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["student", "academic_year"])]

    def __str__(self):
        return f"{self.student} - {self.category} on {self.date}"
