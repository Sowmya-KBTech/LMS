from django.contrib import admin

from .models import TimeSlot, TimetableEntry


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("period_no", "start_time", "end_time", "label", "is_break")
    ordering = ("period_no",)


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ("day_of_week", "time_slot", "assignment")
    list_filter = ("day_of_week",)