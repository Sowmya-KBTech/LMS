"""
AUTOMATION (Point 12, step 4)

JobRun       one row per job per run: when, how it ended, how many sent
ReminderLog  one row per reminder actually sent; the unique key stops the
             same reminder (job + item + person + stage) being sent twice
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class JobRun(models.Model):
    STATUS = [
        ("running", "Running"),
        ("ok", "OK"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    job = models.CharField(max_length=60)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="running")
    sent_count = models.PositiveIntegerField(default=0)
    dry_run = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Job run"

    def __str__(self):
        return f"{self.job} {self.started_at:%d-%m-%Y %H:%M} {self.status}"


class ReminderLog(models.Model):
    job = models.CharField(max_length=60)
    item_key = models.CharField(max_length=80)      # e.g. "fee:42"
    stage = models.CharField(max_length=40)         # e.g. "due_in_3_days"
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Reminder sent"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "item_key", "stage", "recipient"],
                name="unique_reminder_per_stage",
            )
        ]

    def __str__(self):
        return f"{self.job} {self.item_key} {self.stage} -> {self.recipient}"


class AutomationSetting(models.Model):
    """
    AUTOMATION SETTINGS (Point 12, step 5): one row for the whole college.
    Editable in Django admin now; an admin screen comes in step 8.
    """
    fee_reminders_on = models.BooleanField(default=True)
    fee_remind_days_before = models.PositiveSmallIntegerField(
        default=3, help_text="Remind this many days before the fee due date.")
    fee_grace_days = models.PositiveSmallIntegerField(
        default=7, help_text="Days after the due date before the grace period ends.")
    # Point 12, step 6: weekly low-attendance alert
    WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
                (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    attendance_alerts_on = models.BooleanField(default=True)
    attendance_alert_weekday = models.PositiveSmallIntegerField(
        default=0, choices=WEEKDAYS,
        help_text="Day of the week the low-attendance alert is sent.")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Automation settings"
        verbose_name_plural = "Automation settings"

    def __str__(self):
        return (f"Fees: remind {self.fee_remind_days_before} days before, "
                f"grace {self.fee_grace_days} days"
                + ("" if self.fee_reminders_on else " (off)"))

    @classmethod
    def current(cls):
        obj = cls.objects.order_by("id").first()
        return obj or cls.objects.create()



# =====================================================================
#  STEP 6.2: jobs started by a user and run by the Celery worker
#  (first user: timetable auto-fill). JobRun above stays the diary of
#  the nightly jobs.
# =====================================================================
class BackgroundJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    ACTIVE = (Status.QUEUED, Status.RUNNING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=40)                 # e.g. "timetable_autofill"
    college = models.CharField(max_length=40)              # ready for one database per college
    # Jobs with the same lock_key may not run at the same time,
    # e.g. "timetable:<year>:<semester>". Empty = no limit.
    lock_key = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.QUEUED, db_index=True)
    params = models.JSONField(default=dict, blank=True)    # what was asked
    result = models.JSONField(null=True, blank=True)       # what came out
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Background job"
        constraints = [
            # The DATABASE refuses a second active job for the same lock_key,
            # even if Redis is down or two clicks arrive at the same moment.
            models.UniqueConstraint(
                fields=["lock_key"],
                condition=Q(status__in=["queued", "running"]) & ~Q(lock_key=""),
                name="one_active_job_per_lock",
            )
        ]

    def __str__(self):
        return f"{self.kind} {self.status} ({self.id})"