"""
Send notification emails that have not gone out yet.

Run it from Windows Task Scheduler alongside remind_due_assignments:

    python manage.py send_notification_emails

Every run takes the pending queue in batches over ONE SMTP connection. The
work used to happen inline in whichever request created the Notification,
which meant a bulk operation like generate_exam_fees did one authenticated
Gmail connection per student before it could return.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.db_locks import advisory_lock

from core.notifications.emails import send_notification_batch
from core.notifications.models import Notification

# How many attempts before a row is given up on. A permanently bad address
# would otherwise be retried on every run, for ever.
MAX_ATTEMPTS = 3


class Command(BaseCommand):
    help = "Send notification emails that are still pending."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=50,
            help="How many to send per connection (default 50).",
        )
        parser.add_argument(
            "--limit", type=int, default=500,
            help="Most to send in one run (default 500).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be sent without sending or writing anything.",
        )

    def handle(self, *args, **options):
        # STEP 8.2: never two senders at once (the 10-minute run, the nightly
        # runner's email step, a manual run). Otherwise the same pending emails
        # could be sent twice before either run marks them as sent.
        if options["dry_run"]:
            return self._send(**options)
        with advisory_lock("email_queue") as got:
            if not got:
                self.stdout.write("Another email run is still sending; skipped.")
                return
            return self._send(**options)

    def _send(self, **options):
        batch_size = options["batch_size"]
        limit = options["limit"]
        dry_run = options["dry_run"]

        pending = (
            Notification.objects
            .filter(emailed_at__isnull=True, email_attempts__lt=MAX_ATTEMPTS)
            .select_related("recipient")
            .order_by("id")[:limit]
        )
        pending = list(pending)

        if not pending:
            self.stdout.write("Nothing pending.")
            return

        if dry_run:
            self.stdout.write(f"{len(pending)} pending. Nothing sent (--dry-run).")
            for n in pending[:20]:
                address = (getattr(n.recipient, "email", "") or "").strip()
                self.stdout.write(
                    f"  {n.id} | {n.recipient} | {address or '(no email)'} | {n.title}"
                )
            if len(pending) > 20:
                self.stdout.write(f"  … and {len(pending) - 20} more")
            return

        total_sent = total_skipped = total_failed = 0

        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            sent, skipped, failed = send_notification_batch(batch)

            now = timezone.now()

            # Sent and skipped are both finished: one went out, the other has
            # no address to go to and would fail identically for ever.
            done_ids = sent + skipped
            if done_ids:
                Notification.objects.filter(id__in=done_ids).update(emailed_at=now)

            # Failed rows stay pending, with the attempt counted so a
            # permanently broken address eventually stops being retried.
            if failed:
                for n in Notification.objects.filter(id__in=failed):
                    n.email_attempts = (n.email_attempts or 0) + 1
                    n.save(update_fields=["email_attempts"])

            total_sent += len(sent)
            total_skipped += len(skipped)
            total_failed += len(failed)

        self.stdout.write(
            self.style.SUCCESS(
                f"sent {total_sent} · skipped {total_skipped} (no address) · "
                f"failed {total_failed}"
            )
        )

        if total_failed:
            self.stdout.write(
                f"Failed rows stay pending and are retried next run, "
                f"up to {MAX_ATTEMPTS} attempts."
            )