from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ReminderLog


class JobContext:
    def __init__(self, dry_run=False, out=None, today=None):
        self.dry_run = dry_run
        self.today = today or timezone.localdate()
        self.out = out or (lambda line: None)

    def already_sent(self, job, item_key, stage, recipient):
        return ReminderLog.objects.filter(
            job=job, item_key=item_key, stage=stage, recipient=recipient
        ).exists()

    def notify_once(self, job, item_key, stage, recipients, title, message,
                    notif_type="announcement", link=""):
        """
        Notify each recipient once for (job, item, stage). Returns how many
        were (or in a dry run, would be) notified.
        """
        from core.notifications.services import notify

        fresh = [r for r in recipients
                 if r is not None and not self.already_sent(job, item_key, stage, r)]
        if not fresh:
            return 0
        if self.dry_run:
            for r in fresh:
                self.out(f"    would notify {r} - {title}")
            return len(fresh)

        sent = []
        for r in fresh:
            try:
                with transaction.atomic():
                    ReminderLog.objects.create(job=job, item_key=item_key, stage=stage, recipient=r)
                sent.append(r)
            except IntegrityError:
                pass                          # another run got there first
        if sent:
            notify(sent, title, message, notif_type, link=link)
        return len(sent)


def _run_command(name, ctx, *args):
    out = StringIO()
    # no_color: a coloured terminal (VS Code) would add hidden colour codes
    # to the text, and the sent count could not be read from it
    call_command(name, *args, *(["--dry-run"] if ctx.dry_run else []),
                 stdout=out, no_color=True)
    text = out.getvalue().strip()
    for line in text.splitlines():
        ctx.out(f"    {line}")
    return text


# ---------------- existing jobs, now run by the runner ----------------
def assignment_due(ctx):
    """Existing remind_due_assignments command (unchanged)."""
    _run_command("remind_due_assignments", ctx)
    return 0


def email_queue(ctx):
    """Existing send_notification_emails command - always LAST."""
    import re
    text = _run_command("send_notification_emails", ctx)
    found = re.search(r"sent (\d+)", text)
    return int(found.group(1)) if found else 0


# ---------------- FEE REMINDERS (Point 12, step 5) ----------------
# Unpaid fees (pending / partial). Each stage is sent once per fee per person.
# A missed night is caught the next night (a range, not one exact day), but
# fees long past their grace period are NOT reminded again (no history spam).
GRACE_ENDED_CATCH_UP_DAYS = 2


def _fee_setup():
    from config.module_registry import module_enabled
    from .models import AutomationSetting
    if not module_enabled("fees"):
        return None, None
    rules = AutomationSetting.current()
    if not rules.fee_reminders_on:
        return None, rules
    from modules.fees.models import Fee
    return Fee, rules


def _parents_of(student):
    from core.users.models import ParentProfile
    return [pp.user for pp in ParentProfile.objects.filter(children=student).select_related("user")]


def _money(value):
    return f"\u20b9{value:,.0f}" if value == int(value) else f"\u20b9{value:,.2f}"


def _fee_notify(ctx, job, stage, fee, title, student_msg, parent_msg, extra=()):
    student = fee.student
    key = f"fee:{fee.id}"
    n = ctx.notify_once(job, key, stage, [student], title, student_msg, "announcement")
    n += ctx.notify_once(job, key, stage, _parents_of(student), title, parent_msg,
                         "announcement", link="/parent/fees")
    if extra:
        n += ctx.notify_once(job, key, stage, list(extra), title,
                             f"{student.username}: {student_msg}", "announcement", link="/admin/fees")
    return n


def _balance(fee):
    return (fee.amount or 0) - (fee.paid_amount or 0)


def fee_due_soon(ctx):
    """Unpaid fee due within the next X days (default 3)."""
    import datetime
    Fee, rules = _fee_setup()
    if Fee is None:
        return 0
    last = ctx.today + datetime.timedelta(days=rules.fee_remind_days_before)
    sent = 0
    for fee in (Fee.objects.exclude(status="paid")
                .filter(due_date__gt=ctx.today, due_date__lte=last)
                .select_related("student")):
        days = (fee.due_date - ctx.today).days
        when = "tomorrow" if days == 1 else f"in {days} days"
        due = fee.due_date.strftime("%d-%m-%Y")
        bal = _money(_balance(fee))
        sent += _fee_notify(
            ctx, "fee_due_soon", "due_soon", fee,
            f"Fee due {when}: {fee.term}",
            f"{fee.term}: {bal} is due on {due}.",
            f"{fee.student.username}'s fee {fee.term}: {bal} is due on {due}.",
        )
    return sent


