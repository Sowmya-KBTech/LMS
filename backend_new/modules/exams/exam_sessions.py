"""WAVE 3 PART 2 - exam sessions: registration, the session timetable and its
clash check, and the papers a hall ticket lists.

One exam season ("Nov/Dec 2026") is an ExamSession. Exactly one is current.
A student's papers in a session are
  * regular - this semester's subjects (automatic, the student only confirms)
  * arrear  - subjects from published results that are not passed yet
    (RA / absent ...), which the student ticks (or the exam cell adds all).
The timetable has ONE slot per subject per session: an arrear student writes
the same CS301 paper as the Sem 3 class. So a clash is a student whose papers
share a date + session - which only the registrations can tell us.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (ExamRegistration, ExamRegistrationPaper, ExamSchedule,
                     ExamSession, ResultEntry)

SESSION_ORDER = {"FN": 0, "AN": 1}
FEE_TERM_PREFIX = "Exam fee - "


# ---------------------------------------------------------------- sessions
def current_session():
    return ExamSession.objects.filter(is_current=True).order_by("-id").first()


def schedule_rows(session):
    """The timetable rows of a session (no session = the rows saved before
    sessions existed)."""
    qs = ExamSchedule.objects.select_related("subject")
    return qs.filter(exam_session=session) if session else qs.filter(exam_session__isnull=True)


def window_state(session, today=None):
    """not_required | not_open | open | late | closed"""
    today = today or timezone.localdate()
    if not session.registration_required:
        return "not_required"
    if session.registration_closed:
        return "closed"
    if not session.reg_opens or today < session.reg_opens:
        return "not_open"
    if session.reg_closes is None or today <= session.reg_closes:
        return "open"
    if session.late_until and today <= session.late_until:
        return "late"
    return "closed"


def writes_regular(session, student):
    if session.kind != "regular" or not student.semester:
        return False
    return not session.semesters or student.semester in session.semesters


def fee_term(session):
    return (FEE_TERM_PREFIX + session.name)[:50]


# ---------------------------------------------------------------- a student's papers
def current_subjects(student):
    """This semester's subjects: the student's enrolments (so electives are
    right), or the class's subjects when there are no enrolments."""
    from core.academics.models import Enrollment, Subject
    subs = {}
    for e in Enrollment.objects.filter(student=student).select_related("teaching_assignment__subject"):
        s = e.teaching_assignment.subject
        if s.semester == student.semester:
            subs[s.id] = s
    if not subs and student.course_id and student.year and student.semester:
        for s in Subject.objects.filter(year__course_id=student.course_id, year__year_number=student.year,
                                        semester=student.semester):
            subs[s.id] = s
    return sorted(subs.values(), key=lambda s: (s.code or "", s.name))


def arrear_entries(student, exclude_ids=()):
    """Published, not-passed, not-withdrawn subjects - the arrears."""
    qs = (ResultEntry.objects
          .filter(result__student=student, result__is_published=True, is_pass=False)
          .exclude(outcome="excluded").exclude(subject_id__in=list(exclude_ids))
          .select_related("subject", "result").prefetch_related("attempts")
          .order_by("result__semester", "subject__code", "subject__name"))
    return list(qs)


def _subject_row(s):
    return {"id": s.id, "code": s.code or "", "name": s.name, "semester": s.semester,
            "credits": float(s.credits or 0)}


def _slot(row):
    return {"exam_date": row.exam_date.isoformat(), "session": row.session} if row else {"exam_date": None, "session": None}


def _subject_attendance(student, subject):
    from .views import Attendance
    rec = Attendance.objects.filter(student=student, teaching_assignment__subject=subject)
    total = rec.count()
    if not total:
        return None
    return round(rec.filter(status__in=["present", "duty_leave"]).count() * 100 / total, 1)


def _fee_payload(fee):
    if fee is None:
        return None
    return {"id": fee.id, "amount": float(fee.amount), "paid_amount": float(fee.paid_amount),
            "status": fee.status, "term": fee.term}


