"""
ATTENDANCE WINDOW (#46, proposed enhancement)

Two separate rules, both counted in WORKING days (Saturday, Sunday and
calendar holidays are skipped):

  1. LATE ENTRY - a period can be marked for the first time up to
     LATE_ENTRY_DAYS working days after the class date. After that the
     subject teacher can't enter it; the class tutor does, with a reason.

  2. CORRECTION WINDOW - starts when the period is FIRST SAVED and lasts
     WINDOW_DAYS working days. On the first-save day changes are free; on
     the later window days (Part 2) a reason is needed. After the window
     the period is locked and only the class tutor corrects it.

Example: class Mon 02-11, first marked Wed 04-11
  late-entry deadline  = 05-11 (03, 04, 05)
  can change until     = 09-11 (05, 06, 09 - Sat/Sun skipped)
  locked from          = 10-11
"""
import datetime

from django.utils import timezone

WINDOW_DAYS = 3          # correction window, from the first save
LATE_ENTRY_DAYS = 3      # first entry allowed up to this many working days after the class


def _holidays():
    days = set()
    try:
        from core.academics.holidays import holiday_map
        days |= set(holiday_map().keys())
    except Exception:
        pass
    try:
        from modules.timetable.models import Holiday
        days |= set(Holiday.objects.values_list("date", flat=True))
    except Exception:
        pass
    return days


def is_working_day(d, holidays=None):
    holidays = _holidays() if holidays is None else holidays
    return d.weekday() < 5 and d not in holidays


def add_working_days(start, n, holidays=None):
    """The date that is n working days after `start` (start itself not counted)."""
    holidays = _holidays() if holidays is None else holidays
    d = start
    left = n
    while left > 0:
        d += datetime.timedelta(days=1)
        if is_working_day(d, holidays):
            left -= 1
    return d


def late_entry_deadline(class_date, holidays=None):
    """Last day the subject teacher may FIRST mark this class."""
    return add_working_days(class_date, LATE_ENTRY_DAYS, holidays)


def edit_until(first_saved_date, holidays=None):
    """Last day the subject teacher may still change this period."""
    return add_working_days(first_saved_date, WINDOW_DAYS, holidays)


def session_status(ta, day, hour, today=None):
    """
    The state of one register (teaching assignment + date + period):
      not_marked   - can be marked now (within the late-entry deadline)
      late_closed  - never marked and the late-entry deadline has passed
      open_free    - marked; today is the first-save day, changes are free
      open_reason  - marked; inside the correction window (reason - Part 2)
      locked       - marked; the window is over
    """
    from .models import Attendance

    today = today or timezone.localdate()
    holidays = _holidays()
    first = (Attendance.objects
             .filter(teaching_assignment=ta, date=day, hour=hour)
             .order_by("created_at")
             .values_list("created_at", flat=True)
             .first())
    late = late_entry_deadline(day, holidays)

    if first is None:
        state = "not_marked" if today <= late else "late_closed"
        return {"state": state, "late_entry_deadline": late,
                "first_saved": None, "edit_until": None, "lock": None}

    first_day = timezone.localdate(first)
    until = edit_until(first_day, holidays)

    # #46 Part 3: a manual lock (or a tutor's late entry) closes it at once
    from .models import AttendanceLock
    lock = (AttendanceLock.objects.select_related("locked_by")
            .filter(teaching_assignment=ta, date=day, hour=hour).first())
    if lock:
        who = lock.locked_by
        return {"state": "locked", "late_entry_deadline": late,
                "first_saved": first_day, "edit_until": until,
                "lock": {"kind": lock.kind,
                         "by": ((who.get_full_name() or "").strip() or who.username) if who else None,
                         "at": lock.locked_at}}

    if today <= first_day:
        state = "open_free"
    elif today <= until:
        state = "open_reason"
    else:
        state = "locked"
    return {"state": state, "late_entry_deadline": late,
            "first_saved": first_day, "edit_until": until, "lock": None}