def fee_overdue(ctx):
    """Unpaid fee past its due date, still inside the grace period."""
    import datetime
    Fee, rules = _fee_setup()
    if Fee is None:
        return 0
    sent = 0
    first = ctx.today - datetime.timedelta(days=rules.fee_grace_days)   # grace not over yet
    for fee in (Fee.objects.exclude(status="paid")
                .filter(due_date__lt=ctx.today, due_date__gt=first)
                .select_related("student")):
        grace_end = fee.due_date + datetime.timedelta(days=rules.fee_grace_days)
        if ctx.today >= grace_end:
            continue
        end = grace_end.strftime("%d-%m-%Y")
        bal = _money(_balance(fee))
        sent += _fee_notify(
            ctx, "fee_overdue", "overdue", fee,
            f"Fee overdue: {fee.term}",
            f"{fee.term}: {bal} was due on {fee.due_date:%d-%m-%Y}. Please pay by {end} (grace period).",
            f"{fee.student.username}'s fee {fee.term}: {bal} is overdue. Please pay by {end} (grace period).",
        )
    return sent


def fee_grace_ended(ctx):
    """Last grace day (or up to 2 days after, if the runner missed a night)."""
    import datetime
    from django.contrib.auth import get_user_model
    Fee, rules = _fee_setup()
    if Fee is None:
        return 0
    accounts = list(get_user_model().objects.filter(role="admin", sub_role="accounts_admin", is_active=True))
    newest = ctx.today - datetime.timedelta(days=rules.fee_grace_days)
    oldest = newest - datetime.timedelta(days=GRACE_ENDED_CATCH_UP_DAYS)
    sent = 0
    for fee in (Fee.objects.exclude(status="paid")
                .filter(due_date__gte=oldest, due_date__lte=newest)
                .select_related("student")):
        bal = _money(_balance(fee))
        sent += _fee_notify(
            ctx, "fee_grace_ended", "grace_ended", fee,
            f"Grace period ended: {fee.term}",
            f"{fee.term}: {bal} is still unpaid and the grace period has ended. Please pay at the accounts office.",
            f"{fee.student.username}'s fee {fee.term}: {bal} is still unpaid; the grace period has ended.",
            extra=accounts,
        )
    return sent


# ---------------- WEEKLY LOW ATTENDANCE (Point 12, step 6) ----------------
# Once a week (AutomationSetting.attendance_alert_weekday, Monday by default):
# every student below the #41 eligibility minimum gets ONE alert, their
# parents get one, and each class tutor gets one list of their students.
# Same percentage as the hall ticket: this semester's records, present and
# on duty count as attended.
def _semester_percent(student):
    from modules.attendance.models import Attendance
    records = Attendance.objects.filter(
        student=student, teaching_assignment__subject__semester=student.semester,
    )
    total = records.count()
    if total == 0:
        return None
    counted = records.filter(status__in=["present", "duty_leave"]).count()
    return round(counted / total * 100, 1)


def _min_attendance():
    from config.module_registry import module_enabled
    if module_enabled("exams"):
        from modules.exams.models import EligibilitySetting
        return float(EligibilitySetting.current().min_attendance)
    return 75.0


def _pct(value):
    return f"{value:g}%"


def low_attendance(ctx):
    from config.module_registry import module_enabled
    from django.contrib.auth import get_user_model
    from core.academics.models import YearTutor
    from .models import AutomationSetting
    if not module_enabled("attendance") or not AutomationSetting.current().attendance_alerts_on:
        return 0
    minimum = _min_attendance()
    year, week, _ = ctx.today.isocalendar()
    stage = f"week-{year}-{week:02d}"
    sent = 0
    by_class = {}                                   # (course_id, year) -> [(student, pct)]
    students = (get_user_model().objects
                .filter(role="student", is_active=True)
                .order_by("roll_number"))
    for s in students:
        pct = _semester_percent(s)
        if pct is None or pct >= minimum:
            continue
        key = f"attendance:{s.id}"
        sent += ctx.notify_once(
            "low_attendance", key, stage, [s],
            f"Attendance below {_pct(minimum)}",
            f"Your attendance this semester is {_pct(pct)}; the minimum is {_pct(minimum)}. "
            f"Below the minimum you may not get your hall ticket. Please attend every class.",
            "announcement", link="/student/attendance",
        )
        sent += ctx.notify_once(
            "low_attendance", key, stage, _parents_of(s),
            f"Attendance below {_pct(minimum)}: {s.username}",
            f"{s.username}'s attendance this semester is {_pct(pct)}; the minimum is {_pct(minimum)}.",
            "announcement", link="/parent/attendance",
        )
        by_class.setdefault((s.course_id, s.year), []).append((s, pct))

    for (course_id, yr), rows in by_class.items():
        tutors = [t.teacher for t in YearTutor.objects.filter(course_id=course_id, year__year_number=yr)
                  .select_related("teacher")]
        if not tutors:
            continue
        names = ", ".join(f"{s.username} ({_pct(p)})" for s, p in rows)
        sent += ctx.notify_once(
            "low_attendance", f"attendance-class:{course_id}-{yr}", stage, tutors,
            f"{len(rows)} student(s) below {_pct(minimum)} attendance",
            f"Year {yr}: {names}.",
            "announcement", link="/my-class",
        )
    return sent


