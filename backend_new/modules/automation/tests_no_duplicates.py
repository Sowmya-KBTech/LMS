"""Step 8.3 - every scheduled job runs from ONE place only (no double emails)."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from modules.automation.jobs import JOBS

BACKEND = Path(settings.BASE_DIR)


class OneScheduleOnlyTests(SimpleTestCase):

    def test_assignment_reminder_runs_inside_the_nightly_jobs(self):
        when = {name: w for name, _fn, w in JOBS}
        self.assertEqual(when.get("assignment_due"), "daily")
        self.assertEqual(when.get("placement_eligibility"), "daily")

    def test_old_separate_reminder_file_is_gone(self):
        self.assertFalse((BACKEND / "run_reminders.bat").exists())

    def test_beat_has_no_separate_reminder_entry(self):
        tasks = sorted(e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values())
        self.assertEqual(tasks, ["automation.heartbeat", "automation.run_daily_jobs",
                                 "notifications.send_email_queue"])

    def test_remaining_bat_files_warn_not_to_run_with_beat(self):
        for name in ("run_daily_jobs.bat", "run_email_queue.bat"):
            text = (BACKEND / name).read_text(encoding="utf-8", errors="ignore")
            self.assertIn("REPLACED BY CELERY BEAT", text, name)