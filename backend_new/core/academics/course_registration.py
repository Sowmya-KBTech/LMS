"""
CBCS PART A - COURSE REGISTRATION: the rules and the API in one file.

How it works
  1. Admin opens a RegistrationWindow for a semester (all courses or some):
     dates, credit limits (with extra credits for a high CGPA), how many
     choices a student may rank, whether the HOD approves after the class
     in-charge, and how seats are given (by CGPA, or by who submitted first).
  2. A student ranks options in each elective group of their class (the
     existing ElectiveGroup / ElectiveOption). Core subjects are added for
     them. Credits are checked live. Submit -> class in-charge.
  3. The class in-charge (YearTutor of the class) approves or returns it with
     a comment. When the window asks for it, the HOD approves next. The HOD
     and the academic admin can act at any stage.
  4. After the window closes, the admin runs a TRIAL allocation (nothing is
     saved), may cancel options that too few students got, then confirms:
     each student gets the highest-ranked option with a free seat, in CGPA
     (or submission) order. Confirming enrols them (= Enrollment, so
     attendance, IA and results follow) and keeps a waitlist.
  5. When seats free up, "Fill from waitlist" moves waitlisted students up in
     order.

At confirm time, registrations still waiting for approval are approved
automatically when they pass every check; returned and unsubmitted ones get
nothing (staff can still allocate them on the Electives screen).

While a window covers an elective group, students can't use the old
"choose an elective" screen for it (see electives._check_allowed).
"""
import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.academics.permissions import can_manage_academics

from .electives import blocked_reason, in_class, passed_subjects
from .models import Course, Enrollment, Subject, YearTutor
from .models_electives import (
    CourseRegistration as Reg,
    ElectiveChange, ElectiveGroup, ElectiveOption, RegistrationChoice, RegistrationWindow,
)

MIN_COMMENT = 5
WAITING = (Reg.SUBMITTED, Reg.WITH_HOD)


class RegistrationError(Exception):
    """A rule was broken. The message is shown to the user as it is."""


# ============================================================ helpers ===
def _name(user):
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _num(value):
    """Decimal -> int when whole, else float (2 -> 2, 1.5 -> 1.5)."""
    if value is None:
        return None
    value = Decimal(value)
    return int(value) if value == value.to_integral() else float(value)


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def _when(dt):
    return timezone.localtime(dt).strftime("%d %b %Y, %I:%M %p") if dt else ""


def _notify(recipients, title, message, link):
    from core.notifications.services import notify
    notify(recipients, title, message, link=link)


# ============================================================ who / what ===
def window_courses(window):
    ids = list(window.courses.values_list("id", flat=True))
    return ids or list(Course.objects.values_list("id", flat=True))


def window_students(window):
    from core.users.models import User
    return (User.objects.filter(role="student", is_active=True, semester=window.semester,
                                course_id__in=window_courses(window))
            .select_related("course", "department").order_by("course__name", "roll_number", "username"))


def covers(window, student):
    return (student.semester == window.semester
            and student.course_id in window_courses(window))


def window_groups(window, student=None):
    """
    The elective groups in this window (a list): each covered class's own
    groups, plus open electives offered to any covered course (CBCS PART B).
    With a student: only the groups that student takes part in.
    """
    courses = window_courses(window)
    qs = (ElectiveGroup.objects
          .filter(Q(course_id__in=courses, open_elective=False) | Q(open_elective=True), semester=window.semester)
          .select_related("course", "year")
          .prefetch_related("options__teaching_assignment__subject__category",
                            "options__teaching_assignment__teacher", "options__teaching_assignment__course",
                            "options__requires", "open_to")
          .order_by("open_elective", "course__name", "name"))
    groups = list(qs)
    if student is not None:
        return [g for g in groups if in_class(student, g)]
    out = []
    for g in groups:
        audience = [c.id for c in g.open_to.all()]
        if not g.open_elective or not audience or set(audience) & set(courses):
            out.append(g)
    return out


def window_for_group(group):
    """The registration window that covers this elective group, if any."""
    for w in RegistrationWindow.objects.filter(semester=group.semester).prefetch_related("courses"):
        ids = [c.id for c in w.courses.all()]
        if group.open_elective:                                   # CBCS PART B
            audience = [c.id for c in group.open_to.all()]
            if not ids or not audience or set(ids) & set(audience):
                return w
        elif not ids or group.course_id in ids:
            return w
    return None


def current_window(student):
    """The newest window that covers this student (open, closed or allocated)."""
    for w in RegistrationWindow.objects.filter(semester=student.semester).prefetch_related("courses"):
        if covers(w, student):
            return w
    return None


def core_subjects(student):
    return list(Subject.objects.filter(year__course_id=student.course_id, year__year_number=student.year,
                                       semester=student.semester, is_elective=False)
                .select_related("category").order_by("code", "name"))


def is_tutor_of(user, student):
    return YearTutor.objects.filter(teacher=user, course_id=student.course_id,
                                    year__year_number=student.year).exists()


def is_hod_of(user, student):
    from core.users.acting_hod import hod_department_ids
    return bool(student.department_id) and student.department_id in hod_department_ids(user)


def can_act(user, reg):
    """May this user approve / return this registration now?"""
    if reg.status not in WAITING:
        return False
    if can_manage_academics(user) or is_hod_of(user, reg.student):
        return True
    return reg.status == Reg.SUBMITTED and is_tutor_of(user, reg.student)


def reviewable_students(user):
    """Students whose registrations this user may see on the approval screen."""
    from core.users.models import User
    qs = User.objects.filter(role="student", is_active=True)
    if can_manage_academics(user):
        return qs
    from core.users.acting_hod import hod_department_ids
    cond = Q(department_id__in=hod_department_ids(user))
    for course_id, year_no in YearTutor.objects.filter(teacher=user).values_list(
            "course_id", "year__year_number"):
        cond |= Q(course_id=course_id, year=year_no)
    return qs.filter(cond)


