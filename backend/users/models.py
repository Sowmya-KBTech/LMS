from django.contrib.auth.models import AbstractUser
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
            DEPT_CODES = {
                "Computer Science": "CS",
                "Information Technology": "IT",
                "Electronics and Communication": "ECE",
                "Electrical and Electronics": "EEE",
                "Mechanical": "ME",
                "Civil": "CE",
                "Chemistry": "CH",
                "Mathematics": "MA",
            }

            if self.department:
                dept_code = DEPT_CODES.get(self.department.name, "GN")
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

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.faculty.username} — {self.get_category_display()} — {self.title}"