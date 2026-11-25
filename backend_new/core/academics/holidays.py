"""
core/academics/holidays.py   (moved here from events/holidays.py)

The single source of holiday dates for the whole system.

Holidays live in the academic calendar (events.CalendarEvent, event_type
'holiday'). Exams, teaching plans, and the timetable all read them from HERE —
never from their own copy — so a holiday entered once in the calendar is seen
everywhere, and the Google-synced national holidays count too.

A CalendarEvent holiday may span several days (start_date .. end_date). Both
helpers expand that range, so a week-long break blocks every day in it, not
just the first.

This helper lives in CORE so exams, teaching plan and timetable can use it
without needing the Events module. Holidays are still stored in the Events
calendar - if Events is switched off for a college, there are no holidays
(every date counts as a working day).
"""

import datetime

from django.apps import apps


def _holiday_events():
    """Every calendar entry that marks a holiday / leave."""
    if not apps.is_installed("modules.events"):
        return []
    CalendarEvent = apps.get_model("events", "CalendarEvent")
    return CalendarEvent.objects.filter(event_type="holiday")


def _expand(ev):
    """Yield each date a single holiday event covers (inclusive range)."""
    start = ev.start_date
    end = ev.end_date or ev.start_date
    if not start:
        return
    # guard against a bad row where end < start
    if end < start:
        start, end = end, start
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)

def holiday_map():
    """
    FIX #27: {date: name} for every holiday day in the calendar.
    Used by the /holidays/ API and by attendance, so a holiday added in the
    Calendar blocks classes and attendance on that day.
    """
    out = {}
    for ev in _holiday_events():
        for d in _expand(ev):
            out.setdefault(d, ev.title)
    return out

def holiday_dates():
    """
    A set of every date that is a holiday.

    Drop-in replacement for the old
        set(Holiday.objects.values_list("date", flat=True))
    """
    out = set()
    for ev in _holiday_events():
        out.update(_expand(ev))
    return out


def holiday_map():
    """
    {date: name} for every holiday date — for places that show the holiday's
    name, not just skip the day. Name comes from CalendarEvent.title.

    If two holidays overlap on a date, the first by start_date wins (the
    queryset is ordered by start_date via the model's Meta.ordering).
    """
    out = {}
    for ev in _holiday_events():
        label = ev.title or "Holiday"
        for d in _expand(ev):
            out.setdefault(d, label)
    return out