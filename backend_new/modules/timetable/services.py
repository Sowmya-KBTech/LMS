from django.db.models import Q

from .models import TimeSlot, TimetableEntry, TimetableApproval
from datetime import timedelta
from django.utils import timezone

HOLD_HOURS = 48   # a draft holds its slots for 48h of inactivity


# A timetable only blocks other departments once it has been submitted.
# A half-built draft that nobody submits must never lock the whole college.
BLOCKING_STATUSES = [
    TimetableApproval.Status.SUBMITTED,
    TimetableApproval.Status.APPROVED,
]

# Mon .. Fri  (matches TimetableEntry.DAY_CHOICES)
# Saturday was removed from DAY_CHOICES. range(6) here kept offering
# Saturday cells as "free" and as "Move to" suggestions that can't be saved.
DAYS = range(5)


def class_q(year_id, semester):
    """
    Every entry belonging to one class — subject OR activity.

    An activity has no assignment, so a filter written only against
    `assignment__*` silently drops it. Everything that means "this class"
    has to go through here.
    """
    return (
        Q(assignment__year_id=year_id, assignment__subject__semester=semester)
        | Q(class_activity__year_id=year_id, class_activity__semester=semester)
    )


def _locked_entries():
    """
    Every entry allowed to block another department.

    Layer 2 changed this. It used to be submitted/approved only. Now an ACTIVE
    DRAFT also holds its slots — so two HODs can't both build the same cell and
    only find out at submit.

    A draft is "active" if its HOD has touched it in the last HOLD_HOURS.
    Abandon it, and the holds lapse on their own.
    """
    cutoff = timezone.now() - timedelta(hours=HOLD_HOURS)

    pairs = list(
        TimetableApproval.objects
        .filter(
            Q(status__in=BLOCKING_STATUSES)                       # submitted / approved
            | Q(status=TimetableApproval.Status.DRAFT,            # or a live draft
                last_active__gt=cutoff)
        )
        .values_list("year_id", "semester")
    )

    if not pairs:
        return TimetableEntry.objects.none()

    q = Q()
    for year_id, semester in pairs:
        q |= class_q(year_id, semester)

    return TimetableEntry.objects.filter(q).select_related(
        "assignment__teacher",
        "assignment__subject",
        "assignment__year",
        "assignment__course",
        "class_activity__teacher",
        "class_activity__activity",
        "class_activity__year",
        "class_activity__year__course",
        "time_slot",
        "room",
    )


def _own_entry_ids(year_id, semester):
    """
    Primary keys of every entry belonging to this class.

    Used instead of `.exclude(assignment__year_id=...)`, which is a trap:
    an activity row has assignment = NULL, and in SQL `NOT (NULL = 8)` is
    NULL, not TRUE — so every OTHER department's activities would be
    silently dropped from the queryset too.
    """
    return set(
        TimetableEntry.objects
        .filter(class_q(year_id, semester))
        .values_list("id", flat=True)
    )


def _who(entry):
    """A short human label for the class holding a slot, e.g. 'B.E ECE Year 3'."""
    if entry.class_activity_id:
        year = entry.class_activity.year
        course = getattr(getattr(year, "course", None), "name", "")
        year_no = getattr(year, "year_number", "?")
        return f"{course} Year {year_no}".strip()

    a = entry.assignment
    course = getattr(a.course, "name", None) or getattr(
        getattr(a.year, "course", None), "name", ""
    )
    year_no = getattr(a.year, "year_number", "?")
    return f"{course} Year {year_no}".strip()


def _entry_teacher(entry):
    """The person standing at the front of the room — or None."""
    if entry.assignment_id:
        return entry.assignment.teacher
    if entry.class_activity_id:
        return entry.class_activity.teacher    # Library / Sports: None
    return None


