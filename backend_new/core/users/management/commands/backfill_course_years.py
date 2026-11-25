"""
Fill in missing Year rows so every course has a full set of years.

Several courses currently have only 1 (or 0) Year rows configured. That
breaks anything derived from course duration -- passing year comes out
too early, and years 2/3/4 cannot hold subjects, teaching assignments
or tutors at all.

Preview first (changes nothing):
    python manage.py backfill_course_years --dry-run

Then apply:
    python manage.py backfill_course_years

Default duration is 4 years. Override for a different programme length:
    python manage.py backfill_course_years --years 3

Existing Year rows are never touched or renumbered -- only missing ones
are added. Safe to run more than once.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.academics.models import Course, Year


class Command(BaseCommand):
    help = "Create any missing Year rows so each course has a full set."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without saving anything.",
        )
        parser.add_argument(
            "--years",
            type=int,
            default=4,
            help="How many years each course should have. Default 4.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        target_years = options["years"]

        if target_years < 1:
            self.stdout.write(self.style.ERROR("--years must be at least 1."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN -- nothing will be saved.\n"))

        courses = Course.objects.all().order_by("name")

        if not courses.exists():
            self.stdout.write(self.style.WARNING("No courses found."))
            return

        to_create = []
        extra_years = []

        for course in courses:
            existing = set(
                course.years.values_list("year_number", flat=True)
            )
            missing = [n for n in range(1, target_years + 1) if n not in existing]

            # A course with years beyond the target is left alone and flagged,
            # rather than silently deleted.
            beyond = sorted(n for n in existing if n > target_years)
            if beyond:
                extra_years.append((course.name, beyond))

            if missing:
                self.stdout.write(
                    f"   {course.name}: has {sorted(existing) or 'none'} "
                    f"-> adding {missing}"
                )
                for year_number in missing:
                    to_create.append(Year(course=course, year_number=year_number))
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"   {course.name}: already complete")
                )

        self.stdout.write(f"\nYear rows to create: {len(to_create)}")

        for name, beyond in extra_years:
            self.stdout.write(
                self.style.WARNING(
                    f"   note: {name} also has year(s) {beyond} beyond {target_years} "
                    f"-- left untouched"
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run complete. Nothing saved."))
            return

        if not to_create:
            self.stdout.write(self.style.SUCCESS("\nNothing to create."))
            return

        with transaction.atomic():
            Year.objects.bulk_create(to_create)

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Created {len(to_create)} Year rows.")
        )

        # Confirm the end state so the result is visible without a second command.
        self.stdout.write("\nCourse durations now:")
        for course in Course.objects.all().order_by("name"):
            self.stdout.write(f"   {course.name}: {course.years.count()} years")