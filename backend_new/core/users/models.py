from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


# ================= YEAR CHOICES =================
YEAR_CHOICES = (
    (1, "1st Year"),
    (2, "2nd Year"),
    (3, "3rd Year"),
    (4, "4th Year"),
)


# ================= SEMESTER CHOICES =================
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


# ================= DEPARTMENT =================
class Department(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    # ================= SHORT CODE =================
    # Single source of truth for the department's short code (CS, IT, ECE...).
    # Used in roll numbers and, later, in placement branch eligibility.
    # This used to be a dict hardcoded inside User.save() where nothing else
    # could read or validate against it -- which is how EC and EEE ended up
    # inconsistent in live roll numbers.
    # unique + null (not blank-only) so two departments can never share a code,
    # while departments that have not been given one yet stay NULL.
    code = models.CharField(
        max_length=10,
        unique=True,
        null=True,
        blank=True,
    )

    hod = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hod_of',
        limit_choices_to={'role': 'teacher'},
    )

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        # Codes are always stored uppercase so lookups never depend on casing.
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ================= USER =================
class User(AbstractUser):

    # ================= MAIN ROLE =================
    # Top-level category only. The specific level lives in sub_role.
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
        ('non_teaching', 'Non-teaching staff'),
        ('parent', 'Parent'),
    )

    # ================= SUB ROLE =================
    # Blank for students and parents.
    SUB_ROLE_CHOICES = (
        # teacher
        ('assistant_professor', 'Assistant Professor'),
        ('associate_professor', 'Associate Professor'),
        ('professor', 'Professor'),
        # admin
        ('academic_admin', 'Academic Admin'),
        ('exam_admin', 'Examination Admin'),
        ('accounts_admin', 'Accounts Admin'),
        ('iqac_admin', 'IQAC Admin'),
        ('placement_officer', 'Placement Officer'),
        ('super_admin', 'Super Admin'),
        # non-teaching
        ('office_assistant', 'Office Assistant'),
        ('lab_technician', 'Lab Technician'),
        ('librarian', 'Librarian'),
        ('clerk', 'Clerk'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student'
    )

    sub_role = models.CharField(
        max_length=40,
        choices=SUB_ROLE_CHOICES,
        blank=True,
        null=True
    )
    # ================= FORCE PASSWORD CHANGE ON FIRST LOGIN =================
    # Set to True for auto-created parents so they must set a new password.
    must_change_password = models.BooleanField(default=False)

    # ================= DEPARTMENT =================
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # ================= COURSE =================
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # ================= STUDENT ROLL NUMBER =================
    roll_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True
    )

    # ================= STAFF EMPLOYEE ID =================
    employee_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True
    )

    # ================= STUDENT YEAR =================
    year = models.IntegerField(
        choices=YEAR_CHOICES,
        null=True,
        blank=True
    )

    # ================= STUDENT SEMESTER =================
    semester = models.IntegerField(
        choices=SEMESTER_CHOICES,
        null=True,
        blank=True
    )

    # ================= STUDENT BATCH / ADMISSION YEAR =================
    batch_year = models.IntegerField(
        null=True,
        blank=True
    )

    # ================= EMPLOYEE ID PREFIXES (Option A) =================
    EMP_PREFIXES = {
        'teacher': 'TCH',
        'admin': 'ADM',
        'non_teaching': 'STF',
    }

    # ================= SAVE =================
    def save(self, *args, **kwargs):

        # ================= SUPERUSER =================
        if self.is_superuser:
            self.role = "admin"

        # ================= STUDENT ROLL NUMBER =================
        if (
            self.role == "student"
            and not self.roll_number
        ):

            # ================= DEPARTMENT CODE =================
            # Read from Department.code -- one definition, editable in admin.
            # "GN" only when the department is missing or has no code set.
            if self.department and self.department.code:
                dept_code = self.department.code
            else:
                dept_code = "GN"

            # ================= YEAR PREFIX (from batch year) =================
            # batch_year 2021 -> "21". Falls back to current year if not set.
            import datetime
            batch = self.batch_year or datetime.date.today().year
            year_prefix = str(batch)[-2:]

            # ================= FIND LAST STUDENT IN SAME BATCH + DEPT =================
            # counter restarts per (department, batch year)
            last_student = User.objects.filter(
                role="student",
                department=self.department,
                roll_number__startswith=f"{year_prefix}{dept_code}",
            ).order_by('-roll_number').first()

            # ================= COMPUTE NEXT NUMBER =================
            new_number = 1
            if last_student and last_student.roll_number:
                try:
                    new_number = int(last_student.roll_number[-3:]) + 1
                except (ValueError, TypeError):
                    pass

            # ================= FINAL ROLL NUMBER =================
            self.roll_number = f"{year_prefix}{dept_code}{new_number:03d}"

        # ================= STAFF EMPLOYEE ID (TCH / ADM / STF) =================
        prefix = self.EMP_PREFIXES.get(self.role)
        if prefix and not self.employee_id:

            # count only within the same prefix so the series don't collide
            last_staff = User.objects.filter(
                role=self.role,
                employee_id__startswith=prefix,
            ).order_by('-employee_id').first()

            new_number = 1
            if last_staff and last_staff.employee_id:
                try:
                    new_number = int(last_staff.employee_id[-3:]) + 1
                except (ValueError, TypeError):
                    pass

            self.employee_id = f"{prefix}{new_number:03d}"

        super().save(*args, **kwargs)

    # ================= DISPLAY NAME =================
    # The ONE rule for showing a person's name anywhere in the app:
    # full name, falling back to the login name only when no name was entered.
    # Use user.display_name (serializers: source="student.display_name")
    # instead of username, so every screen shows the same name.
    @property
    def display_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username

    # ================= STRING =================
    def __str__(self):
        return self.username


