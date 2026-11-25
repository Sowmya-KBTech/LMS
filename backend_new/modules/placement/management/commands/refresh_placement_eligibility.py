"""
Nightly safety net for the saved placement eligibility (meeting point 10).

    python manage.py refresh_placement_eligibility

Most changes refresh the table the moment they happen (see signals.py).
This catches anything that slipped past - e.g. a bulk update in the shell,
or students promoted to the next year with a queryset .update().

It already runs every night as the "placement_eligibility" job of
run_daily_jobs (Celery Beat, STEP 8). No separate schedule is needed.
"""
from django.core.management.base import BaseCommand

from modules.placement.eligibility_store import refresh_all


class Command(BaseCommand):
    help = "Re-check placement eligibility for every student and every open job role."

    def handle(self, *args, **options):
        summary = refresh_all()
        self.stdout.write(self.style.SUCCESS(
            f"Placement eligibility refreshed: {summary['students']} students x "
            f"{summary['roles']} roles ({summary['rows']} rows)."
        ))
