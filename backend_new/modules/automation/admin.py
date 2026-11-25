from django.contrib import admin

from .models import AutomationSetting, BackgroundJob, JobRun, ReminderLog


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = ("job", "started_at", "finished_at", "status", "sent_count", "dry_run")
    list_filter = ("job", "status", "dry_run")


@admin.register(AutomationSetting)
class AutomationSettingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fee_reminders_on", "fee_remind_days_before", "fee_grace_days",
                    "attendance_alerts_on", "attendance_alert_weekday", "updated_at")


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("job", "item_key", "stage", "recipient", "sent_at")
    list_filter = ("job", "stage")


# STEP 6.2
@admin.register(BackgroundJob)
class BackgroundJobAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "lock_key", "created_by", "created_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("id", "created_at", "started_at", "finished_at")