def is_reviewer(user):
    from core.users.acting_hod import is_hod
    return (can_manage_academics(user) or YearTutor.objects.filter(teacher=user).exists()
            or is_hod(user))


# ============================================================ seats ===
def seats_taken(option_ids):
    return dict(Enrollment.objects.filter(teaching_assignment__elective_option__id__in=option_ids)
                .values_list("teaching_assignment__elective_option__id")
                .annotate(n=Count("id")))


def first_choice_demand(window):
    return dict(RegistrationChoice.objects
                .filter(registration__window=window, rank=1, registration__status__in=WAITING + (Reg.APPROVED,))
                .values_list("option_id").annotate(n=Count("id")))


# ============================================================ credits / checks ===
def credit_limit(window, cgpa):
    if window.max_credits is None:
        return None
    extra = (window.extra_credits if window.extra_cgpa is not None and cgpa is not None
             and Decimal(str(cgpa)) >= window.extra_cgpa else 0)
    return window.max_credits + extra


def count_credits(student, groups, picked):
    """Core credits + for each group the credits of the first `picks` ranked options."""
    total = sum((s.credits for s in core_subjects(student)), Decimal(0))
    for g in groups:
        ranked = sorted(picked.get(g.id, []), key=lambda c: c[1])[:g.picks]
        total += sum((o.teaching_assignment.subject.credits for o, _ in ranked), Decimal(0))
    return total


def checks(window, student, groups, picked, cgpa=None, demand=None, seats=None):
    """
    [{code, text, blocking}] - blocking ones stop the submit and the
    automatic approval at allocation.
    """
    out = []
    credits = count_credits(student, groups, picked)
    limit = credit_limit(window, cgpa)
    for g in groups:
        have = len(picked.get(g.id, []))
        if have < g.picks:
            out.append({"code": "group_missing", "blocking": True,
                        "text": f"Choose {g.picks - have} more in {g.name}."})
    if credits < window.min_credits:
        out.append({"code": "below_min", "blocking": True,
                    "text": f"Below {_num(window.min_credits)} credits."})
    if limit is not None and credits > limit:
        out.append({"code": "above_max", "blocking": True,
                    "text": f"Above {_num(limit)} credits."})
    if demand is not None and seats is not None:
        for g in groups:
            first = [o for o, r in picked.get(g.id, []) if r == 1]
            for o in first:
                if o.seat_limit is not None and (demand.get(o.id, 0) + seats.get(o.id, 0)) > o.seat_limit:
                    out.append({"code": "first_full", "blocking": False,
                                "text": f"1st choice {o.teaching_assignment.subject.name} has more requests "
                                        f"than seats."})
    return out, credits, limit


def picked_of(reg):
    """{group_id: [(option, rank)]} from the saved choices."""
    out = {}
    for c in reg.choices.select_related("option__teaching_assignment__subject",
                                        "option__teaching_assignment__teacher"):
        out.setdefault(c.group_id, []).append((c.option, c.rank))
    return out


# ============================================================ student actions ===
def get_or_start(window, student):
    reg, _ = Reg.objects.get_or_create(window=window, student=student)
    return reg


@transaction.atomic
def save_choices(window, student, rows):
    """
    rows = [{"group": id, "option": id, "rank": n}]. Replaces all choices.
    Changing a submitted (or returned) registration takes it back to draft:
    the student must submit again.
    """
    if window.window_state() != "open":
        raise RegistrationError("The registration window is not open.")
    if not covers(window, student):
        raise RegistrationError("This registration is not for your class.")
    reg = Reg.objects.select_for_update().get(pk=get_or_start(window, student).pk)
    if reg.status == Reg.APPROVED:
        raise RegistrationError("Your registration is approved. Ask your class in-charge to return it "
                                "if you need a change.")

    groups = {g.id: g for g in window_groups(window, student)}
    options = {o.id: o for g in groups.values() for o in g.options.all()}
    passed = passed_subjects(student)
    seen_opt, seen_rank, per_group = set(), set(), {}
    clean = []
    for row in rows or []:
        try:
            gid, oid, rank = int(row.get("group")), int(row.get("option")), int(row.get("rank"))
        except (TypeError, ValueError, AttributeError):
            raise RegistrationError("Each choice needs a group, an option and a rank.")
        g, o = groups.get(gid), options.get(oid)
        if g is None or o is None or o.group_id != gid:
            raise RegistrationError("That elective is not offered to your class.")
        why = blocked_reason(student, o, passed)                  # CBCS PART B
        if why:
            raise RegistrationError(f"{o.teaching_assignment.subject.name}: {why}")
        if oid in seen_opt or (gid, rank) in seen_rank:
            raise RegistrationError(f"Each option and each rank can be used once in {g.name}.")
        per_group[gid] = per_group.get(gid, 0) + 1
        if per_group[gid] > max(window.max_ranks, g.picks):
            raise RegistrationError(f"You can rank at most {max(window.max_ranks, g.picks)} in {g.name}.")
        seen_opt.add(oid)
        seen_rank.add((gid, rank))
        clean.append((g, o, rank))

    # ranks become 1, 2, 3 ... in each group, in the order given
    clean.sort(key=lambda t: (t[0].id, t[2]))
    reg.choices.all().delete()
    n = {}
    objs = []
    for g, o, _ in clean:
        n[g.id] = n.get(g.id, 0) + 1
        objs.append(RegistrationChoice(registration=reg, group=g, option=o, rank=n[g.id]))
    RegistrationChoice.objects.bulk_create(objs)

    reg.credits = count_credits(student, groups.values(), picked_of(reg))
    if reg.status != Reg.DRAFT:
        reg.status = Reg.DRAFT
        reg.submitted_at = None
    reg.save()
    return reg


