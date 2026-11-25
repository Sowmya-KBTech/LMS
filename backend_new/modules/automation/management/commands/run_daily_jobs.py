"""
AUTOMATION (Point 12, step 4): the nightly job runner.

    python manage.py run_daily_jobs              run every job due today
    python manage.py run_daily_jobs --dry-run    show what would happen, send nothing
    python manage.py run_daily_jobs --only email_queue
    python manage.py run_daily_jobs --list       list the jobs and when they run

Started nightly at 12:15 AM by Celery Beat (STEP 8.1, CELERY_BEAT_SCHEDULE).
Each job runs on its own: if one fails, it is logged and the rest still run.
Every run writes one JobRun row per job (the job diary).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.db_locks import advisory_lock
from modules.automation.jobs import JOBS, JobContext, describe_when, due_today
from modules.automation.models import JobRun


class Command(BaseCommand):
    help = "Run the scheduled background jobs (fees, attendance, reminders, email queue)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would be sent; write and send nothing.")
        parser.add_argument("--only", help="Run just this one job (by name).")
        parser.add_argument("--list", action="store_true", help="List the jobs and stop.")

    def handle(self, *args, **opts):
        if opts["list"]:
            for name, _fn, when in JOBS:
                self.stdout.write(f"{name:<20} {describe_when(when)}")
            return

        # STEP 8.2: never two nightly runs at once (Beat + a manual run, or a
        # slow run still going): the reminders would go out twice.
        if opts["dry_run"]:
            return self._run(opts)
        with advisory_lock("daily_jobs") as got:
            if not got:
                self.stdout.write("Another run_daily_jobs is still running; skipped.")
                return
            return self._run(opts)

    def _run(self, opts):
        dry = opts["dry_run"]
        only = opts.get("only")
        names = [n for n, _f, _w in JOBS]
        if only and only not in names:
            self.stderr.write(f"Unknown job '{only}'. Jobs: {', '.join(names)}")
            return

        ctx = JobContext(dry_run=dry, out=self.stdout.write)
        self.stdout.write(
            f"run_daily_jobs {ctx.today:%d-%m-%Y}" + (" (dry run - nothing sent)" if dry else "")
        )

        ok = failed = 0
        for name, fn, when in JOBS:
            if only and name != only:
                continue
            if not only and not due_today(when, ctx.today):
                self.stdout.write(f"- {name}: not due today ({describe_when(when)})")
                continue

            run = JobRun.objects.create(job=name, dry_run=dry)
            self.stdout.write(f"- {name}")
            try:
                count = fn(ctx) or 0
                run.status, run.sent_count = "ok", count
                ok += 1
                self.stdout.write(f"  ok ({count} sent)")
            except Exception as exc:          # one failing job never stops the others
                run.status, run.message = "failed", f"{type(exc).__name__}: {exc}"
                failed += 1
                self.stdout.write(self.style.ERROR(f"  FAILED: {run.message}"))
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "sent_count", "message", "finished_at"])

        style = self.style.SUCCESS if not failed else self.style.WARNING
        self.stdout.write(style(f"Done: {ok} ok, {failed} failed."))