# ---------------- RESULTS PUBLISHED (Point 12, step 7) ----------------
# EVENT-based, not nightly: called when a semester result is published.
# Student + parents are told once per result, even if the admin publishes
# again, or unpublishes to fix a mark and publishes again.
def notify_results_published(result):
    ctx = JobContext()
    student = result.student
    key = f"result:{result.id}"
    n = ctx.notify_once(
        "results_published", key, "published", [student],
        f"Semester {result.semester} results published",
        f"Your Semester {result.semester} results are published. "
        f"Open Results to see your marks and grades.",
        "exam", link="/results",
    )
    n += ctx.notify_once(
        "results_published", key, "published", _parents_of(student),
        f"Semester {result.semester} results published: {student.username}",
        f"{student.username}'s Semester {result.semester} results are published.",
        "exam", link="/results",
    )
    return n



# ---------------- ACTING HOD (#50, Step 5) ----------------
# Start / end notices and nomination reminders. notify_once() makes sure
# nobody gets the same notice twice, and the dry run sends nothing.
# These jobs need the Acting HOD feature (core/users/acting_hod.py and the
# ActingHOD model). Until it is installed they SKIP cleanly instead of
# failing every night.
def _acting():
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is None:
        return None, None
    from core.users import acting_hod as ah
    from core.users.models import ActingHOD
    return ActingHOD, ah


def _acting_missing(ctx):
    ctx.out("    Acting HOD feature not installed - skipped")
    return 0


def _ddmmyyyy(day):
    return day.strftime("%d-%m-%Y")


def acting_hod_start(ctx):
    """Start (or first night after a late approval): tell the Acting HOD and the regular HOD."""
    import datetime
    ActingHOD, ah = _acting()
    if ActingHOD is None:
        return _acting_missing(ctx)
    sent = 0
    rows = (ActingHOD.objects
            .filter(approval_status="approved", ended_at__isnull=True,
                    start_date__lte=ctx.today, end_date__gte=ctx.today)
            .select_related("department__hod", "teacher"))
    for a in rows:
        key = f"acting:{a.id}"
        dept = a.department
        back = _ddmmyyyy(a.end_date + datetime.timedelta(days=1))
        sent += ctx.notify_once(
            "acting_hod_start", key, "start", [a.teacher],
            f"You are Acting HOD of {dept.name}",
            f"You hold the HOD powers of {dept.name} until {_ddmmyyyy(a.end_date)}. Reason: {a.reason}",
            "leave", link="/my-department",
        )
        regular_hod = dept.hod   # the REGULAR HOD on purpose: tell them someone is acting
        sent += ctx.notify_once(
            "acting_hod_start", key, "start", [regular_hod],
            f"{a.teacher.username} is Acting HOD of {dept.name}",
            f"{a.teacher.username} holds the HOD powers of {dept.name} until "
            f"{_ddmmyyyy(a.end_date)}. Your HOD powers return on {back}.",
            "leave",
        )
    return sent


def acting_hod_end(ctx):
    """After an assignment finished or was ended early: tell both that the regular HOD is back."""
    import datetime
    from django.db.models import Q
    ActingHOD, ah = _acting()
    if ActingHOD is None:
        return _acting_missing(ctx)
    sent = 0
    since = ctx.today - datetime.timedelta(days=3)      # catch up if a night was missed
    rows = (ActingHOD.objects
            .filter(approval_status="approved")
            .filter(Q(ended_at__isnull=True, end_date__lt=ctx.today, end_date__gte=since)
                    | Q(ended_at__isnull=False, ended_at__date__gte=since))
            .select_related("department__hod", "teacher"))
    for a in rows:
        if ah.status_of(a, ctx.today) not in ("finished", "ended_early"):
            continue                                    # cancelled before it began
        dept = a.department
        regular_hod = dept.hod   # the REGULAR HOD on purpose: they are HOD again
        hod = regular_hod.username if regular_hod else "The regular HOD"
        sent += ctx.notify_once(
            "acting_hod_end", f"acting:{a.id}", "end", [a.teacher, regular_hod],
            f"Acting HOD period ended: {dept.name}",
            f"{a.teacher.username}'s Acting HOD period for {dept.name} has ended. "
            f"{hod} is HOD of {dept.name} again.",
            "leave",
        )
    return sent