def is_complete(reg):
    return bool(reg and reg.status == "submitted" and (reg.fee_id is None or reg.fee.status == "paid"))


def fee_amount(session, n_regular, n_arrear, late):
    if not session.fee_required:
        return Decimal("0")
    total = session.regular_fee * n_regular + session.arrear_fee * n_arrear
    if late and (n_regular or n_arrear):
        total += session.late_fee
    return total


def registration_view(session, student):
    """Everything the student's registration screen needs."""
    from .views import _can_sit_exam, _rules
    reg = (ExamRegistration.objects.filter(exam_session=session, student=student)
           .select_related("fee").prefetch_related("papers").first())
    slots = {r.subject_id: r for r in schedule_rows(session)}
    picked = {p.subject_id for p in reg.papers.all() if p.kind == "arrear"} if reg else set()

    regular = []
    reg_ids = set()
    if writes_regular(session, student):
        for s in current_subjects(student):
            reg_ids.add(s.id)
            regular.append({**_subject_row(s), **_slot(slots.get(s.id)),
                            "attendance": _subject_attendance(student, s)})

    arrears = []
    for e in arrear_entries(student, exclude_ids=reg_ids):
        history = [{"attempt": a.attempt, "exam_session": a.exam_session, "grade": a.grade}
                   for a in e.attempts.all()]
        history.append({"attempt": e.attempt, "exam_session": e.exam_session,
                        "grade": e.grade or ("AB" if e.marks_obtained is None else "")})
        arrears.append({**_subject_row(e.subject), **_slot(slots.get(e.subject_id)),
                        "grade": e.grade or ("AB" if e.marks_obtained is None else "RA"),
                        "next_attempt": e.attempt + 1, "attempts": history,
                        "internal_marks": e.internal_marks,
                        "picked": (e.subject_id in picked) if session.students_pick_arrears else True})

    eligible, pct, reason = _can_sit_exam(student, _rules()) if regular else (True, None, "attendance")
    state = window_state(session)
    n_arrear = sum(1 for a in arrears if a["picked"])
    late = reg.is_late if (reg and reg.status == "submitted") else state == "late"
    fee = reg.fee if reg else None
    return {
        "session": session_payload(session),
        "window": state,
        "student": {"id": student.id, "name": getattr(student, "display_name", "") or student.username,
                    "roll_number": student.roll_number, "semester": student.semester},
        "writes_regular": bool(regular),
        "regular": regular,
        "arrears": arrears,
        "can_pick_arrears": session.students_pick_arrears,
        "eligible": eligible, "attendance_percent": pct, "eligibility_reason": reason,
        "status": reg.status if reg else "none",
        "is_late": late,
        "complete": is_complete(reg),
        "fee": _fee_payload(fee),
        "fee_preview": {
            "regular_papers": len(regular), "arrear_papers": n_arrear,
            "regular_fee": float(session.regular_fee), "arrear_fee": float(session.arrear_fee),
            "late_fee": float(session.late_fee) if late else 0,
            "total": float(fee_amount(session, len(regular), n_arrear, late)),
        },
        "locked": bool(fee and (fee.status == "paid" or fee.paid_amount > 0)),
    }


class RegistrationError(Exception):
    pass


