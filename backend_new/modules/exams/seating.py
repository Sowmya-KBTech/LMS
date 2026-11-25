"""WAVE 3 PART 2b - exam halls, seating and invigilation, in one file
(the logic and its APIs together).

A SITTING is one date + FN/AN of an exam session. For each sitting:
  * seats are given hall by hall. "alternate" puts different papers side by
    side on a bench; "spaced" seats one student per bench.
  * invigilators are given to every hall in use (two above a set number of
    students), plus relief staff. Duties go to whoever has the fewest so far,
    skipping staff on approved leave, the Principal, HODs (unless included),
    staff who teach a paper of that sitting, and anyone already on duty that
    day.

Exam admin APIs:
  GET/POST            exam-halls/
  PATCH/DELETE        exam-halls/<id>/
  POST                exam-halls/from-rooms/            halls from the timetable's rooms
  GET/PATCH           exam-sessions/<id>/rules/         seating + invigilation rules
  GET                 exam-sessions/<id>/sittings/      every sitting with its counts
  GET                 exam-sessions/<id>/seating/?date=&sitting=
  POST                exam-sessions/<id>/seating/allot/      {date, sitting} or {all: true}
  GET                 exam-sessions/<id>/duties/?date=&sitting=
  POST                exam-sessions/<id>/duties/assign/      {date, sitting} or {all: true}
  PATCH               exam-duties/<id>/                 {staff}
Staff:
  GET                 exam-duties/me/
"""
import datetime
from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .exam_sessions import current_session, schedule_rows, students_by_subject
from .models import (ExamHall, ExamRegistrationPaper, ExamSession, InvigilationDuty,
                     SeatAllotment)

User = get_user_model()
ORDER = {"FN": 0, "AN": 1}


# ================================================================ helpers
def _admin(request):
    from .views import is_exam_admin
    return is_exam_admin(request.user)


def _no():
    return Response({"detail": "Only the exam admin can manage halls, seating and duties."}, status=403)


def _bool(v):
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def _date(v):
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _sitting_args(data):
    day, sit = _date(data.get("date")), data.get("sitting")
    if day is None or sit not in ("FN", "AN"):
        return None, None
    return day, sit


def _person(u):
    return {"id": u.id, "name": (getattr(u, "display_name", "") or u.username), "username": u.username,
            "roll_number": getattr(u, "roll_number", "") or ""}


def hall_payload(h):
    return {"id": h.id, "name": h.name, "seats": h.seats, "per_bench": h.per_bench,
            "is_active": h.is_active, "order": h.order}


def rules_payload(s):
    return {"seating_mode": s.seating_mode, "two_invigilators_above": s.two_invigilators_above,
            "relief_per_sitting": s.relief_per_sitting, "skip_own_subject": s.skip_own_subject,
            "one_duty_per_day": s.one_duty_per_day, "include_hods": s.include_hods}


def sittings(session):
    """[(date, 'FN'|'AN', [subject, ...])] in date order."""
    by = defaultdict(list)
    for r in schedule_rows(session):
        by[(r.exam_date, r.session)].append(r.subject)
    return [(d, s, by[(d, s)]) for d, s in sorted(by, key=lambda k: (k[0], ORDER[k[1]]))]


def sitting_students(session, day, sit):
    """[(student, subject)] writing in this sitting, by paper then roll number.
    With registration: submitted registrations. Without: each class's students."""
    subjects = {r.subject_id: r.subject for r in schedule_rows(session).filter(exam_date=day, session=sit)}
    if not subjects:
        return []
    pairs = {}
    if session.registration_required:
        for p in (ExamRegistrationPaper.objects
                  .filter(registration__exam_session=session, registration__status="submitted",
                          subject_id__in=subjects)
                  .values("registration__student_id", "subject_id")):
            pairs.setdefault(p["registration__student_id"], p["subject_id"])
    else:
        takers = students_by_subject(session)
        for sid in subjects:
            for st in takers.get(sid, ()):
                pairs.setdefault(st, sid)
    people = {u.id: u for u in User.objects.filter(id__in=pairs)}
    out = [(people[st], subjects[sid]) for st, sid in pairs.items() if st in people]
    out.sort(key=lambda x: (x[1].code or x[1].name, x[0].roll_number or "", x[0].username))
    return out