@transaction.atomic
def submit(window, student):
    if window.window_state() != "open":
        raise RegistrationError("The registration window is not open.")
    reg = Reg.objects.select_for_update().filter(window=window, student=student).first()
    if reg is None or (not reg.choices.exists() and window_groups(window, student)):
        raise RegistrationError("Choose your electives first.")
    if reg.status in WAITING + (Reg.APPROVED,):
        raise RegistrationError("Already submitted.")
    from modules.mentoring.utils import student_cgpa
    issues, credits, _ = checks(window, student, list(window_groups(window, student)), picked_of(reg),
                                cgpa=student_cgpa(student))
    blocking = [i["text"] for i in issues if i["blocking"]]
    if blocking:
        raise RegistrationError(" ".join(blocking))
    reg.credits = credits
    reg.status = Reg.SUBMITTED
    reg.submitted_at = timezone.now()
    reg.comment = ""
    reg.save()
    tutors = [t.teacher for t in YearTutor.objects.filter(
        course_id=student.course_id, year__year_number=student.year).select_related("teacher")]
    _notify(tutors, "Course registration to approve",
            f"{_name(student)} submitted their Semester {window.semester} registration.", "/my-class?tab=registration")
    return reg


# ============================================================ approvals ===
@transaction.atomic
def approve(reg, by):
    reg = Reg.objects.select_for_update().select_related("window", "student").get(pk=reg.pk)
    if not can_act(by, reg):
        raise RegistrationError("You can't approve this registration now.")
    now = timezone.now()
    staff_override = can_manage_academics(by) or is_hod_of(by, reg.student)
    if reg.status == Reg.SUBMITTED:
        reg.tutor_by, reg.tutor_at = by, now
        if reg.window.hod_approval and not staff_override:
            reg.status = Reg.WITH_HOD
            reg.save()
            from core.users.acting_hod import current_hod
            _notify([current_hod(reg.student.department)], "Course registration to approve",
                    f"{_name(reg.student)}'s registration was approved by the class in-charge.",
                    "/electives/manage?tab=registration")
            return reg
    reg.hod_by, reg.hod_at = (by, now) if staff_override else (reg.hod_by, reg.hod_at)
    reg.status = Reg.APPROVED
    reg.save()
    _notify([reg.student], "Course registration approved",
            f"Your Semester {reg.window.semester} registration is approved.", "/student/electives")
    return reg


@transaction.atomic
def send_back(reg, by, comment):
    reg = Reg.objects.select_for_update().select_related("window", "student").get(pk=reg.pk)
    comment = (comment or "").strip()
    if len(comment) < MIN_COMMENT:
        raise RegistrationError("Write a comment so the student knows what to change.")
    allowed = can_act(by, reg)
    # an approved registration can be returned (for a change) until allocation
    if reg.status == Reg.APPROVED and not reg.window.allocated_at:
        allowed = (can_manage_academics(by) or is_hod_of(by, reg.student) or is_tutor_of(by, reg.student))
    if not allowed:
        raise RegistrationError("You can't return this registration now.")
    reg.status = Reg.RETURNED
    reg.comment = comment[:1000]
    reg.returned_by = by
    reg.save()
    _notify([reg.student], "Course registration returned",
            f"{_name(by)}: {comment}", "/student/electives")
    return reg


