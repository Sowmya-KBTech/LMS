"""
Read-only audit. Answers two questions against the live database:

  1. Which students are missing Enrollment rows for their CURRENT class?
     Those students show up as "No audience" in every subject group, and
     silently stop receiving assignments, quizzes and materials.

  2. Which classes have students but no class advisor (YearTutor)?
     Those have no class group for the teacher, and (before the fix) an
     ownerless one for the student.

Nothing is written. Add --fix to backfill the missing enrollments.

    python manage.py audit_groups
    python manage.py audit_groups --fix
"""
from django.core.management.base import BaseCommand

from courses.models import Enrollment, TeachingAssignment, Year, YearTutor
from users.models import User


class Command(BaseCommand):
    help = "Audit enrollment gaps and advisor-less classes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix", action="store_true",
            help="Backfill the missing enrollments (add-only, keeps old rows).",
        )

    def handle(self, *args, **opts):
        # ---------- 1. enrollment gaps ----------
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n1. Students missing enrollments for their current class"))

        broken = []
        for s in User.objects.filter(role="student", is_active=True).select_related("course"):
            if not (s.course_id and s.year and s.semester):
                continue
            expected = TeachingAssignment.objects.filter(
                course_id=s.course_id,
                year__year_number=s.year,
                subject__semester=s.semester,
            ).exclude(subject__is_elective=True)
            expected_count = expected.count()
            if not expected_count:
                continue
            have = Enrollment.objects.filter(
                student=s, teaching_assignment__in=expected).count()
            if have < expected_count:
                broken.append((s, expected_count, have))

        if not broken:
            self.stdout.write(self.style.SUCCESS("   None. Every student is enrolled."))
        else:
            for s, exp, have in broken:
                self.stdout.write(
                    f"   {s.roll_number or s.username:<14} "
                    f"{(s.course.name if s.course else '-'):<18} "
                    f"Y{s.year} S{s.semester}   "
                    f"{have}/{exp} subjects  "
                    + self.style.WARNING(f"missing {exp - have}")
                )
            self.stdout.write(self.style.WARNING(
                f"   {len(broken)} student(s) affected."))

        # ---------- 2. classes with no advisor ----------
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n2. Classes with students but no class advisor"))

        orphans = []
        for y in Year.objects.select_related("course"):
            students = User.objects.filter(
                role="student", is_active=True,
                course_id=y.course_id, year=y.year_number).count()
            if students and not YearTutor.objects.filter(year=y).exists():
                orphans.append((y, students))

        if not orphans:
            self.stdout.write(self.style.SUCCESS("   None. Every class has an advisor."))
        else:
            for y, n in orphans:
                self.stdout.write(
                    f"   {y.course.name} Year {y.year_number}   "
                    f"{n} student(s)   " + self.style.WARNING("no YearTutor"))

        # ---------- 3. optional backfill ----------
        if opts["fix"] and broken:
            from courses.services import enroll_student
            self.stdout.write(self.style.MIGRATE_HEADING("\n3. Backfilling"))
            total = 0
            for s, _, _ in broken:
                total += enroll_student(s)
            self.stdout.write(self.style.SUCCESS(
                f"   Created {total} enrollment row(s) for {len(broken)} student(s)."))
        elif broken:
            self.stdout.write(
                "\n   Re-run with --fix to backfill these. Add-only: nothing is deleted.")