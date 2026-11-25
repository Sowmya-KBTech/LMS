from django.apps import AppConfig


class AutomationConfig(AppConfig):
    """
    AUTOMATION (Point 12, step 4): the nightly job runner.
    One command, run_daily_jobs, runs every scheduled job in order and keeps a
    JobRun diary plus a ReminderLog so nobody gets the same reminder twice.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.automation"
    label = "automation"
    verbose_name = "Automation (background jobs)"