def acting_hod_pending(ctx):
    """Remind the main admin about waiting nominations; tell the HOD when one expired."""
    import datetime
    ActingHOD, ah = _acting()
    if ActingHOD is None:
        return _acting_missing(ctx)
    sent = 0
    tomorrow = ctx.today + datetime.timedelta(days=1)
    rows = (ActingHOD.objects
            .filter(approval_status="pending", ended_at__isnull=True)
            .select_related("department", "teacher", "nominated_by"))
    for a in rows:
        key = f"acting:{a.id}"
        st = ah.status_of(a, ctx.today)
        who = a.nominated_by.username if a.nominated_by else "The HOD"
        if st == "pending" and a.start_date <= tomorrow:
            when = "today" if a.start_date <= ctx.today else "tomorrow"
            sent += ctx.notify_once(
                "acting_hod_pending", key, f"remind-{ctx.today.isoformat()}",
                list(ah.main_admins()),
                "Acting HOD nomination waiting for you",
                f"{who} nominated {a.teacher.username} as Acting HOD of {a.department.name} "
                f"from {_ddmmyyyy(a.start_date)} to {_ddmmyyyy(a.end_date)}. It starts {when} "
                f"and is still waiting for your decision.",
                "leave", link="/departments",
            )
        elif st == "expired":
            sent += ctx.notify_once(
                "acting_hod_pending", key, "expired", [a.nominated_by],
                "Acting HOD nomination expired",
                f"Your nomination of {a.teacher.username} as Acting HOD of {a.department.name} "
                f"({_ddmmyyyy(a.start_date)} to {_ddmmyyyy(a.end_date)}) was not approved in time, "
                f"so it gave no HOD powers.",
                "leave", link="/teacher/leave",
            )
    return sent

# ---------------- the job list (order matters) ----------------
# (name, function, when)   when = "daily" or "weekly:<0-6>" (0 = Monday)
# Steps 5-7 add: fee_due_soon, fee_overdue, fee_grace_ended,
#                low_attendance (weekly), ...
# ---------------- PLACEMENT ELIGIBILITY (meeting point 10) ----------------
def placement_eligibility(ctx):
    """
    Nightly safety net for the saved placement eligibility table. Most
    changes refresh it straight away (placement/signals.py); this catches
    anything that slipped past, e.g. students promoted in bulk.
    Sends nothing. Dry run: only says how much would be re-checked.
    """
    from django.apps import apps
    if not apps.is_installed("modules.placement"):
        ctx.out("    placement module is off - skipped")
        return 0
    from modules.placement import eligibility_store as store
    if ctx.dry_run:
        roles, students = len(store._roles()), len(store._students())
        ctx.out(f"    would re-check {students} students x {roles} open roles")
        return 0
    summary = store.refresh_all()
    ctx.out(f"    re-checked {summary['students']} students x {summary['roles']} roles")
    return summary["rows"]


JOBS = [
    ("fee_due_soon", fee_due_soon, "daily"),        # step 5
    ("fee_overdue", fee_overdue, "daily"),          # step 5
    ("fee_grace_ended", fee_grace_ended, "daily"),  # step 5
    ("low_attendance", low_attendance, "weekly:setting"),   # step 6, day from settings
    ("assignment_due", assignment_due, "daily"),
    ("acting_hod_start", acting_hod_start, "daily"),      # #50 Step 5
    ("acting_hod_end", acting_hod_end, "daily"),          # #50 Step 5
    ("acting_hod_pending", acting_hod_pending, "daily"),  # #50 Step 5
    ("placement_eligibility", placement_eligibility, "daily"),   # point 10
    ("email_queue", email_queue, "daily"),      # keep last
]


def describe_when(when):
    """'daily', or 'weekly (Monday)' - for --list and the run output."""
    if when == "weekly:setting":
        from .models import AutomationSetting
        when = f"weekly:{AutomationSetting.current().attendance_alert_weekday}"
    if when.startswith("weekly:"):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"weekly ({days[int(when.split(':')[1])]})"
    return when


def due_today(when, today):
    if when == "daily":
        return True
    if when == "weekly:setting":                    # step 6: day chosen in settings
        from .models import AutomationSetting
        return today.weekday() == AutomationSetting.current().attendance_alert_weekday
    if when.startswith("weekly:"):
        return today.weekday() == int(when.split(":")[1])
    return False