@transaction.atomic
def save_registration(session, student, arrear_ids, submit):
    """Save (and optionally submit) a student's papers. Raises RegistrationError."""
    from modules.fees.models import Fee
    state = window_state(session)
    if state not in ("open", "late"):
        raise RegistrationError({
            "not_required": "This exam session does not use registration.",
            "not_open": "Registration has not opened yet.",
            "closed": "Registration is closed. Please contact the exam cell.",
        }[state])
    reg, _ = ExamRegistration.objects.select_for_update().get_or_create(exam_session=session, student=student)
    if reg.fee_id and (reg.fee.status == "paid" or reg.fee.paid_amount > 0):
        raise RegistrationError("Your exam fee is paid, so the registration is final. Ask the exam cell to change it.")

    regular = [s.id for s in current_subjects(student)] if writes_regular(session, student) else []
    arrears = {e.subject_id for e in arrear_entries(student, exclude_ids=regular)}
    if session.students_pick_arrears:
        wanted = set()
        for x in arrear_ids or []:
            try:
                wanted.add(int(x))
            except (TypeError, ValueError):
                raise RegistrationError("Arrear subjects must be a list of subject ids.")
        unknown = wanted - arrears
        if unknown:
            raise RegistrationError("You can only register for your own arrear subjects.")
    else:
        wanted = arrears
    if not regular and not wanted:
        raise RegistrationError("There is nothing to register for in this session."
                                if not arrears else "Tick at least one arrear subject.")

    reg.papers.all().delete()
    ExamRegistrationPaper.objects.bulk_create(
        [ExamRegistrationPaper(registration=reg, subject_id=s, kind="regular") for s in regular]
        + [ExamRegistrationPaper(registration=reg, subject_id=s, kind="arrear") for s in sorted(wanted)])

    if submit:
        late = state == "late"
        reg.status = "submitted"
        reg.is_late = late
        reg.submitted_at = timezone.now()
        amount = fee_amount(session, len(regular), len(wanted), late)
        if amount > 0:
            due = session.late_until or session.reg_closes or (timezone.localdate() + datetime.timedelta(days=14))
            fee = reg.fee
            if fee is None:
                fee = Fee.objects.filter(student=student, term=fee_term(session)).first()
            if fee is None:
                fee = Fee.objects.create(student=student, term=fee_term(session), amount=amount,
                                         due_date=due, status="pending")
            elif fee.amount != amount:
                fee.amount = amount
                fee.save(update_fields=["amount"])
            reg.fee = fee
        else:
            if reg.fee_id:
                old = reg.fee
                reg.fee = None
                reg.save(update_fields=["fee"])
                old.delete()
            reg.fee = None
    reg.save()
    return reg


# ---------------------------------------------------------------- the session timetable
def students_by_subject(session):
    """{subject_id: {student_id, ...}} for everyone who writes in the session:
    registrations, plus - for students who have not registered yet - their
    class's subjects (they will register for those anyway)."""
    from django.contrib.auth import get_user_model
    from core.academics.models import Subject
    User = get_user_model()
    takers = defaultdict(set)
    registered = set()
    for p in ExamRegistrationPaper.objects.filter(registration__exam_session=session).values(
            "subject_id", "registration__student_id"):
        takers[p["subject_id"]].add(p["registration__student_id"])
        registered.add(p["registration__student_id"])
    if session.kind == "regular":
        class_subjects = defaultdict(list)
        for s in Subject.objects.values("id", "year__course_id", "year__year_number", "semester"):
            class_subjects[(s["year__course_id"], s["year__year_number"], s["semester"])].append(s["id"])
        students = User.objects.filter(role="student").exclude(id__in=registered)
        if session.semesters:
            students = students.filter(semester__in=session.semesters)
        for st in students.values("id", "course_id", "year", "semester"):
            for sid in class_subjects.get((st["course_id"], st["year"], st["semester"]), []):
                takers[sid].add(st["id"])
    return takers


def _session_dates(session, rows):
    from .views import _working_dates
    start = session.exam_start or (min(r.exam_date for r in rows) if rows else None)
    end = session.exam_end or (max(r.exam_date for r in rows) if rows else None)
    if not start or not end:
        return []
    return _working_dates(start, end)