# ============================================================ allocation ===
def allocate(window, skip=(), save=False, by=None):
    """
    Give seats. Nothing is saved unless save=True.
    skip = option ids that will not run (their students move to their next choice).
    Returns the report shown on the Allocation tab.
    """
    from modules.mentoring.utils import cgpa_map

    if window.allocated_at and not save:
        return saved_report(window)
    groups = list(window_groups(window))
    options = {o.id: o for g in groups for o in g.options.all()}
    skip = {int(s) for s in skip if int(s) in options}
    taken = seats_taken(list(options))
    free = {oid: (None if o.seat_limit is None else max(o.seat_limit - taken.get(oid, 0), 0))
            for oid, o in options.items()}

    students = list(window_students(window))
    regs = {r.student_id: r for r in Reg.objects.filter(window=window).prefetch_related(
        "choices__option__teaching_assignment__subject")}
    cgpas = cgpa_map(students)
    by_id = {s.id: s for s in students}

    # who takes part: approved, plus waiting ones that pass every check
    takers, auto_approve = [], []
    for sid, reg in regs.items():
        st = by_id.get(sid)
        if st is None:
            continue
        if reg.status == Reg.APPROVED:
            takers.append(reg)
        elif reg.status in WAITING:
            sgroups = [g for g in groups if in_class(st, g)]
            issues, _, _ = checks(window, st, sgroups, picked_of(reg), cgpa=cgpas.get(sid))
            if not any(i["blocking"] for i in issues):
                takers.append(reg)
                auto_approve.append(reg)

    far = timezone.now() + datetime.timedelta(days=36500)
    if window.allocation == RegistrationWindow.BY_CGPA:
        takers.sort(key=lambda r: (-(cgpas.get(r.student_id) or -1), r.submitted_at or far,
                                   by_id[r.student_id].roll_number or ""))
    else:
        takers.sort(key=lambda r: (r.submitted_at or far, by_id[r.student_id].roll_number or ""))

    held = {}           # (student_id, group_id) -> number of options already held in that group
    for sid, oid in Enrollment.objects.filter(
            student_id__in=list(by_id), teaching_assignment__elective_option__id__in=list(options)
    ).values_list("student_id", "teaching_assignment__elective_option__id"):
        key = (sid, options[oid].group_id)
        held[key] = held.get(key, 0) + 1

    results = {}        # choice id -> (result, waitlist_no)
    allotted = []       # (student, option)
    waitlists = {}      # option id -> count
    unplaced = []
    first_got = first_total = 0
    for reg in takers:
        st = by_id[reg.student_id]
        by_group = {}
        for c in reg.choices.all():
            by_group.setdefault(c.group_id, []).append(c)
        passed = passed_subjects(st)
        for g in groups:
            if not in_class(st, g):
                continue
            chosen = sorted(by_group.get(g.id, []), key=lambda c: c.rank)
            need = g.picks - held.get((st.id, g.id), 0)
            if need <= 0 or not chosen:
                continue
            got = 0
            for c in chosen:
                if got >= need:
                    results[c.id] = (RegistrationChoice.NOT_ALLOTTED, None)
                    continue
                oid = c.option_id
                if blocked_reason(st, options[oid], passed):          # CBCS PART B: e.g. prerequisite failed since
                    results[c.id] = (RegistrationChoice.NOT_ALLOTTED, None)
                    continue
                if oid not in skip and (free[oid] is None or free[oid] > 0):
                    if free[oid] is not None:
                        free[oid] -= 1
                    got += 1
                    results[c.id] = (RegistrationChoice.ALLOTTED, None)
                    allotted.append((st, options[oid]))
                    if c.rank == 1:
                        first_got += 1
                elif oid in skip:
                    results[c.id] = (RegistrationChoice.NOT_ALLOTTED, None)
                else:
                    waitlists[oid] = waitlists.get(oid, 0) + 1
                    results[c.id] = (RegistrationChoice.WAITLIST, waitlists[oid])
            first_total += 1
            if got < need:
                unplaced.append({"student": st.id, "name": _name(st), "roll_number": st.roll_number or "",
                                 "group": g.id, "group_name": g.name})

    demand = {}
    for reg in takers:
        for c in reg.choices.all():
            if c.rank == 1:
                demand[c.option_id] = demand.get(c.option_id, 0) + 1
    got_by_option = {}
    for _, o in allotted:
        got_by_option[o.id] = got_by_option.get(o.id, 0) + 1

    rows = []
    for g in groups:
        for o in g.options.all():
            filled = taken.get(o.id, 0) + got_by_option.get(o.id, 0)
            note = ""
            if o.id in skip:
                note = "cancelled"
            elif waitlists.get(o.id):
                note = "popular"
            elif filled < window.min_strength:
                note = "low"
            rows.append({
                "option": o.id, "group": g.id, "group_name": g.name, "course_name": g.course.name,
                "code": o.teaching_assignment.subject.code or "",
                "subject": o.teaching_assignment.subject.name,
                "teacher_name": _name(o.teaching_assignment.teacher),
                "seat_limit": o.seat_limit, "filled": filled, "first_choice": demand.get(o.id, 0),
                "waitlist": waitlists.get(o.id, 0), "note": note,
            })

    report = {
        "students": len(students),
        "submitted": sum(1 for r in regs.values() if r.status in WAITING + (Reg.APPROVED,)),
        "approved": sum(1 for r in regs.values() if r.status == Reg.APPROVED),
        "auto_approved": len(auto_approve),
        "taking_part": len(takers),
        "first_choice_pct": round(first_got * 100 / first_total) if first_total else 0,
        "unplaced": unplaced, "options": rows, "skip": sorted(skip),
        "allocated_at": window.allocated_at, "saved": False,
    }
    if not save:
        return report

    with transaction.atomic():
        w = RegistrationWindow.objects.select_for_update().get(pk=window.pk)
        if w.allocated_at:
            raise RegistrationError("Seats were already given for this window.")
        if w.window_state() != "closed":
            raise RegistrationError("Seats can be given only after the window closes.")
        now = timezone.now()
        Reg.objects.filter(pk__in=[r.pk for r in auto_approve]).update(status=Reg.APPROVED, hod_at=now)
        Enrollment.objects.bulk_create(
            [Enrollment(student=st, teaching_assignment_id=o.teaching_assignment_id) for st, o in allotted],
            ignore_conflicts=True)
        ElectiveChange.objects.bulk_create([
            ElectiveChange(student=st, group=o.group, to_option=o, changed_by=by,
                           reason=f"Course registration: {w.name}") for st, o in allotted])
        RegistrationChoice.objects.filter(registration__window=w).update(result="", waitlist_no=None)
        for cid, (res, no) in results.items():
            RegistrationChoice.objects.filter(pk=cid).update(result=res, waitlist_no=no)
        w.allocated_at, w.allocated_by = now, by
        w.save(update_fields=["allocated_at", "allocated_by"])
    _notify([by_id[r.student_id] for r in takers], "Electives allotted",
            f"Your electives for Semester {window.semester} are ready. See Course registration.",
            "/student/electives")
    report.update(saved=True, allocated_at=w.allocated_at)
    return report


def saved_report(window):
    """The Allocation tab after seats were given: what was saved, and who still has no seat."""
    groups = list(window_groups(window))
    options = {o.id: o for g in groups for o in g.options.all()}
    taken = seats_taken(list(options))
    choices = list(RegistrationChoice.objects.filter(registration__window=window)
                   .select_related("registration__student"))
    first, wait = {}, {}
    for c in choices:
        if c.rank == 1 and c.registration.status == Reg.APPROVED:
            first[c.option_id] = first.get(c.option_id, 0) + 1
        if c.result == RegistrationChoice.WAITLIST:
            wait[c.option_id] = wait.get(c.option_id, 0) + 1
    holding = set(Enrollment.objects.filter(teaching_assignment__elective_option__id__in=list(options))
                  .values_list("student_id", "teaching_assignment__elective_option__group_id"))
    unplaced, seen = [], set()
    first_got = first_total = 0
    for c in choices:
        reg = c.registration
        if reg.status != Reg.APPROVED or (reg.id, c.group_id) in seen:
            continue
        seen.add((reg.id, c.group_id))
        first_total += 1
        st = reg.student
        if any(x.registration_id == reg.id and x.group_id == c.group_id and x.rank == 1
               and x.result == RegistrationChoice.ALLOTTED for x in choices):
            first_got += 1
        if (st.id, c.group_id) not in holding:
            g = options[c.option_id].group
            unplaced.append({"student": st.id, "name": _name(st), "roll_number": st.roll_number or "",
                             "group": g.id, "group_name": g.name})
    rows = []
    for g in groups:
        for o in g.options.all():
            filled = taken.get(o.id, 0)
            rows.append({
                "option": o.id, "group": g.id, "group_name": g.name, "course_name": g.course.name,
                "code": o.teaching_assignment.subject.code or "", "subject": o.teaching_assignment.subject.name,
                "teacher_name": _name(o.teaching_assignment.teacher), "seat_limit": o.seat_limit,
                "filled": filled, "first_choice": first.get(o.id, 0), "waitlist": wait.get(o.id, 0),
                "note": "popular" if wait.get(o.id) else ("low" if filled < window.min_strength else ""),
            })
    regs = Reg.objects.filter(window=window)
    return {
        "students": window_students(window).count(),
        "submitted": regs.filter(status__in=WAITING + (Reg.APPROVED,)).count(),
        "approved": regs.filter(status=Reg.APPROVED).count(), "auto_approved": 0,
        "taking_part": regs.filter(status=Reg.APPROVED).count(),
        "first_choice_pct": round(first_got * 100 / first_total) if first_total else 0,
        "unplaced": unplaced, "options": rows, "skip": [],
        "allocated_at": window.allocated_at, "saved": True,
    }


