"""
SAVED PLACEMENT ELIGIBILITY (meeting point 10)

The reviewer asked for "a separate table to store placement eligibility
results for each student", updated "through a background job or when a
placement drive is added". This module is that table's only writer.

    check_eligibility()   eligibility.py  - DECIDES (the rules live only there)
    PlacementEligibility  models.py       - REMEMBERS the answer
    this module                           - keeps the two in step

When rows are refreshed
  * a drive is PUBLISHED            -> publish_drive(): its roles, then the
                                       "you're eligible" notices
  * a role / its rule is edited     -> signals.py queues that role
  * results published / changed,
    10th-12th verified, offer
    accepted or declined, a
    student's year / course changed -> signals.py queues that student
  * placement rules switched        -> everything
  * every night                     -> manage.py refresh_placement_eligibility
  * the officer's "Refresh" button  -> refresh_all()
  * a row is missing when read      -> worked out on the spot and saved

Reading never trusts a row for APPLYING: apply_to_role() still runs the live
check, so a stale row can never let an ineligible student apply.
"""
import logging
import threading

from django.db import transaction
from django.utils import timezone

from core.users.models import User

from .eligibility import check_eligibility
from .models import JobRole, PlacementEligibility

log = logging.getLogger(__name__)

# drives whose roles are kept fresh: officer sees drafts before publishing,
# students see published and closed drives in their list
REFRESHED_DRIVE_STATUSES = ("draft", "published", "closed")


# ===================== WHO / WHAT =====================
def candidates(qs):
    """
    The students the table holds. With "final-year students only" ON (the
    default) only a final-year student can ever be eligible, so only they are
    stored - 600 rows per role instead of 2,400, which keeps publishing and
    the officer's Refresh fast. Anyone else is worked out live when THEY look
    (one student, instant) and simply isn't in the officer's lists.
    """
    from django.db.models import Max, Q
    from core.academics.models import Year
    from .tiers import current_policy
    if not current_policy().final_year_only:
        return qs
    q = Q(pk__in=[])
    for course_id, last in Year.objects.values("course_id").annotate(m=Max("year_number")).values_list("course_id", "m"):
        q |= Q(course_id=course_id, year=last)
    return qs.filter(q)


def _is_candidate(student):
    return candidates(User.objects.filter(pk=student.pk, role="student", is_active=True)).exists()



def _roles(roles=None):
    qs = JobRole.objects.filter(is_active=True, drive__status__in=REFRESHED_DRIVE_STATUSES)
    if roles is not None:
        ids = [getattr(r, "id", r) for r in roles]
        qs = qs.filter(id__in=ids)
    return list(qs.select_related("drive__company").prefetch_related("eligibility__allowed_departments"))


def _students(students=None):
    qs = candidates(User.objects.filter(role="student", is_active=True))
    if students is not None:
        ids = [getattr(s, "id", s) for s in students]
        qs = qs.filter(id__in=ids)
    return list(qs.select_related("department", "course", "prior_academics"))


def _standing(student):
    from modules.exams.services import get_academic_standing
    return get_academic_standing(student)


def _payload(result):
    return {"eligible": result["eligible"], "blockers": result["blockers"], "checks": result["checks"]}


# ===================== WRITE =====================
def _save(results):
    """results: {(student_id, role_id): result}. Insert new rows, update the rest."""
    if not results:
        return 0
    now = timezone.now()
    student_ids = {s for s, _ in results}
    role_ids = {r for _, r in results}
    existing = {
        (row.student_id, row.job_role_id): row
        for row in PlacementEligibility.objects.filter(student_id__in=student_ids, job_role_id__in=role_ids)
    }
    new_rows, changed = [], []
    for (sid, rid), res in results.items():
        row = existing.get((sid, rid))
        if row is None:
            new_rows.append(PlacementEligibility(student_id=sid, job_role_id=rid, checked_at=now, **_payload(res)))
        else:
            row.eligible, row.blockers, row.checks = res["eligible"], res["blockers"], res["checks"]
            row.checked_at = now                 # bulk_update skips auto_now
            changed.append(row)
    PlacementEligibility.objects.bulk_create(new_rows, ignore_conflicts=True)
    PlacementEligibility.objects.bulk_update(changed, ["eligible", "blockers", "checks", "checked_at"], batch_size=500)
    return len(results)


def refresh(students=None, roles=None):
    """
    Work out and save eligibility for these students x these roles.
    None = every active student / every role of a draft, published or closed
    drive. Each student's academic standing is read ONCE for all roles.
    """
    role_list = _roles(roles)
    student_list = _students(students)
    # rows for students who stopped being candidates (graduated, made
    # inactive, rule switched on) would be stale - remove them
    keep = {s.id for s in student_list}
    stale = PlacementEligibility.objects.exclude(student_id__in=keep)
    if students is not None:
        stale = stale.filter(student_id__in=[getattr(x, "id", x) for x in students])
    if roles is not None:
        stale = stale.filter(job_role_id__in=[r.id for r in role_list] or [getattr(x, "id", x) for x in roles])
    stale.delete()
    if not role_list or not student_list:
        return {"students": len(student_list), "roles": len(role_list), "rows": 0}
    results = {}
    ctx = {}                                   # policy / final years / best offers, read once
    for s in student_list:
        standing = _standing(s)
        for r in role_list:
            results[(s.id, r.id)] = check_eligibility(s, r, standing=standing, ctx=ctx)
    rows = _save(results)
    return {"students": len(student_list), "roles": len(role_list), "rows": rows}