# ================================================================ seating
def _seats(halls, spaced):
    out = []
    for h in halls:
        per = max(1, h.per_bench)
        for n in range(1, h.seats + 1):
            pos = (n - 1) % per
            if spaced and pos:
                continue
            out.append((h, n, pos))
    return out


@transaction.atomic
def allot(session, day, sit):
    """Give seats for one sitting. Returns a summary."""
    people = sitting_students(session, day, sit)
    halls = list(ExamHall.objects.filter(is_active=True))
    spaced = session.seating_mode == "spaced"
    seats = _seats(halls, spaced)
    SeatAllotment.objects.filter(exam_session=session, exam_date=day, sitting=sit).delete()

    subject_of = {}
    if spaced:
        seq = [(st, sub.id) for st, sub in people]
    else:
        groups = defaultdict(list)
        for st, sub in people:
            groups[sub.id].append(st)
        seq = []
        # restart the alternation at each bench, so the choice only looks at the bench-mate
        left = {k: list(v) for k, v in groups.items()}
        prev = None
        for _h, _n, pos in seats:
            if not any(left.values()):
                break
            if pos == 0:
                prev = None
            options = sorted((k for k in left if left[k]), key=lambda k: -len(left[k]))
            pick = next((k for k in options if k != prev), options[0])
            seq.append((left[pick].pop(0), pick))
            prev = pick
        for k in left:                      # more students than seats
            seq.extend((st, k) for st in left[k])
    for st, sub in people:
        subject_of[sub.id] = sub

    rows, unseated = [], []
    for i, (st, sid) in enumerate(seq):
        if i < len(seats):
            h, n, _pos = seats[i]
            rows.append(SeatAllotment(exam_session=session, exam_date=day, sitting=sit, hall=h, seat_no=n,
                                      student=st, subject_id=sid))
        else:
            unseated.append(st)
    SeatAllotment.objects.bulk_create(rows)
    return {"date": day.isoformat(), "sitting": sit, "students": len(people), "seated": len(rows),
            "unseated": len(unseated)}