@transaction.atomic
def fill_from_waitlist(window, by):
    """
    Seats that came free after allocation go to waitlisted students in order.
    A student who moves up leaves the lower-ranked option they held.
    Returns the number of students moved.
    """
    if not window.allocated_at:
        raise RegistrationError("Give seats first.")
    moved = 0
    waiting = (RegistrationChoice.objects
               .filter(registration__window=window, result=RegistrationChoice.WAITLIST)
               .select_related("option__teaching_assignment__subject", "registration__student", "group")
               .order_by("option_id", "waitlist_no"))
    for c in waiting:
        o = ElectiveOption.objects.select_for_update().get(pk=c.option_id)
        if o.seat_limit is not None and o.seats_taken >= o.seat_limit:
            continue
        st = c.registration.student
        lower = (RegistrationChoice.objects
                 .filter(registration=c.registration, group=c.group, rank__gt=c.rank,
                         result=RegistrationChoice.ALLOTTED).first())
        if lower is not None:
            Enrollment.objects.filter(student=st,
                                      teaching_assignment_id=lower.option.teaching_assignment_id).delete()
            lower.result = RegistrationChoice.NOT_ALLOTTED
            lower.save(update_fields=["result"])
        Enrollment.objects.get_or_create(student=st, teaching_assignment_id=o.teaching_assignment_id)
        ElectiveChange.objects.create(student=st, group=c.group, to_option=o,
                                      from_option=lower.option if lower else None, changed_by=by,
                                      reason="Moved up from the waitlist")
        # this student no longer waits for anything ranked below the new seat
        RegistrationChoice.objects.filter(registration=c.registration, group=c.group, rank__gt=c.rank,
                                          result=RegistrationChoice.WAITLIST).update(
            result=RegistrationChoice.NOT_ALLOTTED, waitlist_no=None)
        c.result, c.waitlist_no = RegistrationChoice.ALLOTTED, None
        c.save(update_fields=["result", "waitlist_no"])
        _notify([st], "Moved up from the waitlist",
                f"You now have {o.teaching_assignment.subject.name}.", "/student/electives")
        moved += 1
    # renumber what is left on each waitlist
    left = {}
    for c in (RegistrationChoice.objects.filter(registration__window=window, result=RegistrationChoice.WAITLIST)
              .order_by("option_id", "waitlist_no")):
        left[c.option_id] = left.get(c.option_id, 0) + 1
        if c.waitlist_no != left[c.option_id]:
            c.waitlist_no = left[c.option_id]
            c.save(update_fields=["waitlist_no"])
    return moved


# ============================================================ data shapes ===
def _option_row(o, seats, demand, picked_rank=None, show_demand=False, blocked=""):
    ta = o.teaching_assignment
    taken = seats.get(o.id, 0)
    left = None if o.seat_limit is None else max(o.seat_limit - taken, 0)
    row = {
        "id": o.id, "code": ta.subject.code or "", "subject": ta.subject.name,
        "credits": _num(ta.subject.credits), "teacher_name": _name(ta.teacher),
        "seat_limit": o.seat_limit, "seats_left": left, "rank": picked_rank,
        # CBCS PART B
        "category": ta.subject.category.code if ta.subject.category_id else "",
        "course_name": ta.course.name if ta.course_id else "", "blocked": blocked,
    }
    if show_demand:
        row["first_choice"] = demand.get(o.id, 0)
    return row


def window_data(w, full=False):
    data = {
        "id": w.id, "name": w.name, "semester": w.semester,
        "courses": [c.id for c in w.courses.all()],
        "course_names": [c.name for c in w.courses.all()],
        "opens_at": w.opens_at, "closes_at": w.closes_at, "state": w.window_state(),
        "min_credits": _num(w.min_credits), "max_credits": _num(w.max_credits),
        "extra_cgpa": _num(w.extra_cgpa), "extra_credits": _num(w.extra_credits),
        "allocation": w.allocation, "max_ranks": w.max_ranks, "hod_approval": w.hod_approval,
        "min_strength": w.min_strength, "allocated_at": w.allocated_at,
    }
    if full:
        groups = list(window_groups(w))
        data["groups"] = [{"id": g.id, "name": g.name, "course_name": g.course.name, "picks": g.picks,
                           "options": g.options.count()} for g in groups]
        counts = dict(Reg.objects.filter(window=w).values_list("status").annotate(n=Count("id")))
        total = window_students(w).count()
        started = sum(counts.values())
        data["progress"] = {"students": total, "not_started": total - started,
                            **{k: counts.get(k, 0) for k, _ in Reg.STATUS_CHOICES}}
    return data