def refresh_all():
    """Everything - the nightly job and the officer's Refresh button."""
    return refresh()


# ===================== READ =====================
def results_for_student(student, roles):
    """
    {role_id: {"eligible", "blockers", "checks"}} for one student, from the
    table. Missing rows are worked out now and saved, so the answer is never
    empty and the table heals itself.
    """
    roles = list(roles)
    rows = {r.job_role_id: r for r in PlacementEligibility.objects.filter(
        student=student, job_role_id__in=[r.id for r in roles])}
    out, missing = {}, {}
    standing = None
    ctx = {}
    store_rows = _is_candidate(student)
    for role in roles:
        row = rows.get(role.id)
        if row is not None:
            out[role.id] = {"eligible": row.eligible, "blockers": row.blockers, "checks": row.checks}
            continue
        if standing is None:
            standing = _standing(student)
        res = check_eligibility(student, role, standing=standing, ctx=ctx)
        out[role.id] = _payload(res)
        if store_rows and role.drive.status in REFRESHED_DRIVE_STATUSES and role.is_active:
            missing[(student.id, role.id)] = res
    _save(missing)
    return out


def rows_for_role(role, students):
    """
    {student_id: PlacementEligibility} for these students and one role -
    candidates only (see candidates()). Missing rows are worked out now and saved.
    """
    allowed = set(candidates(User.objects.filter(role="student", is_active=True,
                                                  pk__in=[s.id for s in students])).values_list("id", flat=True))
    students = [s for s in students if s.id in allowed]
    rows = {r.student_id: r for r in PlacementEligibility.objects.filter(
        job_role=role, student_id__in=[s.id for s in students])}
    todo = [s for s in students if s.id not in rows]
    if todo:
        ctx = {}
        _save({(s.id, role.id): check_eligibility(s, role, ctx=ctx) for s in todo})
        rows.update({r.student_id: r for r in PlacementEligibility.objects.filter(
            job_role=role, student_id__in=[s.id for s in todo])})
    return rows


def last_checked(roles):
    """When the saved answers for these roles were last worked out (oldest row)."""
    from django.db.models import Min
    return PlacementEligibility.objects.filter(job_role__in=roles).aggregate(t=Min("checked_at"))["t"]


# ===================== PUBLISH =====================
def _notice(role):
    company = role.drive.company.name
    bits = [role.title]
    if role.package_lpa is not None:
        bits.append(f"{role.package_lpa} LPA")
    if role.drive.application_deadline:
        bits.append(f"apply by {timezone.localtime(role.drive.application_deadline):%d %b}")
    return f"You're eligible for {company}", " · ".join(bits)


def to_notify_count(drive):
    """How many students publishing this drive would notify (preview for the officer)."""
    roles = [r for r in drive.job_roles.all() if r.is_active]
    if not roles:
        return 0
    for role in roles:
        rows_for_role(role, _students())       # make sure every row exists
    return (PlacementEligibility.objects
            .filter(job_role__in=roles, eligible=True, notified_at__isnull=True, student__is_active=True)
            .values("student").distinct().count())


def publish_drive(drive):
    """
    Called when a drive changes to PUBLISHED: refresh its roles, then send each
    eligible student one in-app notice per role. A student already notified
    for a role (re-publishing) is skipped. Returns how many students were notified.
    """
    from core.notifications.services import notify

    roles = [r for r in drive.job_roles.select_related("drive__company") if r.is_active]
    if not roles:
        return 0
    refresh(roles=roles)
    notified = set()
    now = timezone.now()
    for role in roles:
        pending = list(PlacementEligibility.objects
                       .filter(job_role=role, eligible=True, notified_at__isnull=True, student__is_active=True)
                       .select_related("student"))
        if not pending:
            continue
        title, message = _notice(role)
        notify([p.student for p in pending], title, message, notif_type="placement", link="/student/placement")
        PlacementEligibility.objects.filter(pk__in=[p.pk for p in pending]).update(notified_at=now)
        notified.update(p.student_id for p in pending)
    return len(notified)


# ===================== QUEUE (used by signals.py) =====================
# Changes are collected during a request / transaction and refreshed ONCE
# after it commits - importing 600 results refreshes each student once, not
# once per row.
_local = threading.local()


def _pending():
    p = getattr(_local, "pending", None)
    if p is None:
        p = _local.pending = {"students": set(), "roles": set(), "all": False}
    return p


def queue(students=(), roles=(), everything=False):
    p = _pending()
    p["students"].update(s for s in students if s)
    p["roles"].update(r for r in roles if r)
    p["all"] = p["all"] or everything
    transaction.on_commit(_flush)     # extra callbacks find nothing left to do


def _flush():
    p = getattr(_local, "pending", None)
    _local.pending = None
    if not p or not (p["all"] or p["students"] or p["roles"]):
        return
    try:
        if p["all"]:
            refresh_all()
            return
        if p["roles"]:
            refresh(roles=p["roles"])
        if p["students"]:
            refresh(students=p["students"])
    except Exception:
        # the change itself is already saved; a failed refresh is healed by the
        # next read of that row or by the nightly job - but it must be visible
        log.exception("Placement eligibility refresh failed: %s", p)