def free_slots(subject_id, takers, busy, dates, near=None, limit=3, skip=None):
    """Slots (date, FN/AN) where nobody who writes this subject has another paper."""
    studs = takers.get(subject_id, set())
    out = []
    for d in dates:
        for ss in ("FN", "AN"):
            key = (d, ss)
            if skip and key == skip:
                continue
            if any(key in busy[s] for s in studs):
                continue
            out.append(key)
    if near:
        out.sort(key=lambda k: (abs((k[0] - near[0]).days), SESSION_ORDER[k[1]] != SESSION_ORDER[near[1]], k[0]))
    return [{"exam_date": d.isoformat(), "session": ss} for d, ss in out[:limit]]


def timetable_check(session):
    """The whole session's timetable with its clashes and unscheduled papers."""
    from django.contrib.auth import get_user_model
    from core.academics.models import Subject
    User = get_user_model()
    rows = list(schedule_rows(session).select_related("subject"))
    slot = {r.subject_id: (r.exam_date, r.session) for r in rows}
    takers = students_by_subject(session)
    busy = defaultdict(lambda: defaultdict(set))   # student -> slot -> subjects
    for sid, studs in takers.items():
        if sid in slot:
            for st in studs:
                busy[st][slot[sid]].add(sid)
    arrear_count = defaultdict(int)
    for p in ExamRegistrationPaper.objects.filter(registration__exam_session=session, kind="arrear").values("subject_id"):
        arrear_count[p["subject_id"]] += 1

    # group clashing students by (slot, the subjects that clash)
    groups = defaultdict(set)
    for st, by_slot in busy.items():
        for key, subs in by_slot.items():
            if len(subs) > 1:
                groups[(key, tuple(sorted(subs)))].add(st)

    busy_slots = {st: set(by_slot) for st, by_slot in busy.items()}
    busy_slots = defaultdict(set, busy_slots)
    dates = _session_dates(session, rows)
    subjects = {s.id: s for s in Subject.objects.filter(id__in=set(takers) | set(slot))}
    sched_id = {r.subject_id: r.id for r in rows}

    def subj(sid):
        s = subjects[sid]
        return {**_subject_row(s), "students": len(takers.get(sid, ())), "arrear_students": arrear_count.get(sid, 0),
                "schedule_id": sched_id.get(sid)}

    clashes = []
    for (key, subs), studs in sorted(groups.items(), key=lambda g: (g[0][0][0], SESSION_ORDER[g[0][0][1]])):
        # suggest moving the paper with the fewest students
        move = min(subs, key=lambda s: (len(takers.get(s, ())), -arrear_count.get(s, 0)))
        # slots free for everyone who writes `move`, ignoring `move`'s own current slot
        own = {st: {k for k, v in busy[st].items() if v - {move}} for st in takers.get(move, ())}
        people = User.objects.filter(id__in=studs).order_by("roll_number")
        clashes.append({
            "exam_date": key[0].isoformat(), "session": key[1],
            "subjects": [subj(s) for s in subs],
            "count": len(studs),
            "students": [{"id": u.id, "name": u.username, "roll_number": u.roll_number} for u in people[:200]],
            "move_subject": move,
            "suggestions": free_slots(move, takers, defaultdict(set, own), dates, near=key, skip=key),
        })

    unscheduled = []
    for sid, studs in takers.items():
        if sid in slot or not studs or sid not in subjects:
            continue
        unscheduled.append({**subj(sid), "suggestions": free_slots(sid, takers, busy_slots, dates)})
    unscheduled.sort(key=lambda x: (x["semester"], x["code"], x["name"]))

    grid = defaultdict(list)
    for r in rows:
        grid[(r.exam_date, r.session)].append(r.subject_id)
    clash_ids = defaultdict(int)
    for c in clashes:
        for s in c["subjects"]:
            clash_ids[(c["exam_date"], c["session"], s["id"])] += c["count"]
    days = []
    for d in sorted({k[0] for k in grid}):
        day = {"date": d.isoformat(), "FN": [], "AN": []}
        for ss in ("FN", "AN"):
            for sid in sorted(grid.get((d, ss), []), key=lambda x: (subjects[x].semester, subjects[x].code or "")):
                row = subj(sid)
                row["clash_students"] = clash_ids.get((d.isoformat(), ss, sid), 0)
                day[ss].append(row)
        days.append(day)

    papers = [sid for sid, st in takers.items() if st]
    return {
        "session": session_payload(session),
        "days": days,
        "clashes": clashes,
        "unscheduled": unscheduled,
        "checks": {
            "papers": len(papers),
            "scheduled": sum(1 for s in papers if s in slot),
            "clashes": len(clashes),
            "clash_students": len({st for c in clashes for st in (x["id"] for x in c["students"])}),
            "max_students_in_a_session": max((sum(len(takers.get(s, ())) for s in v) for v in grid.values()), default=0),
        },
    }