def registration_view(window, student):
    """Everything the student screen needs."""
    from modules.mentoring.utils import student_cgpa
    reg = Reg.objects.filter(window=window, student=student).first()
    groups = list(window_groups(window, student))
    option_ids = [o.id for g in groups for o in g.options.all()]
    seats = seats_taken(option_ids)
    demand = first_choice_demand(window)
    picked = picked_of(reg) if reg else {}
    cgpa = student_cgpa(student)
    # after seats are given, "more requests than seats" is no longer useful
    live = None if window.allocated_at else demand
    issues, credits, limit = checks(window, student, groups, picked, cgpa=cgpa, demand=live, seats=seats)
    results = {}
    if reg and window.allocated_at:
        for c in reg.choices.all():
            results[c.option_id] = {"result": c.result, "waitlist_no": c.waitlist_no}
    group_rows = []
    passed = passed_subjects(student)
    for g in groups:
        ranks = {o.id: r for o, r in picked.get(g.id, [])}
        rows = [_option_row(o, seats, demand, ranks.get(o.id), show_demand=True,
                            blocked=blocked_reason(student, o, passed)) for o in g.options.all()]
        for r in rows:
            r.update(results.get(r["id"], {}))
        group_rows.append({"id": g.id, "name": g.name, "picks": g.picks, "open_elective": g.open_elective,
                           "options": rows})
    return {
        "window": window_data(window),
        "student": {"name": _name(student), "roll_number": student.roll_number or "",
                    "course_name": student.course.name if student.course_id else "",
                    "semester": student.semester, "cgpa": cgpa},
        "core": [{"code": s.code or "", "name": s.name, "credits": _num(s.credits),
                  "ltp": f"{s.lecture_hours}-{s.tutorial_hours}-{s.practical_hours}",
                  "category": s.category.code if s.category_id else ""}
                 for s in core_subjects(student)],
        "degree": degree_progress(student),
        "groups": group_rows,
        "status": reg.status if reg else Reg.DRAFT,
        "status_label": reg.get_status_display() if reg else "Not submitted",
        "submitted_at": reg.submitted_at if reg else None,
        # a returned registration keeps its comment while the student edits it
        "comment": reg.comment if reg and reg.status in (Reg.RETURNED, Reg.DRAFT) else "",
        "returned_by": _name(reg.returned_by) if reg and reg.comment and reg.status in (Reg.RETURNED, Reg.DRAFT)
        else "",
        "tutor_at": reg.tutor_at if reg else None,
        "credits": _num(credits), "limit": _num(limit), "min_credits": _num(window.min_credits),
        "issues": issues,
        "can_edit": window.window_state() == "open" and (reg is None or reg.status != Reg.APPROVED),
    }


def degree_progress(student):
    """
    CBCS PART B: credits earned so far per category against the regulation's
    requirement (the same numbers as My credits). None when the regulation
    has no credit requirements for the student's course.
    """
    try:
        from modules.exams.grading import semester_summary
        summary = semester_summary(student)
    except Exception:
        return None
    if not summary.get("regulation") or not summary.get("credits_required"):
        return None
    return {"regulation": summary["regulation"]["name"],
            "required": summary["credits_required"], "earned": summary["credits_earned"],
            "categories": [{"code": c["code"], "name": c["name"], "required": c["required"], "earned": c["earned"]}
                           for c in summary["categories"]]}


def review_row(reg, cgpa, groups, demand, seats):
    st = reg.student
    picked = picked_of(reg)
    sgroups = [g for g in groups if in_class(st, g)]
    issues, credits, _ = checks(reg.window, st, sgroups, picked, cgpa=cgpa, demand=demand, seats=seats)
    return {
        "id": reg.id, "student": st.id, "name": _name(st), "roll_number": st.roll_number or "",
        "course_name": st.course.name if st.course_id else "", "cgpa": cgpa,
        "credits": _num(credits), "status": reg.status, "status_label": reg.get_status_display(),
        "comment": reg.comment, "submitted_at": reg.submitted_at,
        "choices": [{"group": g.name, "options": [o.teaching_assignment.subject.name
                                                   for o, _ in sorted(picked.get(g.id, []), key=lambda t: t[1])]}
                    for g in sgroups],
        "issues": issues, "ok": not any(i["blocking"] for i in issues),
    }


