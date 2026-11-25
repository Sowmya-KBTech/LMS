"""
Emails students who have assignment(s) due within the next 24 hours
that they have not yet submitted.

Each student receives ONE email listing all their due-soon assignments,
not one email per assignment. This keeps volume under Gmail limits and
avoids sending the same person several separate reminders.

Run manually:      python manage.py remind_due_assignments
Dry run (no send): python manage.py remind_due_assignments --dry-run

STEP 8.3: runs every night as the "assignment_due" job of run_daily_jobs
(started by Celery Beat). Do NOT schedule it separately as well: it has no
"already sent" check, so students would get the same email twice.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from modules.learning.models import Assignment, Submission
from core.academics.models import Enrollment
from core.notifications.emails import send_notification_email


class Command(BaseCommand):
    help = "Email students about assignments due within the next 24 hours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print who would be emailed, but do not send anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        window_end = now + timedelta(hours=24)

        # Assignments due in the next 24h, with a real due date.
        due_soon = Assignment.objects.filter(
            due_date__isnull=False,
            due_date__gte=now,
            due_date__lte=window_end,
        )

        # Build a per-student list of their due-soon, unsubmitted assignments.
        # Keyed by student id -> {"student": user, "items": [text, ...]}
        per_student = {}

        for assignment in due_soon:
            enrollments = Enrollment.objects.filter(
                teaching_assignment=assignment.teaching_assignment
            ).select_related("student")

            submitted_ids = set(
                Submission.objects.filter(
                    assignment=assignment
                ).values_list("student_id", flat=True)
            )

            due_text = assignment.due_date.strftime("%d %b %Y, %I:%M %p")
            subject_name = assignment.teaching_assignment.subject.name
            line = f"- '{assignment.title}' ({subject_name}) due {due_text}"

            for enr in enrollments:
                student = enr.student
                if student.id in submitted_ids:
                    continue
                bucket = per_student.setdefault(
                    student.id, {"student": student, "items": []}
                )
                bucket["items"].append(line)

        sent = 0
        skipped_no_email = 0

        for entry in per_student.values():
            student = entry["student"]
            items = entry["items"]

            count = len(items)
            title = "You have assignment(s) due soon"
            message = (
                f"Hello {student.username},\n\n"
                f"You have {count} assignment(s) due within the next 24 hours "
                f"that you have not submitted yet:\n\n"
                + "\n".join(items)
                + "\n\nPlease log in to submit before the deadline."
            )

            if dry_run:
                self.stdout.write(
                    f"WOULD EMAIL {student.email or '(no email)'} "
                    f"-> {count} assignment(s)"
                )
                continue

            ok = send_notification_email(student, title, message)
            if ok:
                sent += 1
            else:
                skipped_no_email += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"Dry run complete. {len(per_student)} student(s) would be emailed. "
                f"Nothing sent."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. Sent {sent} email(s), "
                f"skipped {skipped_no_email} (no email address)."
            ))
