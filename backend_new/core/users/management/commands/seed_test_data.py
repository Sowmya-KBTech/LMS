"""
python manage.py seed_test_data --size small      (about 500 students)
python manage.py seed_test_data --size large      (about 5,000 students)
python manage.py seed_test_data --clear           (remove ONLY the test data)

Fills a LOCAL DEVELOPMENT database with realistic test data for
performance testing: departments, courses, years, subjects, teachers,
teaching assignments, students, enrollments, attendance and notifications.

Safety:
  * Runs only when DJANGO_DEBUG=True AND the database name ends with "_dev".
  * Only ADDS records. Every test record is clearly marked:
      usernames start with "test_", departments/courses start with "TEST ".
  * --clear deletes only those marked records, nothing else.
  * Test notifications are marked as already emailed, so the email queue
    never sends mail to fake users.

All test users have the password:  Test@12345
"""
import datetime
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.notifications.models import Notification
from core.users.models import Department
from modules.attendance.models import Attendance

User = get_user_model()

USER_PREFIX = "test_"
NAME_PREFIX = "TEST "
EMAIL_DOMAIN = "kbtech-seed.test"
PASSWORD = "Test@12345"

SIZES = {
    #          students  teachers  attendance days  notifications per student
    "small": dict(students=500, teachers=50, days=20, notes=10),
    "large": dict(students=5000, teachers=300, days=20, notes=10),
}

DEPARTMENTS = [  # (short name, code used in test roll numbers)
    ("CSE", "TCSE"), ("ECE", "TECE"), ("EEE", "TEEE"), ("MECH", "TMEC"), ("IT", "TIT"),
]
SUBJECTS_PER_SEMESTER = 3
BATCH = 5000  # rows per bulk insert