# ============================================================ API: student ===
def _parse_choices(data):
    rows = data.get("choices")
    if not isinstance(rows, list):
        raise RegistrationError("Send the list of choices.")
    return rows


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def my_registration(request):
    user = request.user
    if user.role != "student":
        return _error("Only students register for courses.", status.HTTP_403_FORBIDDEN)
    window = current_window(user)
    if window is None:
        return Response({"window": None})
    if request.method == "PUT":
        try:
            save_choices(window, user, _parse_choices(request.data))
        except RegistrationError as exc:
            return _error(str(exc))
    return Response(registration_view(window, user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_submit(request):
    user = request.user
    window = current_window(user) if user.role == "student" else None
    if window is None:
        return _error("There is no registration for you now.")
    try:
        if "choices" in request.data:
            save_choices(window, user, _parse_choices(request.data))
        submit(window, user)
    except RegistrationError as exc:
        return _error(str(exc))
    return Response(registration_view(window, user))


# ============================================================ API: approvers ===
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def review_list(request):
    """
    ?window=<id>&tab=waiting|returned|approved|not_submitted
    Class in-charge: their classes. HOD: their department. Admin: everyone.
    """
    from modules.mentoring.utils import cgpa_map
    user = request.user
    if not is_reviewer(user):
        return _error("Only class in-charges, HODs and the academic admin approve registrations.",
                      status.HTTP_403_FORBIDDEN)
    windows = [w for w in RegistrationWindow.objects.filter(allocated_at__isnull=True)
               .prefetch_related("courses")]
    wid = request.query_params.get("window")
    if wid:
        windows = [w for w in RegistrationWindow.objects.filter(pk=wid).prefetch_related("courses")]
    if not windows:
        return Response({"windows": [], "window": None, "rows": [], "counts": {}})
    window = windows[0]
    students = reviewable_students(user).filter(semester=window.semester,
                                                course_id__in=window_courses(window))
    regs = list(Reg.objects.filter(window=window, student__in=students)
                .select_related("student__course", "window", "returned_by")
                .prefetch_related("choices__option__teaching_assignment__subject"))
    tab = request.query_params.get("tab", "waiting")
    hod_or_admin = can_manage_academics(user)

    def waiting_for_me(r):
        return can_act(user, r) and (r.status == Reg.SUBMITTED or hod_or_admin or is_hod_of(user, r.student))

    counts = {
        "waiting": sum(1 for r in regs if waiting_for_me(r)),
        "returned": sum(1 for r in regs if r.status == Reg.RETURNED),
        "approved": sum(1 for r in regs if r.status == Reg.APPROVED),
    }
    started = {r.student_id for r in regs if r.status != Reg.DRAFT}
    not_sub = [s for s in students.select_related("course").order_by("roll_number") if s.id not in started]
    counts["not_submitted"] = len(not_sub)

    if tab == "not_submitted":
        rows = [{"student": s.id, "name": _name(s), "roll_number": s.roll_number or "",
                 "course_name": s.course.name if s.course_id else ""} for s in not_sub]
    else:
        pick = {"waiting": waiting_for_me,
                "returned": lambda r: r.status == Reg.RETURNED,
                "approved": lambda r: r.status == Reg.APPROVED}.get(tab, waiting_for_me)
        chosen = [r for r in regs if pick(r)]
        groups = list(window_groups(window))
        seats = seats_taken([o.id for g in groups for o in g.options.all()])
        demand = first_choice_demand(window)
        cg = cgpa_map([r.student_id for r in chosen])
        rows = [review_row(r, cg.get(r.student_id), groups, demand, seats) for r in chosen]
        for row, r in zip(rows, chosen):
            row["can_act"] = can_act(user, r)
            row["can_return"] = can_act(user, r) or (r.status == Reg.APPROVED and not window.allocated_at)
        rows.sort(key=lambda x: x["roll_number"])
    return Response({"windows": [{"id": w.id, "name": w.name} for w in windows],
                     "window": window_data(window), "rows": rows, "counts": counts, "tab": tab})


def _reg_or_404(pk):
    return Reg.objects.select_related("window", "student").filter(pk=pk).first()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_approve(request, pk):
    reg = _reg_or_404(pk)
    if reg is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    try:
        reg = approve(reg, request.user)
    except RegistrationError as exc:
        return _error(str(exc))
    return Response({"status": reg.status, "status_label": reg.get_status_display()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_return(request, pk):
    reg = _reg_or_404(pk)
    if reg is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    try:
        reg = send_back(reg, request.user, request.data.get("comment", ""))
    except RegistrationError as exc:
        return _error(str(exc))
    return Response({"status": reg.status, "status_label": reg.get_status_display()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_approve_ok(request):
    """Approve every waiting registration in `ids` that has no problems."""
    from modules.mentoring.utils import cgpa_map
    ids = request.data.get("ids") or []
    regs = list(Reg.objects.filter(pk__in=[i for i in ids if str(i).isdigit()])
                .select_related("window", "student"))
    cg = cgpa_map([r.student_id for r in regs])
    done = skipped = 0
    for r in regs:
        st = r.student
        issues, _, _ = checks(r.window, st, list(window_groups(r.window, st)), picked_of(r), cgpa=cg.get(st.id))
        if any(i["blocking"] for i in issues) or not can_act(request.user, r):
            skipped += 1
            continue
        approve(r, request.user)
        done += 1
    return Response({"approved": done, "skipped": skipped})


# ============================================================ API: admin ===
def _dec(value, field, errors, allow_blank=True):
    if value in (None, ""):
        if not allow_blank:
            errors[field] = "Required."
        return None
    try:
        d = Decimal(str(value))
    except Exception:
        errors[field] = "Enter a number."
        return None
    if d < 0:
        errors[field] = "Can't be negative."
    return d


def _bool(value):
    return value in (True, "true", "True", "1", 1, "on")


def _apply(w, data, creating):
    errors = {}
    if creating or "name" in data:
        w.name = (data.get("name") or "").strip()[:60]
        if not w.name:
            errors["name"] = "Give the window a name."
        elif RegistrationWindow.objects.filter(name__iexact=w.name).exclude(pk=w.pk).exists():
            errors["name"] = "That name is taken."
    if creating or "semester" in data:
        try:
            w.semester = int(data.get("semester"))
            if not 1 <= w.semester <= 10:
                raise ValueError
        except (TypeError, ValueError):
            errors["semester"] = "Choose a semester."
    for f in ("opens_at", "closes_at"):
        if creating or f in data:
            v = data.get(f)
            dt = parse_datetime(v) if isinstance(v, str) else v
            if dt is not None and timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            if dt is None:
                errors[f] = "Enter a date and time."
            else:
                setattr(w, f, dt)
    for f, blank in (("min_credits", False), ("max_credits", True), ("extra_cgpa", True),
                     ("extra_credits", False)):
        if creating or f in data:
            v = _dec(data.get(f), f, errors, allow_blank=True)
            setattr(w, f, v if v is not None or blank else Decimal(0))
    if creating or "allocation" in data:
        a = data.get("allocation") or RegistrationWindow.BY_CGPA
        if a not in dict(RegistrationWindow.ALLOCATION_CHOICES):
            errors["allocation"] = "Choose how seats are given."
        w.allocation = a
    for f, lo, hi in (("max_ranks", 1, 10), ("min_strength", 0, 500)):
        if f in data:
            try:
                v = int(data.get(f))
                if not lo <= v <= hi:
                    raise ValueError
                setattr(w, f, v)
            except (TypeError, ValueError):
                errors[f] = f"Enter {lo} to {hi}."
    if "hod_approval" in data:
        w.hod_approval = _bool(data.get("hod_approval"))
    # cross-field checks always run
    if w.opens_at and w.closes_at and w.closes_at <= w.opens_at:
        errors.setdefault("closes_at", "Must be after the opening time.")
    if w.max_credits is not None and w.min_credits is not None and w.max_credits < w.min_credits:
        errors.setdefault("max_credits", "Must be at least the minimum.")
    if w.extra_cgpa is not None and w.extra_cgpa > 10:
        errors.setdefault("extra_cgpa", "CGPA is out of 10.")
    return errors


def _overlap(w, course_ids):
    """Another not-yet-allocated window for the same semester and a shared course?"""
    for other in (RegistrationWindow.objects.filter(semester=w.semester, allocated_at__isnull=True)
                  .exclude(pk=w.pk).prefetch_related("courses")):
        theirs = {c.id for c in other.courses.all()}
        if not course_ids or not theirs or theirs & set(course_ids):
            return other
    return None


def _save_window(request, w, creating):
    data = request.data
    errors = _apply(w, data, creating)
    course_ids = None
    if creating or "courses" in data:
        course_ids = [int(c) for c in (data.get("courses") or []) if str(c).isdigit()]
        if Course.objects.filter(pk__in=course_ids).count() != len(set(course_ids)):
            errors["courses"] = "Unknown course."
    if not errors:
        ids = course_ids if course_ids is not None else [c.id for c in w.courses.all()] if w.pk else []
        other = _overlap(w, ids)
        if other is not None:
            errors["courses"] = f"'{other.name}' already covers these students for Semester {w.semester}."
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    if creating:
        w.created_by = request.user
    w.save()
    if course_ids is not None:
        w.courses.set(course_ids)
    return Response(window_data(w, full=True), status=201 if creating else 200)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def window_list(request):
    if request.method == "GET":
        if not (can_manage_academics(request.user) or is_reviewer(request.user)):
            return _error("Not allowed.", status.HTTP_403_FORBIDDEN)
        return Response([window_data(w) for w in RegistrationWindow.objects.prefetch_related("courses")])
    if not can_manage_academics(request.user):
        return _error("Only the academic admin opens registration.", status.HTTP_403_FORBIDDEN)
    return _save_window(request, RegistrationWindow(), creating=True)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def window_detail(request, pk):
    w = RegistrationWindow.objects.prefetch_related("courses").filter(pk=pk).first()
    if w is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        if not (can_manage_academics(request.user) or is_reviewer(request.user)):
            return _error("Not allowed.", status.HTTP_403_FORBIDDEN)
        return Response(window_data(w, full=True))
    if not can_manage_academics(request.user):
        return _error("Only the academic admin changes registration.", status.HTTP_403_FORBIDDEN)
    if w.allocated_at:
        return _error("Seats were already given; this window can't change now.")
    if request.method == "DELETE":
        if w.registrations.exclude(status=Reg.DRAFT).exists():
            return _error("Students have submitted registrations in this window.")
        w.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if w.registrations.exists() and "semester" in request.data and int(request.data["semester"]) != w.semester:
        return _error("Students have started registering; the semester can't change.")
    return _save_window(request, w, creating=False)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def window_allocation(request, pk):
    """GET ?skip=1,2 -> trial (nothing saved). POST {skip: [..]} -> give seats and enrol."""
    if not can_manage_academics(request.user):
        return _error("Only the academic admin gives seats.", status.HTTP_403_FORBIDDEN)
    w = RegistrationWindow.objects.prefetch_related("courses").filter(pk=pk).first()
    if w is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        skip = [s for s in (request.query_params.get("skip") or "").split(",") if s.strip().isdigit()]
        return Response(allocate(w, skip=skip))
    skip = [s for s in (request.data.get("skip") or []) if str(s).isdigit()]
    try:
        return Response(allocate(w, skip=skip, save=True, by=request.user))
    except RegistrationError as exc:
        return _error(str(exc))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def window_fill_waitlist(request, pk):
    if not can_manage_academics(request.user):
        return _error("Only the academic admin moves the waitlist.", status.HTTP_403_FORBIDDEN)
    w = RegistrationWindow.objects.filter(pk=pk).first()
    if w is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    try:
        moved = fill_from_waitlist(w, request.user)
    except RegistrationError as exc:
        return _error(str(exc))
    return Response({"moved": moved})


# ============================================================ CBCS PART B: report ===
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def window_student_list(request, pk):
    """
    Every student the window covers: class, status, credits, and per elective
    group what they ranked and what they got. The Download student list button
    makes the Excel (CSV) file from this.
    """
    if not (can_manage_academics(request.user) or is_reviewer(request.user)):
        return _error("Not allowed.", status.HTTP_403_FORBIDDEN)
    w = RegistrationWindow.objects.prefetch_related("courses").filter(pk=pk).first()
    if w is None:
        return _error("Not found.", status.HTTP_404_NOT_FOUND)
    students = window_students(w)
    if not can_manage_academics(request.user):
        students = students.filter(pk__in=reviewable_students(request.user))
    groups = window_groups(w)
    options = {o.id: o for g in groups for o in g.options.all()}
    regs = {r.student_id: r for r in Reg.objects.filter(window=w).prefetch_related("choices")}
    held = {}
    for sid, oid in Enrollment.objects.filter(
            student__in=students, teaching_assignment__elective_option__id__in=list(options)
    ).values_list("student_id", "teaching_assignment__elective_option__id"):
        held.setdefault((sid, options[oid].group_id), []).append(options[oid].teaching_assignment.subject.name)
    rows = []
    for st in students:
        reg = regs.get(st.id)
        choices = {}
        if reg:
            for c in sorted(reg.choices.all(), key=lambda c: c.rank):
                label = options[c.option_id].teaching_assignment.subject.name if c.option_id in options else "?"
                if c.result == RegistrationChoice.WAITLIST:
                    label += f" (waitlist #{c.waitlist_no})"
                choices.setdefault(c.group_id, []).append(label)
        rows.append({
            "name": _name(st), "roll_number": st.roll_number or "",
            "course_name": st.course.name if st.course_id else "",
            "status": reg.get_status_display() if reg else "Not started",
            "credits": _num(reg.credits) if reg else None,
            "groups": [{"group": g.name, "ranked": choices.get(g.id, []), "got": held.get((st.id, g.id), [])}
                       for g in groups if in_class(st, g)],
        })
    return Response({"window": w.name, "rows": rows})