# ================= STUDENT PROFILE =================
class StudentProfile(models.Model):

    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='student_profile',
        limit_choices_to={'role': 'student'},
    )

    # personal
    gender = models.CharField(max_length=10, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    photo = models.ImageField(upload_to='student_photos/', null=True, blank=True)

    # address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    # admission
    admission_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


# ================= PRIOR ACADEMICS (SCHOOL / DIPLOMA) =================
class PriorAcademics(models.Model):
    """
    A student's education BEFORE joining the college -- 10th, 12th, diploma.

    Lives in `users`, not `placement`, on purpose: these are permanent facts
    about the student. They were true before admission and stay true after
    graduation. Placement is simply the first module to need them; admissions,
    IQAC and transcripts will want them too. If the placement app were ever
    removed, this data should survive.

    Percentages are Decimal, never Float. These get compared against company
    cutoffs (>= 60), and float arithmetic can turn 60.0 into 59.999999 and
    silently reject an eligible student.

    Marksheet uploads are deliberately NOT here yet. Add them as nullable
    FileFields if a college asks -- that needs a migration but no backfill.
    """

    PERCENT_VALIDATORS = [
        MinValueValidator(0),
        MaxValueValidator(100),
    ]

    student = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='prior_academics',
        limit_choices_to={'role': 'student'},
    )

    # ---------------- 10th ----------------
    # Every student has a 10th, lateral entry or not.
    tenth_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=PERCENT_VALIDATORS,
    )
    tenth_board = models.CharField(max_length=100, blank=True)   # State Board / CBSE / ICSE
    tenth_year = models.IntegerField(null=True, blank=True)      # year of passing

    # ---------------- LATERAL ENTRY ----------------
    # A lateral entry student joins in 2nd year with a diploma instead of a 12th.
    # This flag decides WHICH qualification the eligibility check reads, so it
    # must never be guessed from whichever field happens to be filled in.
    is_lateral_entry = models.BooleanField(default=False)

    # ---------------- 12th ----------------
    # Blank for lateral entry students.
    twelfth_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=PERCENT_VALIDATORS,
    )
    twelfth_board = models.CharField(max_length=100, blank=True)
    twelfth_year = models.IntegerField(null=True, blank=True)

    # ---------------- DIPLOMA ----------------
    # Blank for regular students.
    diploma_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=PERCENT_VALIDATORS,
    )
    diploma_branch = models.CharField(max_length=150, blank=True)
    diploma_year = models.IntegerField(null=True, blank=True)

    # ---------------- VERIFICATION ----------------
    # Students enter their own marks, so anyone could type 95%. Eligibility
    # treats UNVERIFIED marks as not-yet-eligible -- nobody types their way
    # into a drive. The coordinator's Profile Verification screen sets this.
    verified = models.BooleanField(default=False)

    verified_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prior_academics_verified',
        limit_choices_to={'role': 'teacher'},
    )

    verified_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prior academics"
        verbose_name_plural = "Prior academics"

    # ---------------- VALIDATION ----------------
    def clean(self):
        errors = {}

        if self.is_lateral_entry:
            if self.diploma_percent is None:
                errors['diploma_percent'] = (
                    "Diploma percentage is required for a lateral entry student."
                )
        else:
            if self.twelfth_percent is None:
                errors['twelfth_percent'] = (
                    "12th percentage is required for a regular student."
                )

        if errors:
            raise ValidationError(errors)

    # ---------------- QUALIFYING MARK ----------------
    @property
    def qualifying_percent(self):

        if self.is_lateral_entry:
            return self.diploma_percent
        return self.twelfth_percent

    def __str__(self):
        return f"Prior academics of {self.student.username}"


