"""
#50 ACTING HOD - rules for a temporary HOD.

Step 1 : assign / extend / end early, with all the checks.
Step 2 : helpers that every HOD check in the LMS uses (who is HOD right now).
Step 3b: HOD nomination from the leave form + main admin approve / reject,
         expiry, and the link to the leave (leave cancelled -> cancelled).

Rules
  - start_date and end_date are both included (college date, Asia/Kolkata).
  - "Today" is ALWAYS timezone.localdate(), never the server's own clock.
  - No back-dating of a direct assignment.
  - Only APPROVED assignments give powers. Pending / expired / rejected never do.
  - Late approval is never retroactive: powers start at approval time.
  - Ending early stops the powers at that moment (ended_at).
  - A pending nomination holds its dates (no overlap) until decided or expired.
"""
import datetime
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.users.models import ActingHOD, ActingHODLog, Department, User

logger = logging.getLogger(__name__)

MIN_REASON = 10
MAX_REASON = 255
ONE_DAY = datetime.timedelta(days=1)
ADMIN_LINK = "/departments"


class ActingHODError(Exception):
    """A rule was broken. The message is shown to the user as it is."""


# ----------------------------------------------------------------- who ---
def is_main_admin(user):
    """Superuser, or role admin with no sub-role / super_admin (same rule as #41)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (getattr(user, "role", "") == "admin"
            and (getattr(user, "sub_role", "") or "") in ("", "super_admin"))


def main_admins():
    return (User.objects.filter(is_active=True)
            .filter(Q(is_superuser=True)
                    | Q(role="admin", sub_role__in=["", "super_admin"])
                    | Q(role="admin", sub_role__isnull=True))
            .distinct())


def can_nominate(user):
    """Only the REGULAR HOD of a department may nominate (not an Acting HOD)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", "") != "teacher":
        return False
    return Department.objects.filter(hod_id=user.id).exists()


def _notify(users, title, message, link):
    """Best effort: a failed notification must never undo the action."""
    users = [u for u in users if u]
    if not users:
        return
    try:
        from core.notifications.services import notify
        notify(users, title, message, "leave", link=link)
    except Exception:
        logger.exception("Acting HOD notification failed: %s", title)


# --------------------------------------------------------------- dates ---
def _d(day):
    return day.strftime("%d-%m-%Y")


def _parse_date(value, label):
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise ActingHODError(f"{label} must be a date like 2026-11-10.")


def _check_reason(reason):
    text = (reason or "").strip()
    if len(text) < MIN_REASON:
        raise ActingHODError(f"Please give a reason (at least {MIN_REASON} characters).")
    if len(text) > MAX_REASON:
        raise ActingHODError(f"Keep the reason under {MAX_REASON} characters.")
    return text


def effective_end(a):
    """Last full day this row holds its dates (for overlap checks)."""
    if a.ended_at is None:
        return a.end_date
    return min(a.end_date, timezone.localdate(a.ended_at) - ONE_DAY)


def status_of(a, today=None):
    """pending | expired | rejected | upcoming | active | finished | ended_early | cancelled"""
    today = today or timezone.localdate()
    if a.approval_status == "rejected":
        return "rejected"
    if a.ended_at:
        if a.approval_status == "pending" or timezone.localdate(a.ended_at) < a.start_date:
            return "cancelled"
        return "ended_early"
    if a.approval_status == "pending":
        return "expired" if today > a.end_date else "pending"
    if today < a.start_date:
        return "upcoming"
    if today > a.end_date:
        return "finished"
    return "active"


def _check_overlap(department, start, end, exclude_id=None):
    others = (ActingHOD.objects.filter(department=department)
              .exclude(pk=exclude_id)
              .exclude(approval_status="rejected")
              .select_related("teacher"))
    for other in others:
        if other.approval_status == "pending" and other.ended_at:
            continue  # cancelled nomination
        last = effective_end(other)
        if last < other.start_date:
            continue  # cancelled before it began
        if other.start_date <= end and start <= last:
            kind = ("has a pending Acting HOD nomination for"
                    if other.approval_status == "pending" else "is already Acting HOD of")
            raise ActingHODError(
                f"{other.teacher.username} {kind} {department.name} "
                f"from {_d(other.start_date)} to {_d(last)}. The dates cannot overlap."
            )


