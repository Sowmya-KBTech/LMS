"""
ELECTIVES - college-based configuration (meeting point 9)

  ElectiveSetting  one row: who selects electives in this college
                   (students choose / HOD-staff allocate)
  ElectiveGroup    "from these, a student takes N" for one class,
                   e.g. B.E Mech · Year 3 · Sem 5 · Professional Elective I
  ElectiveOption   one choice inside a group = one teaching assignment
                   (subject + teacher), with an optional seat limit
  ElectiveChange   history: every pick, move and removal - who, when, why

The CHOICE itself is stored nowhere new: choosing an option = an Enrollment
in its teaching assignment. Attendance, IA, results and hall tickets already
read Enrollment, so they keep working unchanged (single source of truth).
The rules live in core/academics/electives.py.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ElectiveSetting(models.Model):
    """College-wide: who selects electives. One row (see current())."""

    STUDENTS = "students"
    STAFF = "staff"
    MODE_CHOICES = [
        (STUDENTS, "Students choose"),
        (STAFF, "HOD / staff allocate"),
    ]

    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=STUDENTS)
    updated_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Elective setting"

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def students_choose(self):
        return self.mode == self.STUDENTS

    def __str__(self):
        return self.get_mode_display()


class ElectiveGroup(models.Model):
    """A slot for one class: students take `picks` options from this group."""

    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='elective_groups')
    year = models.ForeignKey('courses.Year', on_delete=models.CASCADE, related_name='elective_groups')
    semester = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100, help_text="e.g. Professional Elective I")

    # whose HOD manages this group (Course has no department of its own)
    department = models.ForeignKey(
        'users.Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='elective_groups'
    )

    picks = models.PositiveSmallIntegerField(default=1, help_text="How many options each student takes")

    # CBCS PART B - open elective: offered to students of OTHER courses too
    # (same semester). Options may come from any course; a student can't take
    # an option taught to their own course. open_to blank = every course.
    open_elective = models.BooleanField(default=False)
    open_to = models.ManyToManyField('courses.Course', blank=True, related_name='open_elective_groups')

    # selection window - used when students choose. Blank = no limit.
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['course__name', 'year__year_number', 'semester', 'name']
        constraints = [
            models.UniqueConstraint(fields=['course', 'year', 'semester', 'name'],
                                    name='unique_elective_group_per_class'),
        ]

    def clean(self):
        errors = {}
        if self.year_id and self.course_id and self.year.course_id != self.course_id:
            errors['year'] = "This year does not belong to the selected course."
        if self.year_id and self.semester:
            n = self.year.year_number
            if self.semester not in (2 * n - 1, 2 * n):
                errors['semester'] = f"Year {n} has semesters {2 * n - 1} and {2 * n}."
        if self.picks is not None and self.picks < 1:
            errors['picks'] = "Students must take at least 1."
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            errors['closes_at'] = "The last date must be after the opening date."
        if errors:
            raise ValidationError(errors)

    # ---- selection window ----
    def window_state(self, now=None):
        """'not_open' | 'open' | 'closed' - blank dates mean no limit on that side."""
        now = now or timezone.now()
        if self.opens_at and now < self.opens_at:
            return 'not_open'
        if self.closes_at and now > self.closes_at:
            return 'closed'
        return 'open'

    def is_open(self, now=None):
        return self.window_state(now) == 'open'

    def __str__(self):
        return f"{self.course} · Year {self.year.year_number} · Sem {self.semester} · {self.name}"


class ElectiveOption(models.Model):
    """One choice in a group: a teaching assignment (subject + teacher) and its seats."""

    group = models.ForeignKey(ElectiveGroup, on_delete=models.CASCADE, related_name='options')
    # a teaching assignment belongs to at most ONE group, so its enrollments
    # (= the students who chose it) can't be counted twice
    teaching_assignment = models.OneToOneField(
        'courses.TeachingAssignment', on_delete=models.CASCADE, related_name='elective_option'
    )
    seat_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = no limit")
    # CBCS PART B - subjects the student must have passed to take this option
    requires = models.ManyToManyField('courses.Subject', blank=True, related_name='required_by_options')

    class Meta:
        ordering = ['teaching_assignment__subject__name']

    def clean(self):
        ta = getattr(self, 'teaching_assignment', None)
        group = getattr(self, 'group', None)
        if ta is None or group is None:
            return
        if not ta.subject.is_elective:
            raise ValidationError(f"{ta.subject.name} is not marked as an elective.")
        if group.open_elective:                               # CBCS PART B: any course, same semester
            if ta.subject.semester != group.semester:
                raise ValidationError(f"{ta.subject.name} is a Semester {ta.subject.semester} subject.")
            return
        if ta.course_id != group.course_id or ta.year_id != group.year_id:
            raise ValidationError(f"{ta.subject.name} is taught to a different class.")
        if ta.subject.semester != group.semester:
            raise ValidationError(f"{ta.subject.name} is a Semester {ta.subject.semester} subject.")

    @property
    def seats_taken(self):
        from core.academics.models import Enrollment
        return Enrollment.objects.filter(teaching_assignment_id=self.teaching_assignment_id).count()

    def __str__(self):
        return f"{self.group.name}: {self.teaching_assignment.subject.name}"


class ElectiveChange(models.Model):
    """History of every pick / move / removal. Never edited or deleted by the app."""

    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='elective_changes')
    group = models.ForeignKey(ElectiveGroup, on_delete=models.CASCADE, related_name='changes')
    from_option = models.ForeignKey(
        ElectiveOption, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    to_option = models.ForeignKey(
        ElectiveOption, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    changed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    reason = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.student} · {self.group.name} · {self.changed_at:%d-%m-%Y}"


# ======================================================================
# CBCS PART A - course registration
#   RegistrationWindow   one registration round for a semester (all or some
#                        courses): dates, credit limits, how seats are given
#   CourseRegistration   one student's registration in a window and where it
#                        is (class in-charge -> HOD -> approved)
#   RegistrationChoice   one ranked choice inside an elective group, and what
#                        the student got after allocation
# The rules live in core/academics/course_registration.py.
# ======================================================================
class RegistrationWindow(models.Model):
    BY_CGPA = "cgpa"
    BY_TIME = "fcfs"
    ALLOCATION_CHOICES = [
        (BY_CGPA, "By CGPA after the window closes"),
        (BY_TIME, "By who submitted first"),
    ]

    name = models.CharField(max_length=60, unique=True)
    semester = models.PositiveSmallIntegerField()
    # blank = every course that has this semester
    courses = models.ManyToManyField('courses.Course', blank=True, related_name='registration_windows')
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()

    min_credits = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    max_credits = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    # students with CGPA >= extra_cgpa may take extra_credits above the maximum
    extra_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    extra_credits = models.DecimalField(max_digits=4, decimal_places=1, default=0)

    allocation = models.CharField(max_length=6, choices=ALLOCATION_CHOICES, default=BY_CGPA)
    max_ranks = models.PositiveSmallIntegerField(default=3)
    hod_approval = models.BooleanField(default=False)
    min_strength = models.PositiveSmallIntegerField(default=15)   # below this an option is flagged

    allocated_at = models.DateTimeField(null=True, blank=True)
    allocated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-opens_at']

    def window_state(self, now=None):
        """'not_open' | 'open' | 'closed' | 'allocated'"""
        if self.allocated_at:
            return 'allocated'
        now = now or timezone.now()
        if now < self.opens_at:
            return 'not_open'
        if now > self.closes_at:
            return 'closed'
        return 'open'

    def __str__(self):
        return self.name


class CourseRegistration(models.Model):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    WITH_HOD = "with_hod"
    APPROVED = "approved"
    RETURNED = "returned"
    STATUS_CHOICES = [
        (DRAFT, "Not submitted"),
        (SUBMITTED, "With class in-charge"),
        (WITH_HOD, "With HOD"),
        (APPROVED, "Approved"),
        (RETURNED, "Returned"),
    ]

    window = models.ForeignKey(RegistrationWindow, on_delete=models.CASCADE, related_name='registrations')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='course_registrations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    credits = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, default="")      # last comment from the approver
    tutor_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='+')
    tutor_at = models.DateTimeField(null=True, blank=True)
    hod_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='+')
    hod_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['window', 'student'], name='one_registration_per_window'),
        ]

    def __str__(self):
        return f"{self.student} · {self.window}"


class RegistrationChoice(models.Model):
    ALLOTTED = "allotted"
    WAITLIST = "waitlist"
    NOT_ALLOTTED = "not_allotted"
    RESULT_CHOICES = [
        ("", "Not decided"),
        (ALLOTTED, "Allotted"),
        (WAITLIST, "Waitlist"),
        (NOT_ALLOTTED, "Not allotted"),
    ]

    registration = models.ForeignKey(CourseRegistration, on_delete=models.CASCADE, related_name='choices')
    group = models.ForeignKey(ElectiveGroup, on_delete=models.CASCADE, related_name='+')
    option = models.ForeignKey(ElectiveOption, on_delete=models.CASCADE, related_name='choices')
    rank = models.PositiveSmallIntegerField()
    result = models.CharField(max_length=12, choices=RESULT_CHOICES, blank=True, default="")
    waitlist_no = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['group_id', 'rank']
        constraints = [
            models.UniqueConstraint(fields=['registration', 'option'], name='one_choice_per_option'),
            models.UniqueConstraint(fields=['registration', 'group', 'rank'], name='one_choice_per_rank'),
        ]