# ================= FACULTY / STAFF PROFILE =================
# Used for both teachers AND non-teaching staff (both are employees).
class FacultyProfile(models.Model):

    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='faculty_profile',
    )

    # personal
    gender = models.CharField(max_length=10, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    photo = models.ImageField(upload_to='staff_photos/', null=True, blank=True)

    # address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    # employment
    qualification = models.CharField(max_length=255, blank=True)     # M.E., Ph.D.
    specialization = models.CharField(max_length=255, blank=True)    # for teachers
    date_of_joining = models.DateField(null=True, blank=True)
    experience_years = models.PositiveIntegerField(null=True, blank=True)

    # HRIS PART A - job details kept by the office (designation is User.sub_role)
    EMPLOYMENT_CHOICES = [
        ("permanent", "Permanent"), ("probation", "On probation"), ("contract", "Contract"),
        ("visiting", "Visiting / guest"),
    ]
    employment_type = models.CharField(max_length=12, choices=EMPLOYMENT_CHOICES, blank=True, default="")
    aicte_id = models.CharField(max_length=30, blank=True, default="")          # AICTE faculty ID
    relieved_on = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


# ================= PARENT PROFILE =================
class ParentProfile(models.Model):

    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='parent_profile',
        limit_choices_to={'role': 'parent'},
    )

    children = models.ManyToManyField(
        'users.User',
        related_name='parents',
        limit_choices_to={'role': 'student'},
        blank=True,
    )

    # contact details (useful when a parent is auto-created from a student)
    phone = models.CharField(max_length=15, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    relation = models.CharField(max_length=20, blank=True)   # Father / Mother / Guardian

    def __str__(self):
        return self.user.username


# ================= FACULTY PARTICIPATION (IQAC) =================

class FacultyParticipation(models.Model):

    # what kind of activity it was
    CATEGORY_CHOICES = (
        ('fdp', 'FDP / Training Attended'),
        ('workshop_attended', 'Workshop / Seminar Attended'),
        ('workshop_conducted', 'Workshop / Seminar Conducted'),
        ('conference', 'Conference Paper Presented'),
        ('journal', 'Journal Publication'),
        ('certification', 'Certification / MOOC (NPTEL etc.)'),
        ('guest_lecture', 'Guest Lecture Delivered'),
        ('committee', 'Committee / Cell Membership'),
        ('project', 'Project / Grant / Consultancy'),
        ('book', 'Book / Book chapter'),            # HRIS PART B
        ('patent', 'Patent'),                       # HRIS PART B
        ('award', 'Award / Recognition'),           # HRIS PART B
        ('other', 'Other'),
    )

    # the teacher's part in it
    ROLE_CHOICES = (
        ('attended', 'Attended'),
        ('conducted', 'Conducted / Organized'),
        ('presented', 'Presented'),
        ('published', 'Published'),
        ('member', 'Member'),
        ('other', 'Other'),
    )

    faculty = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='participations',
        limit_choices_to={'role': 'teacher'},
    )

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=255)            # e.g. "AI Workshop at IIT Madras"
    organizer = models.CharField(max_length=255, blank=True)   # where / who ran it
    activity_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='attended')

    date = models.DateField()
    academic_year = models.CharField(max_length=9, blank=True)  # e.g. "2025-26"

    # the uploaded proof (certificate / PDF / image)
    proof = models.FileField(upload_to='faculty_proofs/', null=True, blank=True)

    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # HRIS PART B - the HOD verifies; only verified entries count in appraisal and reports
    STATUS_CHOICES = (('pending', 'Waiting for verification'), ('verified', 'Verified'),
                      ('returned', 'Returned for correction'))
    INDEXING_CHOICES = (('scopus', 'Scopus'), ('sci', 'SCI / SCIE'), ('wos', 'Web of Science'),
                        ('ugc_care', 'UGC-CARE'), ('other', 'Other / not indexed'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    details = models.CharField(max_length=300, blank=True, default='')     # journal, volume, DOI, patent no.
    indexing = models.CharField(max_length=10, choices=INDEXING_CHOICES, blank=True, default='')
    amount_lakhs = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)   # funded projects
    verified_by = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='participations_verified')
    verified_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.faculty.username} — {self.get_category_display()} — {self.title}"

    