def _same_neighbours(allots):
    """Bench-mates writing the same paper (alternate mode can't always avoid it)."""
    by_bench = defaultdict(list)
    for a in allots:
        by_bench[(a.hall_id, (a.seat_no - 1) // max(1, a.hall.per_bench))].append(a.subject_id)
    return sum(len(v) - len(set(v)) for v in by_bench.values())


def seating_plan(session, day, sit):
    allots = list(SeatAllotment.objects.filter(exam_session=session, exam_date=day, sitting=sit)
                  .select_related("hall", "student", "subject"))
    writing = sitting_students(session, day, sit)
    seated = {a.student_id for a in allots}
    halls = []
    by_hall = defaultdict(list)
    for a in allots:
        by_hall[a.hall_id].append(a)
    for h in ExamHall.objects.all():
        rows = by_hall.get(h.id, [])
        if not rows and not h.is_active:
            continue
        halls.append({**hall_payload(h), "used": len(rows), "seat_map": [
            {"seat": a.seat_no, "student_id": a.student_id, "roll_number": a.student.roll_number or "",
             "name": a.student.username, "subject_id": a.subject_id, "code": a.subject.code or a.subject.name}
            for a in rows]})
    papers = Counter((sub.id, sub.code or sub.name) for _st, sub in writing)
    return {
        "date": day.isoformat(), "sitting": sit, "rules": rules_payload(session),
        "papers": [{"id": k[0], "code": k[1], "students": n} for k, n in sorted(papers.items(), key=lambda x: x[0][1])],
        "students": len(writing), "seated": len(allots),
        "not_seated": [_person(st) for st, _sub in writing if st.id not in seated][:200],
        "seats_available": sum(len(_seats([h], session.seating_mode == "spaced")) for h in ExamHall.objects.filter(is_active=True)),
        "same_neighbours": _same_neighbours(allots),
        "halls": halls,
    }


# ================================================================ invigilation
def _on_leave(day, sit):
    """Staff ids on approved (or recorded) leave for this date + sitting."""
    from config.module_registry import optional_model
    Leave = optional_model("attendance", "attendance", "StaffLeaveRequest")
    half = "forenoon" if sit == "FN" else "afternoon"
    return set(Leave.objects.filter(status__in=["approved", "recorded"], from_date__lte=day, to_date__gte=day,
                                    session__in=["full", half]).values_list("teacher_id", flat=True))


def _excluded(session):
    """{staff_id: reason} for people never put on the duty list."""
    out = {}
    from core.users.principal import current_principal
    p = current_principal()
    if p:
        out[p.id] = "Principal"
    if not session.include_hods:
        from core.users.models import Department
        for hid in Department.objects.exclude(hod__isnull=True).values_list("hod_id", flat=True):
            out.setdefault(hid, "HOD")
    return out


def staff_pool():
    return list(User.objects.filter(role="teacher", is_active=True).order_by("username"))


def _teachers_of(subject_ids):
    from core.academics.models import TeachingAssignment
    return set(TeachingAssignment.objects.filter(subject_id__in=subject_ids).values_list("teacher_id", flat=True))


def _sitting_need(session, day, sit):
    """[(hall, students, invigilators needed)] for halls in use."""
    counts = Counter(SeatAllotment.objects.filter(exam_session=session, exam_date=day, sitting=sit)
                     .values_list("hall_id", flat=True))
    thr = session.two_invigilators_above
    halls = {h.id: h for h in ExamHall.objects.filter(id__in=counts)}
    out = []
    for hid in sorted(counts, key=lambda x: (halls[x].order, halls[x].name)):
        n = counts[hid]
        out.append((halls[hid], n, 2 if (thr == 0 or n > thr) else 1))
    return out


def _blocked(session, day, sit, subject_ids):
    """{staff_id: reason} who can't take a duty in this sitting."""
    out = dict(_excluded(session))
    for sid in _on_leave(day, sit):
        out.setdefault(sid, "on leave")
    if session.skip_own_subject:
        for sid in _teachers_of(subject_ids):
            out.setdefault(sid, "teaches a paper of this sitting")
    return out


@transaction.atomic
def assign_sitting(session, day, sit, load=None):
    """Give duties for one sitting, fairly. Returns (filled, unfilled)."""
    InvigilationDuty.objects.filter(exam_session=session, exam_date=day, sitting=sit).delete()
    need = _sitting_need(session, day, sit)
    if not need:
        return 0, 0
    subject_ids = list(schedule_rows(session).filter(exam_date=day, session=sit).values_list("subject_id", flat=True))
    blocked = _blocked(session, day, sit, subject_ids)
    if load is None:
        load = Counter(InvigilationDuty.objects.filter(exam_session=session).values_list("staff_id", flat=True))
    busy_today = set()
    if session.one_duty_per_day:
        busy_today = set(InvigilationDuty.objects.filter(exam_session=session, exam_date=day)
                         .values_list("staff_id", flat=True))
    pool = [u for u in staff_pool() if u.id not in blocked and u.id not in busy_today]
    used = set()

    def take():
        cands = [u for u in pool if u.id not in used]
        if not cands:
            return None
        u = min(cands, key=lambda x: (load[x.id], x.username))
        used.add(u.id)
        load[u.id] += 1
        return u

    rows, unfilled = [], 0
    slots = [h for h, _n, k in need for _ in range(k)] + [None] * session.relief_per_sitting
    for h in slots:
        u = take()
        if u is None:
            unfilled += 1
            continue
        rows.append(InvigilationDuty(exam_session=session, exam_date=day, sitting=sit, hall=h, staff=u))
    InvigilationDuty.objects.bulk_create(rows)
    return len(rows), unfilled


def best_replacement(duty):
    s = duty.exam_session
    subject_ids = list(schedule_rows(s).filter(exam_date=duty.exam_date, session=duty.sitting)
                       .values_list("subject_id", flat=True))
    blocked = _blocked(s, duty.exam_date, duty.sitting, subject_ids)
    busy = InvigilationDuty.objects.filter(exam_session=s, exam_date=duty.exam_date)
    if not s.one_duty_per_day:
        busy = busy.filter(sitting=duty.sitting)
    busy = set(busy.values_list("staff_id", flat=True))
    load = Counter(InvigilationDuty.objects.filter(exam_session=s).values_list("staff_id", flat=True))
    cands = [u for u in staff_pool() if u.id not in blocked and u.id not in busy]
    if not cands:
        return None, load
    u = min(cands, key=lambda x: (load[x.id], x.username))
    return u, load


def duties_view(session, day, sit):
    duties = list(InvigilationDuty.objects.filter(exam_session=session, exam_date=day, sitting=sit)
                  .select_related("hall", "staff"))
    need = _sitting_need(session, day, sit)
    leave = _on_leave(day, sit)
    load = Counter(InvigilationDuty.objects.filter(exam_session=session).values_list("staff_id", flat=True))
    by_hall = defaultdict(list)
    for d in duties:
        by_hall[d.hall_id].append({"duty_id": d.id, **_person(d.staff), "on_leave": d.staff_id in leave})
    rows = [{"hall": hall_payload(h), "students": n, "needed": k, "staff": by_hall.get(h.id, [])} for h, n, k in need]
    relief = by_hall.get(None, [])
    subject_ids = list(schedule_rows(session).filter(exam_date=day, session=sit).values_list("subject_id", flat=True))
    blocked = _blocked(session, day, sit, subject_ids)
    names = {u.id: u for u in User.objects.filter(id__in=blocked)}
    skipped = [{**_person(names[i]), "reason": r} for i, r in blocked.items() if i in names and names[i].role == "teacher"]
    skipped.sort(key=lambda x: (x["reason"], x["name"]))
    return {
        "date": day.isoformat(), "sitting": sit, "rules": rules_payload(session),
        "halls": rows, "relief": relief,
        "unfilled": sum(max(0, r["needed"] - len(r["staff"])) for r in rows) + max(0, session.relief_per_sitting - len(relief)),
        "seated": bool(need),
        "skipped": skipped,
        "load": [{**_person(u), "duties": load[u.id]} for u in sorted(staff_pool(), key=lambda x: (-load[x.id], x.username))],
        "conflicts": conflicts(session),
    }


def conflicts(session):
    """Duties whose staff member is now on approved leave, with a suggested replacement."""
    out = []
    for d in (InvigilationDuty.objects.filter(exam_session=session).select_related("staff", "hall")
              .order_by("exam_date", "sitting")):
        if d.staff_id not in _on_leave(d.exam_date, d.sitting):
            continue
        rep, load = best_replacement(d)
        out.append({"duty_id": d.id, "date": d.exam_date.isoformat(), "sitting": d.sitting,
                    "hall": d.hall.name if d.hall else "Relief", "staff": _person(d.staff),
                    "suggest": ({**_person(rep), "duties": load[rep.id]} if rep else None)})
    return out


def sitting_summary(session):
    seats = Counter(SeatAllotment.objects.filter(exam_session=session).values_list("exam_date", "sitting"))
    duties = Counter(InvigilationDuty.objects.filter(exam_session=session).values_list("exam_date", "sitting"))
    out = []
    for d, s, subs in sittings(session):
        out.append({"date": d.isoformat(), "sitting": s, "papers": [x.code or x.name for x in subs],
                    "seated": seats.get((d, s), 0), "duties": duties.get((d, s), 0)})
    return out


# ================================================================ APIs
def _session(pk):
    return ExamSession.objects.filter(pk=pk).first()


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def halls(request):
    if not _admin(request):
        return _no()
    if request.method == "GET":
        return Response([hall_payload(h) for h in ExamHall.objects.all()])
    h = ExamHall()
    err = _apply_hall(h, request.data)
    if err:
        return Response({"detail": err}, status=400)
    h.save()
    return Response(hall_payload(h), status=201)


def _apply_hall(h, data):
    if "name" in data or h.pk is None:
        name = (data.get("name") or "").strip()
        if not name:
            return "Give the hall a name."
        if ExamHall.objects.filter(name__iexact=name).exclude(pk=h.pk).exists():
            return f"There is already a hall called {name}."
        h.name = name[:40]
    for f, lo, hi, label in (("seats", 1, 500, "Exam seats"), ("per_bench", 1, 4, "Students per bench"),
                             ("order", 0, 999, "Order")):
        if f in data:
            try:
                v = int(data[f])
            except (TypeError, ValueError):
                return f"{label} must be a number."
            if not lo <= v <= hi:
                return f"{label} must be between {lo} and {hi}."
            setattr(h, f, v)
    if "is_active" in data:
        h.is_active = _bool(data["is_active"])
    return None


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def hall_detail(request, pk):
    if not _admin(request):
        return _no()
    h = ExamHall.objects.filter(pk=pk).first()
    if h is None:
        return Response({"detail": "Hall not found."}, status=404)
    if request.method == "DELETE":
        if h.allotments.exists() or h.duties.exists():
            return Response({"detail": "This hall already has seats or duties. Switch it off instead."}, status=400)
        h.delete()
        return Response(status=204)
    err = _apply_hall(h, request.data)
    if err:
        return Response({"detail": err}, status=400)
    h.save()
    return Response(hall_payload(h))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def halls_from_rooms(request):
    """Add a hall for every timetable room that isn't one yet: exam seats = half
    the class seats; labs start switched off."""
    if not _admin(request):
        return _no()
    from config.module_registry import module_enabled
    if not module_enabled("timetable"):
        return Response({"detail": "The timetable module is off, so there are no rooms to copy."}, status=400)
    from modules.timetable.models import Room
    have = {n.lower() for n in ExamHall.objects.values_list("name", flat=True)}
    added = 0
    for r in Room.objects.filter(is_active=True):
        if r.name.lower() in have:
            continue
        ExamHall.objects.create(name=r.name, seats=max(1, r.capacity // 2), per_bench=2, is_active=r.kind != "lab")
        added += 1
    return Response({"added": added, "halls": [hall_payload(h) for h in ExamHall.objects.all()]})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def rules(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    if request.method == "PATCH":
        d = request.data
        if "seating_mode" in d:
            if d["seating_mode"] not in ("alternate", "spaced"):
                return Response({"detail": "Choose alternate or spaced seating."}, status=400)
            s.seating_mode = d["seating_mode"]
        for f, hi in (("two_invigilators_above", 500), ("relief_per_sitting", 10)):
            if f in d:
                try:
                    v = int(d[f])
                except (TypeError, ValueError):
                    return Response({"detail": "Use whole numbers."}, status=400)
                if not 0 <= v <= hi:
                    return Response({"detail": f"Keep it between 0 and {hi}."}, status=400)
                setattr(s, f, v)
        for f in ("skip_own_subject", "one_duty_per_day", "include_hods"):
            if f in d:
                setattr(s, f, _bool(d[f]))
        s.save()
    return Response(rules_payload(s))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_sittings(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    return Response({"rules": rules_payload(s), "timetable_published": s.timetable_published,
                     "halls": [hall_payload(h) for h in ExamHall.objects.all()], "sittings": sitting_summary(s)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def seating(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    day, sit = _sitting_args(request.query_params)
    if s is None or day is None:
        return Response({"detail": "Pick an exam session, a date and FN or AN."}, status=400)
    return Response(seating_plan(s, day, sit))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def seating_allot(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    if not s.timetable_published:
        return Response({"detail": "Publish the timetable first, so the seats match the final dates."}, status=400)
    if not ExamHall.objects.filter(is_active=True).exists():
        return Response({"detail": "Add at least one exam hall first."}, status=400)
    if _bool(request.data.get("all")):
        done = [allot(s, d, sit) for d, sit, _subs in sittings(s)]
        short = sum(x["unseated"] for x in done)
        return Response({"sittings": done, "unseated": short,
                         "detail": (f"Seats given for {len(done)} sittings."
                                    + (f" {short} students had no seat - add halls or seats." if short else ""))})
    day, sit = _sitting_args(request.data)
    if day is None:
        return Response({"detail": "Pick a date and FN or AN."}, status=400)
    res = allot(s, day, sit)
    res["detail"] = (f"{res['seated']} students seated." if not res["unseated"]
                     else f"{res['seated']} seated, {res['unseated']} without a seat - add halls or seats.")
    return Response(res)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def duties(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    day, sit = _sitting_args(request.query_params)
    if s is None or day is None:
        return Response({"detail": "Pick an exam session, a date and FN or AN."}, status=400)
    return Response(duties_view(s, day, sit))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def duties_assign(request, pk):
    if not _admin(request):
        return _no()
    s = _session(pk)
    if s is None:
        return Response({"detail": "Exam session not found."}, status=404)
    if _bool(request.data.get("all")):
        InvigilationDuty.objects.filter(exam_session=s).delete()
        load = Counter()
        filled = unfilled = 0
        for d, sit, _subs in sittings(s):
            f, u = assign_sitting(s, d, sit, load)
            filled, unfilled = filled + f, unfilled + u
        if not filled and not unfilled:
            return Response({"detail": "Give seats first - duties follow the halls in use."}, status=400)
        return Response({"filled": filled, "unfilled": unfilled,
                         "detail": f"{filled} duties given." + (f" {unfilled} could not be filled - not enough free staff." if unfilled else "")})
    day, sit = _sitting_args(request.data)
    if day is None:
        return Response({"detail": "Pick a date and FN or AN."}, status=400)
    f, u = assign_sitting(s, day, sit)
    if not f and not u:
        return Response({"detail": "Give seats for this sitting first - duties follow the halls in use."}, status=400)
    return Response({"filled": f, "unfilled": u,
                     "detail": f"{f} duties given." + (f" {u} could not be filled - not enough free staff." if u else "")})


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def duty_detail(request, pk):
    """Put someone else on a duty. The same rules as the automatic list apply."""
    if not _admin(request):
        return _no()
    d = InvigilationDuty.objects.filter(pk=pk).select_related("exam_session").first()
    if d is None:
        return Response({"detail": "Duty not found."}, status=404)
    staff = User.objects.filter(pk=request.data.get("staff"), role="teacher", is_active=True).first()
    if staff is None:
        return Response({"detail": "Pick a staff member."}, status=400)
    s = d.exam_session
    subject_ids = list(schedule_rows(s).filter(exam_date=d.exam_date, session=d.sitting).values_list("subject_id", flat=True))
    why = _blocked(s, d.exam_date, d.sitting, subject_ids).get(staff.id)
    if why:
        return Response({"detail": f"{staff.username} can't take this duty ({why})."}, status=400)
    clash = InvigilationDuty.objects.filter(exam_session=s, exam_date=d.exam_date, staff=staff).exclude(pk=d.pk)
    if not s.one_duty_per_day:
        clash = clash.filter(sitting=d.sitting)
    if clash.exists():
        return Response({"detail": f"{staff.username} already has a duty {'that day' if s.one_duty_per_day else 'in this sitting'}."},
                        status=400)
    d.staff = staff
    d.save(update_fields=["staff"])
    return Response({"duty_id": d.id, **_person(staff)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_duties(request):
    """A staff member's exam duties in the current session, from today on."""
    s = current_session()
    if s is None:
        return Response({"session": None, "duties": []})
    rows = (InvigilationDuty.objects.filter(exam_session=s, staff=request.user,
                                            exam_date__gte=timezone.localdate())
            .select_related("hall").order_by("exam_date", "sitting"))
    return Response({"session": s.name, "duties": [
        {"date": d.exam_date.isoformat(), "sitting": d.sitting, "hall": d.hall.name if d.hall else "Relief / flying squad"}
        for d in rows]})


def seat_for(session, student):
    """{(date, sitting): (hall name, seat)} for a hall ticket."""
    return {(a.exam_date.isoformat(), a.sitting): (a.hall.name, a.seat_no)
            for a in SeatAllotment.objects.filter(exam_session=session, student=student).select_related("hall")}