class Command(BaseCommand):
    help = "Seed a LOCAL _dev database with realistic test data (or --clear it)."

    def add_arguments(self, parser):
        parser.add_argument("--size", choices=SIZES.keys(), default="small")
        parser.add_argument("--clear", action="store_true",
                            help="Delete only the test data and stop.")
        parser.add_argument("--seed", type=int, default=42,
                            help="Random seed, so every run creates the same data.")

    # ------------------------------------------------------------------ safety
    def _check_safe(self):
        db_name = connection.settings_dict.get("NAME", "")
        if not settings.DEBUG:
            raise CommandError("Refusing to run: DJANGO_DEBUG is not True. "
                               "This command is for local development only.")
        if not str(db_name).endswith("_dev"):
            raise CommandError(f"Refusing to run: database '{db_name}' does not end with '_dev'. "
                               "Use a local development database only.")
        return db_name

    def handle(self, *args, **opts):
        db_name = self._check_safe()
        self.stdout.write(f"Database : {db_name}")

        if opts["clear"]:
            self._clear()
            return

        if User.objects.filter(username__startswith=USER_PREFIX).exists():
            raise CommandError("Test data already exists. Run with --clear first, "
                               "then seed again.")

        size = SIZES[opts["size"]]
        random.seed(opts["seed"])
        self.stdout.write(f"Size     : {opts['size']} ({size['students']} students, "
                          f"{size['teachers']} teachers)")
        with transaction.atomic():
            self._seed(size)
        self.stdout.write(self.style.SUCCESS("Done. Test password for every test user: " + PASSWORD))

    # ------------------------------------------------------------------- clear
    def _clear(self):
        with transaction.atomic():
            users = User.objects.filter(username__startswith=USER_PREFIX)
            n_users = users.count()
            # Attendance / enrollments / notifications / teaching assignments
            # cascade from the users and courses.
            Department.objects.filter(name__startswith=NAME_PREFIX).update(hod=None)
            users.delete()
            n_courses, _ = Course.objects.filter(name__startswith=NAME_PREFIX).delete()
            n_depts, _ = Department.objects.filter(name__startswith=NAME_PREFIX).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed test data: {n_users} users, plus their courses, subjects, "
            f"enrollments, attendance and notifications."))

    # -------------------------------------------------------------------- seed
    def _seed(self, size):
        today = datetime.date.today()
        now = timezone.now()
        password_hash = make_password(PASSWORD)   # hash once, reuse (fast)

        # 1) Departments, courses, years, subjects
        depts, courses, subjects_by = {}, {}, {}
        for short, code in DEPARTMENTS:
            dept = Department.objects.create(name=f"{NAME_PREFIX}{short}", code=code)
            course = Course.objects.create(name=f"{NAME_PREFIX}B.E {short}")
            depts[short], courses[short] = dept, course
            for year_no in range(1, 5):
                year = Year.objects.create(course=course, year_number=year_no)
                semester = 2 * year_no - 1          # odd semester (Jul-Nov)
                subs = [Subject(name=f"{short} Y{year_no} Subject {i}", code=f"T{code}{year_no}{i}",
                                year=year, semester=semester, credits=3, weekly_hours=4,
                                department=dept)
                        for i in range(1, SUBJECTS_PER_SEMESTER + 1)]
                Subject.objects.bulk_create(subs)
                subjects_by[(short, year_no)] = (year, semester,
                                                 list(Subject.objects.filter(year=year)))
        self.stdout.write(f"  departments/courses : {len(depts)} / {len(courses)}")

        # 2) Teachers (spread across departments)
        teachers = []
        for i in range(1, size["teachers"] + 1):
            short = DEPARTMENTS[(i - 1) % len(DEPARTMENTS)][0]
            teachers.append(User(
                username=f"{USER_PREFIX}tch_{i:04d}", email=f"tch{i:04d}@{EMAIL_DOMAIN}",
                first_name="Teacher", last_name=f"{i:04d}", password=password_hash,
                role="teacher", sub_role="assistant_professor", department=depts[short],
                employee_id=f"TTCH{i:05d}", is_active=True))
        User.objects.bulk_create(teachers, batch_size=BATCH)
        teachers_by_dept = {s: list(User.objects.filter(username__startswith=f"{USER_PREFIX}tch_",
                                                         department=depts[s]))
                            for s, _ in DEPARTMENTS}
        self.stdout.write(f"  teachers            : {size['teachers']}")

        # 3) Teaching assignments (each subject gets one teacher of its department)
        tas, ta_by = [], {}
        for (short, year_no), (year, _sem, subs) in subjects_by.items():
            pool = teachers_by_dept[short]
            for j, sub in enumerate(subs):
                tas.append(TeachingAssignment(teacher=pool[(year_no * 3 + j) % len(pool)],
                                              course=courses[short], year=year, subject=sub))
        TeachingAssignment.objects.bulk_create(tas, batch_size=BATCH)
        for ta in TeachingAssignment.objects.filter(course__name__startswith=NAME_PREFIX) \
                                            .select_related("year", "course"):
            short = ta.course.name.replace(f"{NAME_PREFIX}B.E ", "")
            ta_by.setdefault((short, ta.year.year_number), []).append(ta)
        self.stdout.write(f"  teaching assignments: {len(tas)}")

        # 4) Students (spread across departments and years 1-4)
        students = []
        for i in range(1, size["students"] + 1):
            short, code = DEPARTMENTS[(i - 1) % len(DEPARTMENTS)]
            year_no = ((i - 1) // len(DEPARTMENTS)) % 4 + 1
            batch_year = today.year - year_no + (1 if today.month >= 7 else 0)
            students.append(User(
                username=f"{USER_PREFIX}stu_{i:05d}", email=f"stu{i:05d}@{EMAIL_DOMAIN}",
                first_name="Student", last_name=f"{i:05d}", password=password_hash,
                role="student", department=depts[short], course=courses[short],
                year=year_no, semester=2 * year_no - 1, batch_year=batch_year,
                roll_number=f"T{str(batch_year)[-2:]}{code}{i:05d}", is_active=True))
        User.objects.bulk_create(students, batch_size=BATCH)
        students = list(User.objects.filter(username__startswith=f"{USER_PREFIX}stu_")
                        .select_related("department"))
        self.stdout.write(f"  students            : {len(students)}")

        # 5) Enrollments (each student in their year's subjects)
        enrollments = []
        dept_of = {d.id: s for s, d in depts.items()}
        for st in students:
            for ta in ta_by[(dept_of[st.department_id], st.year)]:
                enrollments.append(Enrollment(student=st, teaching_assignment=ta))
        Enrollment.objects.bulk_create(enrollments, batch_size=BATCH)
        self.stdout.write(f"  enrollments         : {len(enrollments)}")

        # 6) Attendance: last N weekdays, 1 hour per subject per day, ~85% present
        days, d = [], today
        while len(days) < size["days"]:
            d -= datetime.timedelta(days=1)
            if d.weekday() < 5:
                days.append(d)
        rows, total = [], 0
        for en in enrollments:
            ta = en.teaching_assignment
            for day in days:
                rows.append(Attendance(teaching_assignment=ta, student=en.student, date=day, hour=1,
                                       status="present" if random.random() < 0.85 else "absent",
                                       marked_by=ta.teacher, created_at=now))
                if len(rows) >= BATCH:
                    Attendance.objects.bulk_create(rows); total += len(rows); rows = []
        if rows:
            Attendance.objects.bulk_create(rows); total += len(rows)
        self.stdout.write(f"  attendance rows     : {total}")

        # 7) Notifications: N per student, half unread, already marked as emailed
        types = ["assignment", "announcement", "marks", "material", "quiz"]
        notes, total = [], 0
        for st in students:
            for k in range(size["notes"]):
                notes.append(Notification(
                    recipient=st, title=f"Test notification {k + 1}",
                    message="Seeded test notification for performance testing.",
                    notification_type=types[k % len(types)], is_read=(k % 2 == 1),
                    created_at=now - datetime.timedelta(hours=k), emailed_at=now))
                if len(notes) >= BATCH:
                    Notification.objects.bulk_create(notes); total += len(notes); notes = []
        if notes:
            Notification.objects.bulk_create(notes); total += len(notes)
        self.stdout.write(f"  notifications       : {total} (half unread)")