# ================= ACTING HOD (#50) =================
class ActingHOD(models.Model):
    """
    #50 ACTING HOD: a teacher who holds the HOD's powers for ONE department
    for a date range (both days included). The regular HOD stays in
    Department.hod and is never changed.
    Rows are never deleted. Extend / end early are recorded in ActingHODLog.
    ended_at is set when the admin ends it early: powers stop at that moment.
    """
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='acting_hods',
    )
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='acting_hod_assignments',
        limit_choices_to={'role': 'teacher'},
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255)

    assigned_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acting_hods_assigned',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acting_hods_ended',
    )
    end_reason = models.CharField(max_length=255, blank=True)

    # ---- Step 3b: HOD nomination + main admin approval ----
    # Direct admin assignments are 'approved' at once. A nomination from the
    # HOD's leave form is 'pending' until the main admin decides.
    # Only 'approved' rows ever give HOD powers.
    APPROVAL_CHOICES = (
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
    )
    approval_status = models.CharField(
        max_length=10, choices=APPROVAL_CHOICES, default='approved',
    )
    nominated_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acting_hods_nominated',
    )
    approved_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acting_hods_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acting_hods_rejected',
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=255, blank=True)
    # The StaffLeaveRequest this nomination came from. A plain number, not a
    # ForeignKey, so the core users app does not depend on the attendance module.
    leave_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date', '-id']

    def __str__(self):
        return (f"{self.teacher} acting HOD of {self.department} "
                f"({self.start_date:%d-%m-%Y} to {self.end_date:%d-%m-%Y})")


class ActingHODLog(models.Model):
    """
    #50 ACTING HOD: history of every action on an assignment.
    Never edited or deleted (same audit style as the eligibility override log).
    """
    ACTION_CHOICES = (
        ('assigned', 'Assigned'),
        ('extended', 'Extended'),
        ('ended', 'Ended early / cancelled'),
        ('nominated', 'Nominated by HOD'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    assignment = models.ForeignKey(
        ActingHOD,
        on_delete=models.PROTECT,
        related_name='logs',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    old_end_date = models.DateField(null=True, blank=True)
    new_end_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    done_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acting_hod_actions',
    )
    done_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['done_at', 'id']

    def __str__(self):
        return f"{self.get_action_display()} - {self.assignment}"


# ============================================================================
#  WAVE 2 - PRINCIPAL
#  One teacher at a time is the college Principal. The main admin assigns and
#  ends the term; past terms stay as history. Powers come from the CURRENT row
#  only (is_current=True), never from role/sub_role, so nothing about the
#  teacher's own account changes.
# ============================================================================
class PrincipalTerm(models.Model):
    teacher = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='principal_terms',
        limit_choices_to={'role': 'teacher'},
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    ended_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', '-id']
        constraints = [
            # at most ONE current Principal
            models.UniqueConstraint(
                fields=['is_current'],
                condition=models.Q(is_current=True),
                name='one_current_principal',
            )
        ]

    def __str__(self):
        return f"Principal {self.teacher} from {self.start_date}"


# ======================================================================
# HRIS PART A - service record, staff documents, leave rules and balance
#   ServiceRecord     joining, promotions, transfers, extra roles, relieving
#   StaffDocument     certificates, orders, ID proofs kept with the staff record
#   LeaveRule         how many days of each leave type a year (blank = no limit)
#   LeaveAdjustment   admin corrections: carry forward, compensatory off earned ...
# The rules and API live in core/users/hris.py.
# ======================================================================
class ServiceRecord(models.Model):
    KINDS = [
        ("joined", "Joined"), ("promotion", "Promotion"), ("transfer", "Department change"),
        ("pay", "Pay / level change"), ("role", "Additional role"), ("relieved", "Relieved"),
        ("other", "Other"),
    ]
    staff = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='service_records')
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=KINDS)
    details = models.CharField(max_length=300)
    order_no = models.CharField(max_length=60, blank=True, default="")
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']