def avoid_clashes(session, rows, pool):
    """Used by the exam-schedule draft: move a draft row off a slot where some of
    its students (arrear students, mostly) already have a paper from another
    class. Returns (rows, how many moved)."""
    if session is None or not rows:
        return rows, 0
    draft_ids = {r["subject"] for r in rows}
    takers = students_by_subject(session)
    busy = defaultdict(set)
    for e in schedule_rows(session):
        if e.subject_id in draft_ids:
            continue
        for st in takers.get(e.subject_id, ()):
            busy[st].add((e.exam_date.isoformat(), e.session))
    if not busy:
        return rows, 0
    used = {(r["exam_date"], r["session"]) for r in rows}
    used_days = {r["exam_date"] for r in rows}
    moved = 0
    for r in rows:
        studs = takers.get(r["subject"], set())
        cur = (r["exam_date"], r["session"])
        if not any(cur in busy[s] for s in studs):
            continue
        cur_day = datetime.date.fromisoformat(cur[0])
        cands = [(d.isoformat(), ss) for d in pool for ss in ("FN", "AN")]
        cands.sort(key=lambda c: (c[0] in used_days and c[0] != cur[0], abs((datetime.date.fromisoformat(c[0]) - cur_day).days), c[1] != cur[1]))
        for c in cands:
            if c in used or any(c in busy[s] for s in studs):
                continue
            used.discard(cur)
            used.add(c)
            used_days.add(c[0])
            r["exam_date"], r["session"] = c
            moved += 1
            break
    return rows, moved


# ---------------------------------------------------------------- admin views of a session
def session_payload(s):
    return {
        "id": s.id, "name": s.name, "kind": s.kind,
        "exam_start": s.exam_start.isoformat() if s.exam_start else None,
        "exam_end": s.exam_end.isoformat() if s.exam_end else None,
        "registration_required": s.registration_required,
        "reg_opens": s.reg_opens.isoformat() if s.reg_opens else None,
        "reg_closes": s.reg_closes.isoformat() if s.reg_closes else None,
        "late_until": s.late_until.isoformat() if s.late_until else None,
        "registration_closed": s.registration_closed,
        "window": window_state(s),
        "semesters": s.semesters or [],
        "students_pick_arrears": s.students_pick_arrears,
        "fee_required": s.fee_required,
        "regular_fee": float(s.regular_fee), "arrear_fee": float(s.arrear_fee), "late_fee": float(s.late_fee),
        "is_current": s.is_current,
        "timetable_published": s.timetable_published,
        "hall_tickets_released": s.hall_tickets_released,
    }