def availability(assignment, year_id, semester, room=None):
    """
    Return which cells this assignment can go into, and which it can't.

        {
          "free":    [{"day": 0, "slot": 3}, ...],
          "blocked": [{"day": 0, "slot": 1,
                       "reason": "Dr. Kumar is teaching B.E ECE Year 3"}, ...]
        }

    `day` is 0..4 (Mon..Fri) and `slot` is a TimeSlot id.
    Break and lunch slots are left out entirely — they are never droppable.
    """
    slots = list(TimeSlot.objects.filter(is_break=False))
    locked = _locked_entries()

    teacher = assignment.teacher
    teacher_label = (teacher.get_full_name() or "").strip() or teacher.username

    # ---- 1) teacher already busy in someone else's locked timetable ----
    # A teacher can be busy on a LECTURE or on a SUPERVISED ACTIVITY (Mentor).
    # Looking only at assignment__teacher lets another department book the same
    # person for Mentor and this grid would still show the cell green.
    teacher_busy = {}
    for e in locked.filter(
        Q(assignment__teacher=teacher) | Q(class_activity__teacher=teacher)
    ):
        teacher_busy[(e.day_of_week, e.time_slot_id)] = (
            f"{teacher_label} is teaching {_who(e)}"
        )

    # ---- 2) room already booked in someone else's locked timetable ----
    room_busy = {}
    if room is not None:
        for e in locked.filter(room=room):
            room_busy[(e.day_of_week, e.time_slot_id)] = (
                f"{room.name} is booked by {_who(e)}"
            )

    # ---- 3) this class already has something in that cell (any status) ----
    self_busy = set(
        TimetableEntry.objects
        .filter(class_q(year_id, semester))
        .values_list("day_of_week", "time_slot_id")
    )

    free, blocked = [], []

    for day in DAYS:
        for slot in slots:
            key = (day, slot.id)

            reason = teacher_busy.get(key) or room_busy.get(key)
            if not reason and key in self_busy:
                reason = "This class already has something here"

            cell = {"day": day, "slot": slot.id}
            if reason:
                blocked.append({**cell, "reason": reason})
            else:
                free.append(cell)

    return {"free": free, "blocked": blocked}


def validate_submission(year_id, semester):
    """
    Called at SUBMIT. Two HODs can draft the same slot at once — the first
    to submit wins, and the second must be told exactly which cells clash
    and where to move them.

    Returns a list of conflicts, each with three suggested free slots.
    Empty list = safe to submit.
    """
    my_entries = list(
        TimetableEntry.objects
        .filter(class_q(year_id, semester))
        .select_related(
            "assignment__teacher", "assignment__subject",
            "class_activity__teacher", "class_activity__activity",
            "time_slot", "room",
        )
    )

    # everything locked by OTHER classes.
    # Exclude by primary key, never by `assignment__year_id` — see _own_entry_ids.
    own_ids = _own_entry_ids(year_id, semester)
    locked = _locked_entries().exclude(id__in=own_ids)

    slots = list(TimeSlot.objects.filter(is_break=False).order_by("period_no"))
    slot_name = {s.id: f"P{s.period_no}" for s in slots}
    day_name = dict(TimetableEntry.DAY_CHOICES)

    used = {(x.day_of_week, x.time_slot_id) for x in my_entries}
    conflicts = []

    for e in my_entries:
        same_cell = locked.filter(day_of_week=e.day_of_week, time_slot=e.time_slot)

        teacher = _entry_teacher(e)
        kind = None

        # An unsupervised activity (Library, Sports) has no teacher, so it can
        # never clash with one. It can still clash on a room, if it has one.
        if teacher:
            clash = same_cell.filter(
                Q(assignment__teacher=teacher) | Q(class_activity__teacher=teacher)
            ).first()
            if clash:
                who = (teacher.get_full_name() or "").strip() or teacher.username
                kind = f"{who} is now teaching {_who(clash)}"

        if not kind and e.room_id:
            if same_cell.filter(room_id=e.room_id).exists():
                kind = f"{e.room.name} is now booked by another class"

        if not kind:
            continue

        # ---- where COULD this go instead? ----
        if e.assignment_id:
            label = e.assignment.subject.name
            av = availability(
                e.assignment, year_id=year_id, semester=semester, room=e.room
            )
            options = [
                c for c in av["free"] if (c["day"], c["slot"]) not in used
            ][:3]
        else:
            # An activity has no TeachingAssignment, so the availability engine
            # (which takes one) can't be used. Its free cells are simply every
            # cell this class isn't already using.
            label = e.class_activity.activity.name
            options = [
                {"day": d, "slot": s.id}
                for d in DAYS
                for s in slots
                if (d, s.id) not in used
            ][:3]

        conflicts.append({
            "entry": e.id,
            "subject": label,
            "teacher": (
                (teacher.get_full_name() or "").strip() or teacher.username
            ) if teacher else "",
            "day": e.day_of_week,
            "slot": e.time_slot_id,
            "cell": f"{day_name.get(e.day_of_week, '?')} {slot_name.get(e.time_slot_id, '?')}",
            "reason": kind,
            "suggestions": [
                {
                    "day": c["day"],
                    "slot": c["slot"],
                    "label": f"{day_name.get(c['day'], '?')} {slot_name.get(c['slot'], '?')}",
                }
                for c in options
            ],
        })

    return conflicts