class StaffDocument(models.Model):
    KINDS = [
        ("qualification", "Qualification certificate"), ("experience", "Experience certificate"),
        ("order", "Appointment / service order"), ("id_proof", "ID proof"), ("other", "Other"),
    ]
    PRIVATE_KINDS = {"id_proof"}            # seen by the staff member and admin only, never the HOD

    staff = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='staff_documents')
    kind = models.CharField(max_length=14, choices=KINDS)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='staff_documents/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    @property
    def is_private(self):
        return self.kind in self.PRIVATE_KINDS


class LeaveRule(models.Model):
    # the values match StaffLeaveRequest.LeaveType (modules/attendance)
    leave_type = models.CharField(max_length=16, unique=True)
    days_per_year = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)  # blank = no limit
    note = models.CharField(max_length=200, blank=True, default="")
    updated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class LeaveAdjustment(models.Model):
    staff = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='leave_adjustments')
    leave_type = models.CharField(max_length=16)
    year = models.PositiveSmallIntegerField()
    days = models.DecimalField(max_digits=5, decimal_places=1)     # + adds to the allowance, - takes away
    reason = models.CharField(max_length=200)
    by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at']


# ================= HRIS PART B - yearly appraisal =================
DEFAULT_APPRAISAL_AREAS = [
    {"key": "teaching", "label": "Teaching", "max": 30},
    {"key": "results", "label": "Student results and feedback", "max": 20},
    {"key": "research", "label": "Research and development", "max": 25},
    {"key": "department", "label": "Department and college work", "max": 15},
    {"key": "development", "label": "Self-development", "max": 10},
]


def default_appraisal_areas():
    return [dict(a) for a in DEFAULT_APPRAISAL_AREAS]


class AppraisalCycle(models.Model):
    """One appraisal year, e.g. 2025-26 from June to May. The admin opens and closes it."""
    name = models.CharField(max_length=20, unique=True)
    start = models.DateField()
    end = models.DateField()
    areas = models.JSONField(default=default_appraisal_areas)      # [{key, label, max}]
    is_open = models.BooleanField(default=True)
    created_by = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start']

    def __str__(self):
        return f"Appraisal {self.name}"


class Appraisal(models.Model):
    """One teacher's appraisal for one cycle: self -> HOD -> Principal -> done."""
    STATUS_CHOICES = (('draft', 'Being filled in'), ('with_hod', 'With the HOD'),
                      ('with_principal', 'With the Principal'), ('done', 'Finalised'))
    GRADES = (('A+', 'Outstanding'), ('A', 'Very good'), ('B', 'Good'), ('C', 'Average'),
              ('D', 'Needs improvement'))
    cycle = models.ForeignKey(AppraisalCycle, on_delete=models.CASCADE, related_name='appraisals')
    staff = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='appraisals')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    self_scores = models.JSONField(default=dict, blank=True)
    self_summary = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    hod_scores = models.JSONField(default=dict, blank=True)
    hod_remarks = models.TextField(blank=True, default='')
    hod_by = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    hod_at = models.DateTimeField(null=True, blank=True)
    grade = models.CharField(max_length=2, choices=GRADES, blank=True, default='')
    principal_remarks = models.TextField(blank=True, default='')
    principal_by = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    finalised_at = models.DateTimeField(null=True, blank=True)
    returned_note = models.CharField(max_length=300, blank=True, default='')   # why it was sent back
    staff_reply = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['staff__first_name', 'staff__username']
        constraints = [models.UniqueConstraint(fields=['cycle', 'staff'], name='one_appraisal_per_cycle')]

    def __str__(self):
        return f"{self.staff} - {self.cycle.name} ({self.status})"
