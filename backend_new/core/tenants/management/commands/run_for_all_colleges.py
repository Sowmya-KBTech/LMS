"""
python manage.py run_for_all_colleges <command> [its options]

SAAS PHASE 1 - nightly and scheduled jobs run once PER COLLEGE.

A job started from Task Scheduler has no web address, so it does not know
which college to work on. This runs the given management command inside each
active college's schema in turn (the platform's public schema is skipped: it
has no college tables). One college failing does not stop the others.

    python manage.py run_for_all_colleges run_daily_jobs
    python manage.py run_for_all_colleges run_daily_jobs --dry-run
    python manage.py run_for_all_colleges send_notification_emails
    python manage.py run_for_all_colleges run_daily_jobs --only-college abc
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College


class Command(BaseCommand):
    help = "Run a management command once inside every active college."

    def add_arguments(self, parser):
        parser.add_argument("command_name", help="the command to run, e.g. run_daily_jobs")
        parser.add_argument("--only-college", dest="only", help="run for this college code only")

    def run_from_argv(self, argv):
        # everything after the command name belongs to that command
        # (e.g. --dry-run for run_daily_jobs), except our own --only-college
        self._passthrough = []
        own, rest = argv[:3], argv[3:]
        while rest:
            arg = rest.pop(0)
            if arg == "--only-college" and rest:
                own += [arg, rest.pop(0)]
            elif arg.startswith("--only-college="):
                own.append(arg)
            else:
                self._passthrough.append(arg)
        return super().run_from_argv(own)

    def handle(self, *args, **opts):
        passthrough = getattr(self, "_passthrough", [])
        colleges = (College.objects.exclude(schema_name=get_public_schema_name())
                    .filter(is_active=True).order_by("id"))
        if opts["only"]:
            colleges = colleges.filter(schema_name=opts["only"].lower())
            if not colleges.exists():
                raise CommandError(f"No active college with code '{opts['only']}'.")

        ok, failed = 0, 0
        for college in colleges:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"=== {college.name} (schema {college.schema_name}) ==="))
            try:
                with schema_context(college.schema_name):
                    call_command(opts["command_name"], *passthrough,
                                 stdout=self.stdout, stderr=self.stderr)
                ok += 1
            except Exception as exc:            # one college must not stop the rest
                failed += 1
                self.stderr.write(self.style.ERROR(f"  FAILED for {college.schema_name}: {exc}"))

        summary = f"Ran '{opts['command_name']}' for {ok + failed} college(s): {ok} ok, {failed} failed."
        self.stdout.write(self.style.SUCCESS(summary) if not failed else self.style.ERROR(summary))