def _check_teacher(teacher, dept):
    if teacher.role != "teacher" or not teacher.is_active:
        raise ActingHODError("Only an active teacher can be Acting HOD.")
    if teacher.department_id != dept.id:
        raise ActingHODError(f"{teacher.username} is not in {dept.name}.")
    if dept.hod_id == teacher.id:
        raise ActingHODError(f"{teacher.username} is already the HOD of {dept.name}.")


# ------------------------------------------------- who is HOD right now ---
# Every HOD check in the LMS goes through these helpers.

def active_assignments(now=None):
    """APPROVED Acting HOD assignments that give powers at this moment."""
    today = timezone.localdate(now)
    return ActingHOD.objects.filter(
        approval_status="approved",
        start_date__lte=today, end_date__gte=today, ended_at__isnull=True,
    )


def hod_departments(user, now=None):
    """
    Departments this user is HOD of RIGHT NOW:
      - the Acting HOD gets the department while their assignment is active;
      - the regular HOD keeps it only when nobody is acting for it.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Department.objects.none()
    active = active_assignments(now)
    acting_for = active.filter(teacher=user).values("department_id")
    covered = active.values("department_id")
    return Department.objects.filter(
        Q(pk__in=acting_for) | (Q(hod=user) & ~Q(pk__in=covered))
    )


def hod_department_ids(user, now=None):
    return list(hod_departments(user, now).values_list("id", flat=True))


def is_hod(user, now=None):
    return hod_departments(user, now).exists()


def current_assignment(department, now=None):
    """The active (approved) ActingHOD row of this department, or None."""
    if department is None:
        return None
    return (active_assignments(now).filter(department_id=department.pk)
            .select_related("teacher").first())


def current_hod(department, now=None):
    """Who the HOD of this department is right now (Acting HOD wins)."""
    if department is None:
        return None
    a = current_assignment(department, now)
    return a.teacher if a else department.hod


def is_current_hod_of(user, department, now=None):
    hod = current_hod(department, now)
    return bool(hod and user and hod.id == user.id)


def _check_pending_leave(teacher, department, end):
    """
    Refuse when the teacher has a pending leave whose start date is on or
    before the (new) end date: nobody could decide it during the acting
    period. Skipped when the attendance module is off (users is core).
    """
    from django.apps import apps
    from config.module_registry import module_enabled
    if not module_enabled("attendance"):
        return
    try:
        Leave = apps.get_model("attendance", "StaffLeaveRequest")
    except LookupError:
        return
    p = (Leave.objects
         .filter(teacher=teacher, status=Leave.Status.PENDING, from_date__lte=end)
         .order_by("from_date").first())
    if p:
        hod = current_hod(department)
        who = hod.username if hod else "the HOD"
        raise ActingHODError(
            f"{teacher.username} has a pending leave request ({_d(p.from_date)}). "
            f"Ask {who} to decide it first."
        )


# ------------------------------------------------------- admin actions ---
def assign(admin, department_id, teacher_id, start_date, end_date, reason):
    """Direct assignment by the main admin: approved at once."""
    reason = _check_reason(reason)
    start = _parse_date(start_date, "Start date")
    end = _parse_date(end_date, "End date")
    today = timezone.localdate()
    if start < today:
        raise ActingHODError("The start date cannot be in the past.")
    if end < start:
        raise ActingHODError("The end date cannot be before the start date.")

    with transaction.atomic():
        try:
            dept = Department.objects.select_for_update().get(pk=department_id)
        except (Department.DoesNotExist, ValueError, TypeError):
            raise ActingHODError("Pick a department.")
        try:
            teacher = User.objects.get(pk=teacher_id)
        except (User.DoesNotExist, ValueError, TypeError):
            raise ActingHODError("Pick a teacher.")

        _check_teacher(teacher, dept)
        _check_pending_leave(teacher, dept, end)
        _check_overlap(dept, start, end)

        a = ActingHOD.objects.create(
            department=dept, teacher=teacher, start_date=start, end_date=end,
            reason=reason, assigned_by=admin,
            approval_status="approved", approved_by=admin, approved_at=timezone.now(),
        )
        ActingHODLog.objects.create(
            assignment=a, action="assigned", new_end_date=end,
            reason=reason, done_by=admin,
        )
    return a


def extend(admin, assignment_id, new_end_date, reason):
    reason = _check_reason(reason)
    new_end = _parse_date(new_end_date, "New end date")
    today = timezone.localdate()

    with transaction.atomic():
        a = (ActingHOD.objects.select_for_update()
             .select_related("department", "teacher").get(pk=assignment_id))
        if a.approval_status != "approved":
            raise ActingHODError("Only an approved assignment can be extended.")
        if a.ended_at:
            raise ActingHODError("This assignment was already ended. Make a new one instead.")
        if a.end_date < today:
            raise ActingHODError("This assignment has already finished. Make a new one instead.")
        if new_end <= a.end_date:
            raise ActingHODError(f"The new end date must be after {_d(a.end_date)}.")

        Department.objects.select_for_update().get(pk=a.department_id)
        _check_overlap(a.department, a.start_date, new_end, exclude_id=a.id)
        _check_pending_leave(a.teacher, a.department, new_end)

        old_end = a.end_date
        a.end_date = new_end
        a.save(update_fields=["end_date"])
        ActingHODLog.objects.create(
            assignment=a, action="extended", old_end_date=old_end,
            new_end_date=new_end, reason=reason, done_by=admin,
        )
    return a


def end_early(admin, assignment_id, reason):
    reason = _check_reason(reason)
    today = timezone.localdate()

    with transaction.atomic():
        a = (ActingHOD.objects.select_for_update()
             .select_related("department", "teacher").get(pk=assignment_id))
        if a.approval_status != "approved":
            raise ActingHODError("This nomination is not approved. Approve or reject it instead.")
        if a.ended_at:
            raise ActingHODError("This assignment was already ended.")
        if a.end_date < today:
            raise ActingHODError("This assignment has already finished. There is nothing to end.")

        a.ended_at = timezone.now()
        a.ended_by = admin
        a.end_reason = reason
        a.save(update_fields=["ended_at", "ended_by", "end_reason"])
        ActingHODLog.objects.create(
            assignment=a, action="ended", old_end_date=a.end_date,
            reason=reason, done_by=admin,
        )
    return a


def approve(admin, assignment_id):
    """Main admin approves a pending nomination. Powers start NOW (never retroactive)."""
    with transaction.atomic():
        a = (ActingHOD.objects.select_for_update(of=("self",))
             .select_related("department", "teacher", "nominated_by").get(pk=assignment_id))
        if a.approval_status != "pending" or a.ended_at:
            raise ActingHODError("This nomination is not waiting for approval.")
        if timezone.localdate() > a.end_date:
            raise ActingHODError("This nomination has expired. It can no longer be approved.")

        dept = Department.objects.select_for_update().get(pk=a.department_id)
        _check_teacher(a.teacher, dept)
        _check_overlap(dept, a.start_date, a.end_date, exclude_id=a.id)

        a.approval_status = "approved"
        a.approved_by = admin
        a.approved_at = timezone.now()
        a.save(update_fields=["approval_status", "approved_by", "approved_at"])
        ActingHODLog.objects.create(
            assignment=a, action="approved", new_end_date=a.end_date,
            reason=f"Approved by {admin.username}.", done_by=admin,
        )

    text = (f"{a.teacher.username} is Acting HOD of {dept.name} "
            f"from {_d(a.start_date)} to {_d(a.end_date)} (approved by {admin.username}).")
    _notify([a.teacher], f"You are Acting HOD of {dept.name}", text, "/my-department")
    _notify([a.nominated_by], "Acting HOD nomination approved", text, "/teacher/leave")
    return a


def reject(admin, assignment_id, reason):
    reason = _check_reason(reason)
    with transaction.atomic():
        a = (ActingHOD.objects.select_for_update(of=("self",))
             .select_related("department", "teacher", "nominated_by").get(pk=assignment_id))
        if a.approval_status != "pending" or a.ended_at:
            raise ActingHODError("This nomination is not waiting for approval.")

        a.approval_status = "rejected"
        a.rejected_by = admin
        a.rejected_at = timezone.now()
        a.reject_reason = reason
        a.save(update_fields=["approval_status", "rejected_by", "rejected_at", "reject_reason"])
        ActingHODLog.objects.create(
            assignment=a, action="rejected", reason=reason, done_by=admin,
        )

    _notify([a.nominated_by], "Acting HOD nomination rejected",
            f"Your nomination of {a.teacher.username} as Acting HOD of {a.department.name} "
            f"was rejected by {admin.username}. Reason: {reason}", "/teacher/leave")
    return a


# ------------------------------------------------ HOD nomination (3b) ---
def nominate(hod, leave):
    """
    Called from 'record HOD leave' when the regular HOD ticks
    'Nominate as Acting HOD'. The nominee is the leave's backup teacher,
    the dates are the leave dates (from today if the leave already started).
    Creates a PENDING row: no powers until the main admin approves.
    """
    dept = leave.department
    if dept is None or dept.hod_id != hod.id:
        raise ActingHODError("Only the regular HOD can nominate an Acting HOD.")
    nominee = leave.backup
    if nominee is None:
        raise ActingHODError("Choose a backup teacher to nominate as Acting HOD.")

    today = timezone.localdate()
    if leave.to_date < today:
        raise ActingHODError("This leave has already ended, so no Acting HOD is needed.")
    start = max(leave.from_date, today)
    end = leave.to_date
    reason = (f"Acting HOD needed: {hod.username} on leave "
              f"{_d(leave.from_date)} to {_d(leave.to_date)}.")[:MAX_REASON]

    with transaction.atomic():
        dept = Department.objects.select_for_update().get(pk=dept.pk)
        _check_teacher(nominee, dept)
        _check_pending_leave(nominee, dept, end)
        _check_overlap(dept, start, end)

        a = ActingHOD.objects.create(
            department=dept, teacher=nominee, start_date=start, end_date=end,
            reason=reason, assigned_by=hod, nominated_by=hod,
            approval_status="pending", leave_id=leave.id,
        )
        ActingHODLog.objects.create(
            assignment=a, action="nominated", new_end_date=end,
            reason=reason, done_by=hod,
        )

    _notify(list(main_admins()), f"Acting HOD nomination from {hod.username}",
            f"{hod.username} nominated {nominee.username} as Acting HOD of {dept.name} "
            f"from {_d(start)} to {_d(end)}. Approve or reject it on the Departments page.",
            ADMIN_LINK)
    return a


def leave_cancelled(leave_id, by):
    """
    The HOD's leave was cancelled: cancel what was made with it.
      pending                -> cancelled
      approved, not started  -> cancelled
      approved, active       -> ended early (powers return now)
    Finished / expired / rejected rows are left alone.
    """
    today = timezone.localdate()
    reason = f"Leave cancelled by {by.username}"
    ended = []
    with transaction.atomic():
        rows = (ActingHOD.objects.select_for_update()
                .filter(leave_id=leave_id, ended_at__isnull=True)
                .exclude(approval_status="rejected")
                .select_related("teacher", "department"))
        for a in rows:
            if a.end_date < today:
                continue
            was_approved = a.approval_status == "approved"
            a.ended_at = timezone.now()
            a.ended_by = by
            a.end_reason = reason
            a.save(update_fields=["ended_at", "ended_by", "end_reason"])
            ActingHODLog.objects.create(
                assignment=a, action="ended", old_end_date=a.end_date,
                reason=reason, done_by=by,
            )
            if was_approved:
                ended.append(a)
    for a in ended:
        _notify([a.teacher], f"Acting HOD of {a.department.name} cancelled",
                f"{reason}. Your Acting HOD period ({_d(a.start_date)} to {_d(a.end_date)}) "
                f"has ended.", "/my-department")
    return ended


# ------------------------------------------------------- label (Step 5) ---
def was_acting_hod(user, department_id, at):
    """
    Was `user` the APPROVED, ACTIVE Acting HOD of this department at the
    moment `at` (a datetime)? Used for the "(Acting HOD)" label on decisions.
    Late approval is never retroactive: a decision before approved_at does
    not count. Old rows without approved_at use assigned_at.
    """
    if not user or not department_id or not at:
        return False
    day = timezone.localdate(at)
    rows = ActingHOD.objects.filter(
        teacher=user, department_id=department_id, approval_status="approved",
        start_date__lte=day, end_date__gte=day,
    )
    for a in rows:
        began = a.approved_at or a.assigned_at
        if began and at < began:
            continue
        if a.ended_at and at >= a.ended_at:
            continue
        return True
    return False


# ------------------------------------------------------ banners (Step 4) ---
def _banner_row(a):
    """One assignment as the banner needs it. started_at is set only when the
    approval came on/after the start day (late approval, never retroactive)."""
    started_at = None
    if a.approved_at and timezone.localdate(a.approved_at) >= a.start_date:
        started_at = timezone.localtime(a.approved_at).isoformat()
    approver = a.approved_by or a.assigned_by
    return {
        "id": a.id,
        "department": a.department.name,
        "teacher": a.teacher.username,
        "start_date": a.start_date.isoformat(),
        "end_date": a.end_date.isoformat(),
        "reason": a.reason,
        "approved_by": approver.username if approver else None,
        "nominated_by": a.nominated_by.username if a.nominated_by else None,
        "started_at": started_at,
        "returns_on": (a.end_date + ONE_DAY).isoformat(),
    }


def banner_info(user, now=None):
    """
    Step 4: what the logged-in teacher should be TOLD right now.
    Information only - permissions still come only from hod_departments() /
    current_hod(). Finished / cancelled / rejected / expired rows are never
    returned, so their banners disappear.
    """
    out = {"acting": None, "upcoming": None, "covered_by": None, "pending_nominations": []}
    if (not user or not getattr(user, "is_authenticated", False)
            or getattr(user, "role", "") != "teacher"):
        return out
    today = timezone.localdate(now)
    rel = ("department", "teacher", "approved_by", "assigned_by", "nominated_by")

    a = active_assignments(now).filter(teacher=user).select_related(*rel).first()
    if a:
        out["acting"] = _banner_row(a)

    up = (ActingHOD.objects
          .filter(teacher=user, approval_status="approved", ended_at__isnull=True,
                  start_date__gt=today)
          .select_related(*rel).order_by("start_date").first())
    if up:
        out["upcoming"] = _banner_row(up)

    for dept in Department.objects.filter(hod_id=user.id):
        c = active_assignments(now).filter(department=dept).select_related(*rel).first()
        if c:
            out["covered_by"] = _banner_row(c)
            break

    pend = (ActingHOD.objects
            .filter(nominated_by=user, approval_status="pending", ended_at__isnull=True,
                    end_date__gte=today)
            .select_related(*rel).order_by("start_date"))
    out["pending_nominations"] = [_banner_row(p) for p in pend]
    return out


# ----------------------------------------------------------- serialize ---
def serialize(a, today=None):
    def name(u):
        return u.username if u else None

    def iso(v):
        return v.isoformat() if v else None

    return {
        "id": a.id,
        "department": {"id": a.department_id, "name": a.department.name},
        "teacher": {
            "id": a.teacher_id,
            "username": a.teacher.username,
            "name": a.teacher.get_full_name() or a.teacher.username,
        },
        "start_date": iso(a.start_date),
        "end_date": iso(a.end_date),
        "reason": a.reason,
        "assigned_by": name(a.assigned_by),
        "assigned_at": iso(a.assigned_at),
        "ended_at": iso(a.ended_at),
        "ended_by": name(a.ended_by),
        "end_reason": a.end_reason,
        "approval_status": a.approval_status,
        "nominated_by": name(a.nominated_by),
        "approved_by": name(a.approved_by),
        "approved_at": iso(a.approved_at),
        "rejected_by": name(a.rejected_by),
        "rejected_at": iso(a.rejected_at),
        "reject_reason": a.reject_reason,
        "leave_id": a.leave_id,
        "status": status_of(a, today),
        "log": [
            {
                "action": l.action,
                "action_label": l.get_action_display(),
                "old_end_date": iso(l.old_end_date),
                "new_end_date": iso(l.new_end_date),
                "reason": l.reason,
                "done_by": name(l.done_by),
                "done_at": iso(l.done_at),
            }
            for l in a.logs.all()
        ],
    }