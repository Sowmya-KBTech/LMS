"""
Clear the shared caches when timetable data changes (Step 5).
See config/shared_cache.py.
"""
from django.apps import apps
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from config.shared_cache import invalidate_shared
from modules.timetable.models import Holiday, Semester, TimeSlot


@receiver([post_save, post_delete], sender=TimeSlot)
def clear_timeslots_cache(sender, **kwargs):
    invalidate_shared("timeslots")


@receiver([post_save, post_delete], sender=Semester)
def clear_semester_cache(sender, **kwargs):
    invalidate_shared("semester")


# Step 5.3: /api/holidays/ joins two tables:
#   1. timetable.Holiday
#   2. events.CalendarEvent (event_type="holiday", incl. Google-synced ones)
# A change in either one clears the cache. Any CalendarEvent change clears it,
# because an event can be switched to or from "holiday".
@receiver([post_save, post_delete], sender=Holiday)
def clear_holidays_cache(sender, **kwargs):
    invalidate_shared("holidays")


if apps.is_installed("modules.events"):
    from modules.events.models import CalendarEvent

    @receiver([post_save, post_delete], sender=CalendarEvent)
    def clear_holidays_cache_on_calendar_change(sender, **kwargs):
        invalidate_shared("holidays")