def _session_students(session):
    """Students who write in this session: the semesters it is for, plus anyone
    who registered (arrear students from other semesters)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    User = get_user_model()
    q = Q(exam_registrations__exam_session=session)
    if session.kind == "regular":
        q |= Q(semester__in=session.semesters) if session.semesters else Q(role="student")
    return User.objects.filter(role="student").filter(q).distinct()


def progress(session):
    """Registration progress, one row per class."""
    regs = {r.student_id: r for r in ExamRegistration.objects.filter(exam_session=session)
            .select_related("fee").prefetch_related("papers")}
    from .views import _can_sit_exam, _rules
    rules = _rules()
    by_class = {}
    totals = {"students": 0, "registered": 0, "not_yet": 0, "arrear_papers": 0, "fee_pending": 0, "not_eligible": 0}
    for st in _session_students(session).select_related("course").order_by("course__name", "year", "semester"):
        key = (st.course_id, st.year, st.semester)
        row = by_class.setdefault(key, {
            "course_id": st.course_id, "course": st.course.name if st.course_id else "",
            "year": st.year, "semester": st.semester,
            "students": 0, "registered": 0, "not_yet": 0, "arrear_papers": 0, "fee_pending": 0, "not_eligible": 0})
        reg = regs.get(st.id)
        row["students"] += 1
        if reg and reg.status == "submitted":
            row["registered"] += 1
            if reg.fee_id and reg.fee.status != "paid":
                row["fee_pending"] += 1
        else:
            row["not_yet"] += 1
        if reg:
            row["arrear_papers"] += sum(1 for p in reg.papers.all() if p.kind == "arrear")
        if writes_regular(session, st) and not _can_sit_exam(st, rules)[0]:
            row["not_eligible"] += 1
    for row in by_class.values():
        for k in totals:
            totals[k] += row[k]
    return {"session": session_payload(session), "totals": totals, "classes": list(by_class.values())}


def class_registrations(session, course, year, semester):
    from .views import _can_sit_exam, _rules
    rules = _rules()
    regs = {r.student_id: r for r in ExamRegistration.objects.filter(exam_session=session)
            .select_related("fee").prefetch_related("papers__subject")}
    out = []
    students = _session_students(session).filter(course_id=course, year=year, semester=semester).order_by("roll_number")
    for st in students:
        reg = regs.get(st.id)
        papers = list(reg.papers.all()) if reg else []
        eligible = _can_sit_exam(st, rules) if writes_regular(session, st) else (True, None, "attendance")
        out.append({
            "student": st.id, "name": st.username, "roll_number": st.roll_number,
            "status": reg.status if reg else "none", "is_late": bool(reg and reg.is_late),
            "regular_papers": sum(1 for p in papers if p.kind == "regular"),
            "arrears": [p.subject.code or p.subject.name for p in papers if p.kind == "arrear"],
            "fee": _fee_payload(reg.fee) if reg else None,
            "complete": is_complete(reg),
            "eligible": eligible[0], "attendance_percent": eligible[1], "reason": eligible[2],
        })
    return out


# ---------------------------------------------------------------- hall ticket papers
def hall_ticket_papers(session, student, regular_ok, regular_reason):
    """(registered, papers) for the session's hall ticket. Each paper says
    whether it is withheld and why."""
    slots = {r.subject_id: r for r in schedule_rows(session)}
    reg = (ExamRegistration.objects.filter(exam_session=session, student=student)
           .select_related("fee").prefetch_related("papers__subject").first())
    if reg is None or reg.status != "submitted":
        return False, False, []
    fee_ok = reg.fee_id is None or reg.fee.status == "paid"
    from .seating import seat_for          # WAVE 3 PART 2b: hall + seat once seats are given
    seats = seat_for(session, student)
    papers = []
    for p in reg.papers.all():
        s = p.subject
        withheld = None
        if not fee_ok:
            withheld = "registration_fee_unpaid"
        elif p.kind == "regular" and not regular_ok:
            withheld = regular_reason
        papers.append({"subject_id": s.id, "name": s.name, "code": s.code or "", "semester": s.semester,
                       "kind": p.kind, **_slot(slots.get(s.id)), "withheld": withheld})
        hs = seats.get((papers[-1]["exam_date"], papers[-1]["session"]))
        papers[-1]["hall"], papers[-1]["seat"] = (hs if hs and not withheld else (None, None))
    papers.sort(key=lambda x: (x["exam_date"] is None, x["exam_date"] or "", SESSION_ORDER.get(x["session"] or "FN", 0)))
    return True, fee_ok, papers
