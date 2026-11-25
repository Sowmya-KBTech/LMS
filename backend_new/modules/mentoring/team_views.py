from django.db import transaction
from django.db.models import Count,Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    MentorAllocation,
    MentoringSetting,
    MentorTeam,
    MentorTeamMember,
    UnplacedStudent,
)
from .team_serializers import (
    JoinTeamSerializer,
    MentorRuleSerializer,
    PlaceStudentSerializer,
    SetTeamMentorSerializer,
)
from .utils import (
    band_for_cgpa,
    cgpa_map,
    class_students,
    department_mentors,
    department_students,
    mentor_rule_for,
    resolve_advisor_class,
    student_cgpa,
    student_in_team,
    teams_needed,
)

# helpers that already exist in views.py — no need to write them twice
from .views import _dept_for, _mentor_rows, _year, notify


# ===================== WHO IS HOD NOW (#50 ACTING HOD) =====================
def _current_hod(dept):
    """
    The person holding the HOD powers of this department today. With the
    Acting HOD feature installed (core/users/acting_hod.py, by the teammate)
    that is the Acting HOD while one is active; until it is installed, the
    regular HOD - so submitting teams never crashes for want of that file.
    """
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is not None:
        from core.users.acting_hod import current_hod
        return current_hod(dept)
    return dept.hod if dept.hod_id else None


YEAR_LABEL = {1: "I", 2: "II", 3: "III", 4: "IV"}


# ==================================================================
# ================= HOD: RULES =====================================
# ==================================================================

def _class_preview(dept, setting, rule):
    """
    What each class in the department produces under the current rules.

    Everything here is derived. The number of teams comes from the class
    size and the rule, never from a fixed figure, so a class of 74 and a
    class of 61 both read correctly on the same screen.
    """
    students = list(department_students(dept, setting=setting))
    cgpas = cgpa_map(students)

    classes = {}
    for s in students:
        if not s.course_id or not s.year:
            continue
        key = (s.course_id, s.year)
        row = classes.setdefault(key, {
            "course_id": s.course_id,
            "course_name": s.course.name,
            "year": s.year,
            "year_label": YEAR_LABEL.get(s.year, s.year),
            "students": 0,
            "band_a": 0, "band_b": 0, "band_c": 0, "band_none": 0,
        })
        row["students"] += 1

        band = band_for_cgpa(cgpas.get(s.id), setting)
        if band is None and setting.first_year_rule == "band_b":
            band = "B"
        if band in ("A", "B", "C"):
            row["band_" + band.lower()] += 1
        else:
            row["band_none"] += 1

    out = []
    for row in classes.values():
        n_teams = teams_needed(row["students"], rule)
        row["teams"] = n_teams
        row["mentors_needed"] = n_teams

        # which band runs out first, and by how many
        shortfalls = {}
        if rule.grade_mix == "abc" and n_teams:
            for b in ("a", "b", "c"):
                have = row["band_" + b]
                if have < n_teams:
                    shortfalls[b.upper()] = n_teams - have
        row["short_of"] = shortfalls
        row["fully_balanced"] = not shortfalls
        out.append(row)

    out.sort(key=lambda r: (r["course_name"], r["year"]))
    return out


def _mentor_pool(dept, rule, ay):
    """
    How many teachers are eligible under the rules, and why the rest are not.
    Rotation uses last year's allocation records — nothing else is needed.
    """
    from core.academics.models import YearTutor

    teachers = list(department_mentors(dept))
    total = len(teachers)

    # academic_year is "2026-2027"; the year before is "2025-2026"
    excluded_last_year = set()
    if rule.skip_last_year_mentors:
        try:
            start = int(ay.split("-")[0])
            prev = f"{start - 1}-{start}"
        except (ValueError, IndexError):
            prev = None
        if prev:
            excluded_last_year = set(
                MentorAllocation.objects
                .filter(department=dept, academic_year=prev)
                .values_list("mentor_id", flat=True)
            )

    excluded_advisors = set()
    if rule.skip_class_advisors:
        excluded_advisors = set(
            YearTutor.objects
            .filter(teacher__department=dept)
            .values_list("teacher_id", flat=True)
        )

    eligible = [
        t for t in teachers
        if t.id not in excluded_last_year and t.id not in excluded_advisors
    ]

    return {
        "total_teachers": total,
        "eligible": len(eligible),
        "excluded_mentored_last_year": len(excluded_last_year & {t.id for t in teachers}),
        "excluded_class_advisors": len(excluded_advisors & {t.id for t in teachers}),
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def hod_mentor_rules(request):
    """
    GET  — the department's rules for an academic year, with a live preview
           of what they produce for every class.
    POST — save them. Only the rule fields are writable; department and
           academic year come from the request context, not the body.
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err

    ay = _year(request)
    rule = mentor_rule_for(dept, ay)

    if request.method == "POST":
        ser = MentorRuleSerializer(rule, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        rule = ser.save()

    return Response({
        "academic_year": ay,
        "department": {"id": dept.id, "name": dept.name},
        "rule": MentorRuleSerializer(rule).data,
        "choices": {
            "grade_mix": [
                {"value": v, "label": label}
                for v, label in rule.GRADE_MIX
            ],
            "fallback": [
                {"value": v, "label": label}
                for v, label in rule.FALLBACK
            ],
        },
        "mentor_pool": _mentor_pool(dept, rule, ay),
        "preview": _class_preview(dept, setting, rule),
    })


# ==================================================================
# ================= STUDENT ========================================
# ==================================================================

def _student_context(user, ay):
    """
    Everything both student views need: the class, the rules, this student's
    band, the teams that exist and how many the class should produce.

    Returns (context_dict, error_response). Exactly one is None.
    """
    if user.role != "student":
        return None, Response(
            {"detail": "Only a student has a team."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not user.course_id or not user.year:
        return None, Response(
            {"detail": "Your course and year are not set. Contact the office."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user.department_id:
        return None, Response(
            {"detail": "Your department is not set. Contact the office."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    setting = MentoringSetting.for_department(user.department)

    # Mentoring does not run in every year. Blocked here rather than in the
    # three views, because a student who cannot have a mentor must not be
    # able to form a team either - the advisor would have to unpick it.
    if (user.year or 0) < setting.allocate_from_year:
        return None, Response({
            "detail": (
                f"Mentoring starts in "
                f"{YEAR_LABEL.get(setting.allocate_from_year, setting.allocate_from_year)} Year. "
                "You can be assigned a mentor once you reach that year."
            ),
            "reason": "not_yet_eligible",
        }, status=status.HTTP_403_FORBIDDEN)

    rule = mentor_rule_for(user.department, ay)

    cgpa = student_cgpa(user)
    band = band_for_cgpa(cgpa, setting)
    if band is None and setting.first_year_rule == "band_b":
        band = "B"

    classmates = class_students(user.course, user.year)
    teams = list(
        MentorTeam.objects
        .filter(course=user.course, year=user.year, academic_year=ay)
        .prefetch_related("members__student")
        .order_by("number")
    )

    return {
        "setting": setting,
        "rule": rule,
        "cgpa": cgpa,
        "band": band,
        "class_size": classmates.count(),
        "teams": teams,
        "needed": teams_needed(classmates.count(), rule),
    }, None


def _slot_state(team, rule):
    """Which bands a team already holds, and how many members it has."""
    members = list(team.members.all())
    return {
        "size": len(members),
        "bands": {m.band for m in members if m.band},
        "members": members,
    }


def _fallback_open(teams, rule, band, can_create_more):
    """
    Whether a student of this band may join as an EXTRA member.

    Only once there is genuinely nowhere left to go: no existing team has a
    normal slot for them, and the class cannot form another team either.
    Without the second condition the very first team would accept extras
    while empty teams were still waiting to be created.
    """
    if rule.fallback != "extra_member":
        return False
    if can_create_more:
        return False

    for t in teams:
        if t.is_closed:
            continue
        st = _slot_state(t, rule)
        if st["size"] >= rule.team_size:
            continue
        if rule.grade_mix == "abc" and band:
            if band not in st["bands"]:
                return False          # a proper slot still exists
        else:
            return False
    return True


def _can_join(team, rule, band, fallback_open):
    """
    May this student join this team, and if not, why not.

    A normal join needs the band slot free and the team under its size.
    Anything beyond that is an extra member, allowed only when
    _fallback_open said there is nowhere else to go.
    """
    if team.is_closed:
        return False, False, "Team formation has closed."

    st = _slot_state(team, rule)
    room_for_extra = st["size"] < rule.team_size + 1

    if rule.grade_mix == "abc" and band:
        if band not in st["bands"] and st["size"] < rule.team_size:
            return True, False, ""
        if fallback_open and room_for_extra:
            return True, True, ""
        if band in st["bands"]:
            return False, False, f"This team already has a {band}-band student."
        return False, False, "This team is full."

    # no grade rule, or the student has no band yet
    if st["size"] < rule.team_size:
        return True, False, ""
    if fallback_open and room_for_extra:
        return True, True, ""
    return False, False, "This team is full."


def _team_payload(team, rule, band, fallback_open, me_id):
    st = _slot_state(team, rule)
    ok, as_extra, why = _can_join(team, rule, band, fallback_open)
    return {
        "id": team.id,
        "number": team.number,
        "size": st["size"],
        "team_size": rule.team_size,
        "is_closed": team.is_closed,
        "is_mine": any(m.student_id == me_id for m in st["members"]),
        "open_bands": (
            sorted({"A", "B", "C"} - st["bands"])
            if rule.grade_mix == "abc" and st["size"] < rule.team_size
            else []
        ),
        "can_join": ok,
        "would_be_extra": as_extra,
        "why_not": why,
        "members": [
            {
                "student_id": m.student_id,
                "name": (f"{m.student.first_name} {m.student.last_name}".strip()
                         or m.student.username),
                "roll_number": m.student.roll_number,
                "band": m.band,
                "is_extra": m.is_extra,
                "is_me": m.student_id == me_id,
            }
            for m in st["members"]
        ],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_teams(request):
    """Teams this student may join, their band, and the fallback message."""
    ay = _year(request)
    ctx, err = _student_context(request.user, ay)
    if err:
        return err

    rule, band, teams = ctx["rule"], ctx["band"], ctx["teams"]
    mine = student_in_team(request.user, ay)

    closed = any(t.is_closed for t in teams)
    can_create_more = not closed and len(teams) < ctx["needed"]

    # A student may only take a proper band slot. The extra-member fallback is
    # the tutor's tool for the last one or two students nobody can
    # seat - it is never offered here, or students would fill teams to four
    # while empty slots sat open elsewhere.
    fallback_open = False

    rows = [
        _team_payload(t, rule, band, fallback_open, request.user.id)
        for t in teams
    ]

    can_create = mine is None and can_create_more
    stuck = (
        mine is None and not closed and not can_create_more
        and not any(r["can_join"] for r in rows)
    )

    if mine:
        message = "You are in a team. You can leave until formation closes."
    elif closed:
        message = "Team formation has closed. Your class in-charge will place you."
    elif stuck:
        message = (
            f"Every team already has a {band}-band student, and your class has "
            "all the teams it needs. Your class in-charge will place you when "
            "team formation closes - you do not need to do anything."
        ) if band else (
            "No team has room for you at the moment. Your class in-charge will "
            "place you when team formation closes."
        )
    else:
        message = ""

    return Response({
        "academic_year": ay,
        "class": {
            "course_id": request.user.course_id,
            "course_name": request.user.course.name,
            "year": request.user.year,
            "students": ctx["class_size"],
        },
        "me": {
            "band": band or "",
            "cgpa": ctx["cgpa"],
            "in_team": mine.team_id if mine else None,
        },
        "rule": {
            "team_size": rule.team_size,
            "grade_mix": rule.grade_mix,
            "fallback": rule.fallback,
        },
        "teams_expected": ctx["needed"],
        "teams_formed": len(teams),
        "can_create_team": can_create,
        "waiting_for_advisor": stuck,
        "formation_closed": closed,
        "message": message,
        "results": rows,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_join_team(request):
    """
    Join a team, or start one when team_id is omitted.

    The whole transaction is serialised per class by locking the Course row
    first. Locking MentorTeam rows is not enough: when the class has no team
    yet there is nothing to lock, so two students starting a team at the same
    moment both compute number=1 and the second hits the unique constraint.
    """
    from core.academics.models import Course

    ay = _year(request)
    ctx, err = _student_context(request.user, ay)
    if err:
        return err

    ser = JoinTeamSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    team_id = ser.validated_data.get("team_id")

    rule, band = ctx["rule"], ctx["band"]

    with transaction.atomic():
        # one writer per class at a time — every branch below depends on a
        # consistent view of how many teams exist
        Course.objects.select_for_update().filter(id=request.user.course_id).first()

        if student_in_team(request.user, ay):
            return Response(
                {"detail": "You are already in a team. Leave it first."},
                status=status.HTTP_409_CONFLICT,
            )

        # ---------- start a new team ----------
        if not team_id:
            existing = list(
                MentorTeam.objects
                .filter(course=request.user.course, year=request.user.year,
                        academic_year=ay)
                .order_by("number")
            )
            if any(t.is_closed for t in existing):
                return Response({"detail": "Team formation has closed."},
                                status=status.HTTP_400_BAD_REQUEST)
            if len(existing) >= ctx["needed"]:
                return Response(
                    {"detail": "Your class already has all the teams it needs. "
                               "Join one of them instead."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            team = MentorTeam.objects.create(
                course=request.user.course, year=request.user.year,
                academic_year=ay,
                number=(existing[-1].number + 1 if existing else 1),
            )
            MentorTeamMember.objects.create(
                team=team, student=request.user, band=band or "", is_extra=False
            )
            return Response(
                {"team_id": team.id, "number": team.number, "is_extra": False,
                 "detail": f"You started Team {team.number}."},
                status=status.HTTP_201_CREATED,
            )

        # ---------- join an existing team ----------
        team = (
            MentorTeam.objects
            .filter(id=team_id, course=request.user.course,
                    year=request.user.year, academic_year=ay)
            .prefetch_related("members")
            .first()
        )
        if not team:
            return Response({"detail": "That team is not in your class."},
                            status=status.HTTP_404_NOT_FOUND)

        siblings = list(
            MentorTeam.objects
            .filter(course=request.user.course, year=request.user.year,
                    academic_year=ay)
            .prefetch_related("members")
        )
        can_create_more = (
            not any(t.is_closed for t in siblings)
            and len(siblings) < ctx["needed"]
        )

        # students take proper slots only - see student_teams
        ok, as_extra, why = _can_join(team, rule, band, False)
        if not ok:
            if can_create_more:
                why = why.rstrip(".") + ". Start a new team instead."
            else:
                why = (
                    why.rstrip(".")
                    + ". Your class in-charge will place you when formation closes."
                )
            return Response({"detail": why},
                            status=status.HTTP_400_BAD_REQUEST)

        MentorTeamMember.objects.create(
            team=team, student=request.user, band=band or "", is_extra=as_extra
        )

    return Response({
        "team_id": team.id,
        "number": team.number,
        "is_extra": as_extra,
        "detail": (
            f"You joined Team {team.number}"
            + (" as an extra member." if as_extra else ".")
        ),
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_leave_team(request):
    """
    Leave a team, only while formation is open.

    An empty team is deleted rather than left behind, so the team count
    stays honest and the number can be reused.
    """
    ay = _year(request)
    ctx, err = _student_context(request.user, ay)
    if err:
        return err

    with transaction.atomic():
        member = student_in_team(request.user, ay)
        if not member:
            return Response({"detail": "You are not in a team."},
                            status=status.HTTP_400_BAD_REQUEST)

        team = MentorTeam.objects.select_for_update().get(id=member.team_id)
        if team.is_closed:
            return Response(
                {"detail": "Team formation has closed, so you cannot leave. "
                           "Ask your class in-charge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        number = team.number
        member.delete()
        emptied = not team.members.exists()
        if emptied:
            team.delete()

    return Response({
        "detail": (
            f"You left Team {number}."
            + (" The team was empty, so it was removed." if emptied else "")
        ),
        "team_removed": emptied,
    })


# ==================================================================
# ================= TUTOR ==================================
# ==================================================================

def _advisor_context(request, ay):
    """
    The class this teacher advises, plus everything the Teams tab needs.

    Refuses outright when the teacher is not a YearTutor, so the page is
    class-specific by construction and not by hiding a menu item.
    Returns (context, error_response) — exactly one is None.
    """
    found = resolve_advisor_class(request.user)
    if not found:
        return None, Response(
            {"detail": "You are not the class in-charge of any class."},
            status=status.HTTP_403_FORBIDDEN,
        )
    course, year = found

    if not request.user.department_id:
        return None, Response(
            {"detail": "Your department is not set."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    dept = request.user.department
    setting = MentoringSetting.for_department(dept)
    rule = mentor_rule_for(dept, ay)

    students = list(class_students(course, year))
    cgpas = cgpa_map(students)

    bands = {}
    for st in students:
        b = band_for_cgpa(cgpas.get(st.id), setting)
        if b is None and setting.first_year_rule == "band_b":
            b = "B"
        bands[st.id] = b

    teams = list(
        MentorTeam.objects
        .filter(course=course, year=year, academic_year=ay)
        .prefetch_related("members__student")
        .order_by("number")
    )

    placed = {
        m.student_id
        for t in teams
        for m in t.members.all()
    }

    marked = {
        u.student_id: u
        for u in UnplacedStudent.objects.filter(
            course=course, year=year, academic_year=ay
        )
    }

    return {
        "course": course,
        "year": year,
        "department": dept,
        "setting": setting,
        "rule": rule,
        "students": students,
        "cgpas": cgpas,
        "bands": bands,
        "teams": teams,
        "placed": placed,
        "marked": marked,
        "unplaced": [st for st in students if st.id not in placed],
        "needed": teams_needed(len(students), rule),
        "closed": any(t.is_closed for t in teams),
    }, None


def _name(u):
    return (f"{u.first_name} {u.last_name}".strip() or u.username)


def _options_for(student, band, ctx):
    """Teams this student may be placed into, with the reason when they cannot."""
    rule, teams = ctx["rule"], ctx["teams"]
    can_create_more = not ctx["closed"] and len(teams) < ctx["needed"]
    fallback_open = _fallback_open(teams, rule, band, can_create_more)

    out = []
    for t in teams:
        ok, as_extra, _why = _can_join(t, rule, band, fallback_open)
        if not ok:
            continue
        out.append({
            "team_id": t.id,
            "number": t.number,
            "as_extra": as_extra,
            "label": (
                f"Team {t.number} — as an extra {band}" if as_extra
                else f"Team {t.number} — {band or 'open'} slot open"
            ),
        })
    return out, can_create_more


def _why_unplaced(band, options, ctx):
    """
    Why this student has nowhere to go, in the advisor's words.

    Worked out from the live state, never hard-coded, so it stays true when
    the HOD changes the rules mid-year.
    """
    rule, teams = ctx["rule"], ctx["teams"]

    if not teams:
        return "No team has been formed yet"
    if ctx["closed"]:
        return "Team formation closed before they joined"

    if rule.grade_mix == "abc" and band:
        normal = any(
            not t.is_closed
            and band not in _slot_state(t, rule)["bands"]
            and _slot_state(t, rule)["size"] < rule.team_size
            for t in teams
        )
        if normal:
            return f"Did not join - a {band}-band slot is still open"
        if len(teams) < ctx["needed"]:
            return f"No {band}-band slot available - another team can still be formed"
        if options:
            return f"No {band}-band slot available - can only go in as an extra"
        return f"No {band}-band slot available and no team has room"

    if any(_slot_state(t, rule)["size"] < rule.team_size for t in teams):
        return "Did not join - a team still has room"
    return "Every team is full"


def _band_supply(ctx):
    """
    How the bands divide against the number of teams. This is what tells the
    advisor, before anything is placed, that some teams cannot be balanced.
    """
    rule, needed = ctx["rule"], ctx["needed"]
    counts = {"A": 0, "B": 0, "C": 0, "none": 0}
    for b in ctx["bands"].values():
        counts[b if b in ("A", "B", "C") else "none"] += 1

    rows = []
    for b in ("A", "B", "C"):
        have = counts[b]
        rows.append({
            "band": b,
            "have": have,
            "needed": needed,
            "spare": max(0, have - needed),
            "short": max(0, needed - have),
        })
    return {"bands": rows, "unbanded": counts["none"]}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def advisor_teams(request):
    """Unplaced students, every team, band counts. Own class only."""
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    rule = ctx["rule"]

    unplaced = []
    for st in ctx["unplaced"]:
        band = ctx["bands"].get(st.id)
        options, _ = _options_for(st, band, ctx)
        mark = ctx["marked"].get(st.id)
        unplaced.append({
            "student_id": st.id,
            "name": _name(st),
            "roll_number": st.roll_number,
            "band": band or "",
            "cgpa": ctx["cgpas"].get(st.id),
            "options": options,
            "reason": mark.reason if mark else _why_unplaced(band, options, ctx),
            "left_unplaced": bool(mark),
            "marked_by": _name(mark.marked_by) if mark and mark.marked_by_id else "",
        })

    teams = []
    for t in ctx["teams"]:
        state = _slot_state(t, rule)
        teams.append({
            "id": t.id,
            "number": t.number,
            "size": state["size"],
            "team_size": rule.team_size,
            "is_closed": t.is_closed,
            "is_complete": state["size"] >= rule.team_size,
            "open_bands": (
                sorted({"A", "B", "C"} - state["bands"])
                if rule.grade_mix == "abc" and state["size"] < rule.team_size
                else []
            ),
            "mentor_id": t.mentor_id,
            "mentor_name": _name(t.mentor) if t.mentor_id else "",
            "members": [
                {
                    "student_id": m.student_id,
                    "name": _name(m.student),
                    "roll_number": m.student.roll_number,
                    "band": m.band,
                    "is_extra": m.is_extra,
                }
                for m in state["members"]
            ],
        })

    complete = sum(1 for t in teams if t["is_complete"])
    waiting = [u for u in unplaced if not u["left_unplaced"]]

    return Response({
        "academic_year": ay,
        "class": {
            "course_id": ctx["course"].id,
            "course_name": ctx["course"].name,
            "year": ctx["year"],
            "year_label": YEAR_LABEL.get(ctx["year"], ctx["year"]),
        },
        "rule": {
            "team_size": rule.team_size,
            "grade_mix": rule.grade_mix,
            "fallback": rule.fallback,
            "fallback_label": rule.get_fallback_display(),
        },
        "cards": {
            "students": len(ctx["students"]),
            "teams_expected": ctx["needed"],
            "teams_formed": len(teams),
            "complete_teams": complete,
            "incomplete_teams": len(teams) - complete,
            "unplaced": len(waiting),
            "left_unplaced": len(unplaced) - len(waiting),
        },
        "band_supply": _band_supply(ctx),
        "formation_closed": ctx["closed"],
        "can_close": not ctx["closed"] and not waiting and len(teams) > 0,
        "can_leave_unplaced": rule.fallback == "leave_short" or not any(
            u["options"] for u in unplaced
        ),
        "unplaced_students": unplaced,
        "teams": teams,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def advisor_place_student(request):
    """
    Place one student into one team.

    The band rule is re-checked here. The filtered dropdown the advisor saw
    is a convenience; this is the guard.
    """
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    if ctx["closed"]:
        return Response({"detail": "Team formation has closed."},
                        status=status.HTTP_400_BAD_REQUEST)

    ser = PlaceStudentSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    sid = ser.validated_data["student_id"]
    tid = ser.validated_data.get("team_id")

    student = next((s for s in ctx["students"] if s.id == sid), None)
    if not student:
        return Response({"detail": "That student is not in your class."},
                        status=status.HTTP_404_NOT_FOUND)
    if sid in ctx["placed"]:
        return Response({"detail": f"{_name(student)} is already in a team."},
                        status=status.HTTP_409_CONFLICT)

    band = ctx["bands"].get(sid)

    # ---------- no team_id: leave this student out on purpose ----------
    if not tid:
        options, _ = _options_for(student, band, ctx)
        UnplacedStudent.objects.update_or_create(
            student=student, academic_year=ay,
            defaults={
                "course": ctx["course"],
                "year": ctx["year"],
                "band": band or "",
                "reason": _why_unplaced(band, options, ctx),
                "marked_by": request.user,
            },
        )
        return Response({
            "student_id": sid,
            "left_unplaced": True,
            "detail": (
                f"{_name(student)} is marked as deliberately left out of a team. "
                "You can still place them until formation closes."
            ),
        })

    with transaction.atomic():
        team = (
            MentorTeam.objects
            .select_for_update()
            .filter(id=tid, course=ctx["course"], year=ctx["year"],
                    academic_year=ay)
            .first()
        )
        if not team:
            return Response({"detail": "That team is not in your class."},
                            status=status.HTTP_404_NOT_FOUND)

        can_create_more = len(ctx["teams"]) < ctx["needed"]
        fallback_open = _fallback_open(ctx["teams"], ctx["rule"], band,
                                       can_create_more)
        ok, as_extra, why = _can_join(team, ctx["rule"], band, fallback_open)
        if not ok:
            return Response({"detail": why},
                            status=status.HTTP_400_BAD_REQUEST)

        MentorTeamMember.objects.create(
            team=team, student=student, band=band or "", is_extra=as_extra
        )
        UnplacedStudent.objects.filter(student=student, academic_year=ay).delete()

    return Response({
        "student_id": sid,
        "team_id": team.id,
        "number": team.number,
        "is_extra": as_extra,
        "detail": (
            f"{_name(student)} placed in Team {team.number}"
            + (" as an extra member." if as_extra else ".")
        ),
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def advisor_auto_fill(request):
    """
    Place everyone still unplaced, applying the department fallback rule.

    Scarcest band first, so the students with the fewest options are seated
    before the common ones take the remaining slots. Anyone who genuinely
    cannot be placed is reported rather than silently skipped.
    """
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    if ctx["closed"]:
        return Response({"detail": "Team formation has closed."},
                        status=status.HTTP_400_BAD_REQUEST)
    if not ctx["unplaced"]:
        return Response({"placed": 0, "detail": "Everyone is already in a team."})

    rule = ctx["rule"]
    supply = {r["band"]: r["have"] for r in _band_supply(ctx)["bands"]}
    order = sorted(
        ctx["unplaced"],
        key=lambda s: supply.get(ctx["bands"].get(s.id) or "", 999),
    )

    placed, skipped = [], []

    with transaction.atomic():
        teams = list(
            MentorTeam.objects
            .select_for_update()
            .filter(course=ctx["course"], year=ctx["year"], academic_year=ay)
            .prefetch_related("members")
            .order_by("number")
        )

        for student in order:
            band = ctx["bands"].get(student.id)
            can_create_more = len(teams) < ctx["needed"]

            # 1. a team with a proper slot
            target, as_extra = None, False
            for t in teams:
                ok, extra, _ = _can_join(t, rule, band, False)
                if ok and not extra:
                    target, as_extra = t, False
                    break

            # 2. start a new team
            if target is None and can_create_more:
                target = MentorTeam.objects.create(
                    course=ctx["course"], year=ctx["year"], academic_year=ay,
                    number=(teams[-1].number + 1 if teams else 1),
                )
                teams.append(target)

            # 3. the fallback
            if target is None:
                fallback_open = _fallback_open(teams, rule, band, False)
                for t in teams:
                    ok, extra, _ = _can_join(t, rule, band, fallback_open)
                    if ok:
                        target, as_extra = t, extra
                        break

            if target is None:
                skipped.append({
                    "student_id": student.id,
                    "name": _name(student),
                    "band": band or "",
                    "why": "No team can take this student under the current rules.",
                })
                continue

            MentorTeamMember.objects.create(
                team=target, student=student, band=band or "", is_extra=as_extra
            )
            UnplacedStudent.objects.filter(
                student=student, academic_year=ay
            ).delete()
            target.refresh_from_db()
            placed.append({
                "student_id": student.id,
                "name": _name(student),
                "team_id": target.id,
                "number": target.number,
                "is_extra": as_extra,
            })

    return Response({
        "placed": len(placed),
        "skipped": len(skipped),
        "results": placed,
        "unplaceable": skipped,
        "detail": (
            f"{len(placed)} student(s) placed."
            + (f" {len(skipped)} could not be placed." if skipped else "")
        ),
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def advisor_close_formation(request):
    """
    Lock the teams so students can no longer join or leave.

    Refuses while anyone is unplaced — the disabled button in the UI is a
    convenience, this is the real guard.
    """
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    if ctx["closed"]:
        return Response({"detail": "Team formation is already closed."},
                        status=status.HTTP_400_BAD_REQUEST)
    if not ctx["teams"]:
        return Response({"detail": "No team has been formed yet."},
                        status=status.HTTP_400_BAD_REQUEST)
    waiting = [s for s in ctx["unplaced"] if s.id not in ctx["marked"]]
    if waiting:
        names = ", ".join(_name(s) for s in waiting[:5])
        more = len(waiting) - 5
        return Response({
            "detail": (
                f"{len(waiting)} student(s) are not in a team yet: "
                f"{names}{f' and {more} more' if more > 0 else ''}. "
                "Place them, or mark them as deliberately left unplaced."
            ),
        }, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        MentorTeam.objects.filter(
            course=ctx["course"], year=ctx["year"], academic_year=ay
        ).update(is_closed=True)

    return Response({
        "detail": (
            f"Formation closed. {len(ctx['teams'])} teams are locked — "
            "pick a mentor for each one on the Mentors tab."
        ),
        "teams": len(ctx["teams"]),
    })


# ==================================================================
# =================TUTOR: MENTORS =========================
# ==================================================================

def _previous_year(ay):
    """"2026-2027" -> "2025-2026". None when the string is not that shape."""
    try:
        start = int(ay.split("-")[0])
    except (ValueError, IndexError, AttributeError):
        return None
    return f"{start - 1}-{start}"


def _eligible_mentors(dept, rule, ay):
    """
    Teachers who may mentor a team this year, best first.

    Rotation and the advisor exclusion are PREFERENCES, not hard limits. If
    they leave fewer teachers than the class has teams, the held-back ones are
    added at the end and the shortfall is reported, rather than the class
    quietly ending up with teams that have no mentor.

    Returns (ordered_mentors, info).
    """
    from core.academics.models import YearTutor

    teachers = list(department_mentors(dept))
    loads = {
        row["mentor_id"]: row["n"]
        for row in MentorAllocation.objects
        .filter(department=dept, academic_year=ay)
        .filter(Q(is_active=True) | Q(status="pending"))
        .values("mentor_id").annotate(n=Count("id"))
    }

    excluded_rotation = set()
    prev = _previous_year(ay)
    if rule.skip_last_year_mentors and prev:
        excluded_rotation = set(
            MentorAllocation.objects
            .filter(department=dept, academic_year=prev)
            .values_list("mentor_id", flat=True)
        )

    excluded_advisors = set()
    if rule.skip_class_advisors:
        excluded_advisors = set(
            YearTutor.objects.filter(teacher__department=dept)
            .values_list("teacher_id", flat=True)
        )

    def sort_key(t):
        if rule.tiebreak_fewest_mentees:
            return (loads.get(t.id, 0), _name(t))
        return (_name(t), 0)

    preferred, held_back = [], []
    for t in teachers:
        if t.id in excluded_rotation or t.id in excluded_advisors:
            held_back.append(t)
        else:
            preferred.append(t)

    preferred.sort(key=sort_key)
    held_back.sort(key=sort_key)

    ids = {t.id for t in teachers}
    return preferred + held_back, {
        "total_teachers": len(teachers),
        "eligible": len(preferred),
        "held_back_rotation": len(excluded_rotation & ids),
        "held_back_advisors": len(excluded_advisors & ids),
        "loads": loads,
        "preferred_ids": [t.id for t in preferred],
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def advisor_team_mentors(request):
    """
    GET  - every team with its students and its mentor, suggested where the
           advisor has not chosen one. Suggestions are stored the first time
           so the list is stable between page loads; ?resuggest=1 recomputes
           every team that has not been submitted.
    POST - set or clear one team's mentor: {"team_id": 5, "mentor_id": 9}.
           Send mentor_id null to clear it.
    """
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    dept, rule = ctx["department"], ctx["rule"]
    ordered, info = _eligible_mentors(dept, rule, ay)
    by_id = {m.id: m for m in ordered}

    # ---------- POST ----------
    if request.method == "POST":
        ser = SetTeamMentorSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tid = ser.validated_data["team_id"]
        mid = ser.validated_data.get("mentor_id")

        team = next((t for t in ctx["teams"] if t.id == tid), None)
        if not team:
            return Response({"detail": "That team is not in your class."},
                            status=status.HTTP_404_NOT_FOUND)
        if team.submitted_at:
            return Response({"detail": "This team has already gone to the HOD."},
                            status=status.HTTP_400_BAD_REQUEST)

        if mid is None:
            team.mentor = None
        else:
            mentor = by_id.get(mid)
            if not mentor:
                return Response(
                    {"detail": "That teacher is not in your department."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            team.mentor = mentor
        team.save(update_fields=["mentor"])

        return Response({
            "team_id": team.id,
            "number": team.number,
            "mentor_id": team.mentor_id,
            "mentor_name": _name(team.mentor) if team.mentor_id else "",
            "detail": (
                f"Team {team.number} - {_name(team.mentor)}"
                if team.mentor_id else f"Team {team.number} has no mentor."
            ),
        })

    # ---------- GET ----------
    open_teams = [t for t in ctx["teams"] if not t.submitted_at]
    resuggest = request.query_params.get("resuggest") in ("1", "true", "yes")

    # A plain GET reads. It used to assign a mentor to every team and save it
    # just because the tutor opened the page — so a refresh changed data, and a
    # browser prefetch could too. Suggestions are now written only when the
    # tutor explicitly asks for them.
    if resuggest and open_teams:
        with transaction.atomic():
            for i, team in enumerate(open_teams):
                pick = ordered[i] if i < len(ordered) else None
                team.mentor = pick
                team.mentor_was_suggested = pick
                team.save(update_fields=["mentor", "mentor_was_suggested"])
        # the in-memory teams are stale now; re-read so the response matches
        ctx["teams"] = list(
            MentorTeam.objects
            .filter(course=ctx["course"], year=ctx["year"], academic_year=ay)
            .select_related("mentor", "mentor_was_suggested")
            .prefetch_related("members__student")
            .order_by("number")
        )

    rows = []
    for t in ctx["teams"]:
        members = sorted(
            t.members.all(),
            key=lambda m: ({"A": 0, "B": 1, "C": 2}.get(m.band, 3), m.is_extra),
        )
        by_band = {"A": [], "B": [], "C": [], "": []}
        for m in members:
            by_band.setdefault(m.band or "", []).append({
                "student_id": m.student_id,
                "name": _name(m.student),
                "roll_number": m.student.roll_number,
                "is_extra": m.is_extra,
            })

        changed = bool(
            t.mentor_id and t.mentor_was_suggested_id
            and t.mentor_id != t.mentor_was_suggested_id
        )
        rows.append({
            "team_id": t.id,
            "number": t.number,
            "size": len(members),
            "a": by_band.get("A", []),
            "b": by_band.get("B", []),
            "c": by_band.get("C", []),
            "unbanded": by_band.get("", []),
            "mentor_id": t.mentor_id,
            "mentor_name": _name(t.mentor) if t.mentor_id else "",
            "suggested_id": t.mentor_was_suggested_id,
            "suggested_name": (
                _name(t.mentor_was_suggested) if t.mentor_was_suggested_id else ""
            ),
            "source": "changed" if changed else ("suggested" if t.mentor_id else "none"),
            "submitted": bool(t.submitted_at),
        })

    with_mentor = sum(1 for r in rows if r["mentor_id"])
    changed_n = sum(1 for r in rows if r["source"] == "changed")
    shortfall = max(0, len(rows) - info["eligible"])

    return Response({
        "academic_year": ay,
        "class": {
            "course_id": ctx["course"].id,
            "course_name": ctx["course"].name,
            "year": ctx["year"],
            "year_label": YEAR_LABEL.get(ctx["year"], ctx["year"]),
        },
        "formation_closed": ctx["closed"],
        "cards": {
            "teams": len(rows),
            "with_mentor": with_mentor,
            "without_mentor": len(rows) - with_mentor,
            "you_changed": changed_n,
            "mentors_needed": len(rows),
        },
        "mentor_pool": {
            "total_teachers": info["total_teachers"],
            "eligible": info["eligible"],
            "held_back_rotation": info["held_back_rotation"],
            "held_back_advisors": info["held_back_advisors"],
            "shortfall": shortfall,
            "note": (
                f"Only {info['eligible']} teacher(s) pass the department rules "
                f"but {len(rows)} team(s) need a mentor. Teachers held back by "
                "rotation are offered as well."
            ) if shortfall else "",
        },
        "mentor_options": [
            {
                "id": m.id,
                "name": _name(m),
                "assigned": info["loads"].get(m.id, 0),
                "preferred": m.id in info["preferred_ids"],
            }
            for m in ordered
        ],
        "can_submit": (
            ctx["closed"] and len(rows) > 0 and with_mentor == len(rows)
            and not all(r["submitted"] for r in rows)
        ),
        "already_submitted": bool(rows) and all(r["submitted"] for r in rows),
        "teams": rows,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def advisor_submit_teams(request):
    """
    Send the batch to the HOD.

    Writes one MentorAllocation per student - status 'pending',
    source 'advisor', proposed_by set - which is exactly what the existing HOD
    proposal screen already reads, so nothing downstream changes.

    Refuses unless formation is closed and every team has a mentor. A student
    who already has a proposal waiting is skipped and reported, because the
    model allows only one pending row per student per year.
    """
    ay = _year(request)
    ctx, err = _advisor_context(request, ay)
    if err:
        return err

    if not ctx["closed"]:
        return Response(
            {"detail": "Close team formation before sending anything to the HOD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    teams = [t for t in ctx["teams"] if not t.submitted_at]
    if not teams:
        return Response({"detail": "Every team has already gone to the HOD."},
                        status=status.HTTP_400_BAD_REQUEST)

    missing = [t.number for t in teams if not t.mentor_id]
    if missing:
        listed = ", ".join(f"Team {n}" for n in missing[:5])
        return Response({
            "detail": (
                f"{len(missing)} team(s) still need a mentor: {listed}"
                f"{' and more' if len(missing) > 5 else ''}."
            ),
        }, status=status.HTTP_400_BAD_REQUEST)

    dept = ctx["department"]
    already_pending = set(
        MentorAllocation.objects
        .filter(department=dept, academic_year=ay, status="pending")
        .values_list("student_id", flat=True)
    )

    created, skipped = [], []

    with transaction.atomic():
        for team in teams:
            for m in team.members.all():
                if m.student_id in already_pending:
                    skipped.append({
                        "student_id": m.student_id,
                        "name": _name(m.student),
                        "why": "Already has a proposal waiting with the HOD.",
                    })
                    continue

                MentorAllocation.objects.create(
                    student=m.student,
                    mentor=team.mentor,
                    department=dept,
                    academic_year=ay,
                    grade_band=m.band or "",
                    cgpa_at_allocation=ctx["cgpas"].get(m.student_id),
                    status="pending",
                    is_active=False,
                    source="advisor",
                    proposed_by=request.user,
                    reason=f"Team {team.number} proposed by the class in-charge",
                )
                created.append(m.student_id)

            team.submitted_at = timezone.now()
            team.proposed_by = request.user
            team.save(update_fields=["submitted_at", "proposed_by"])

    hod_now = _current_hod(dept)   # #50 ACTING HOD: the acting HOD when one is active
    if hod_now:
        notify(
            [hod_now],
            "A class in-charge sent a team allocation",
            f"{_name(request.user)} proposed {len(teams)} team(s) for "
            f"{ctx['course'].name} "
            f"{YEAR_LABEL.get(ctx['year'], ctx['year'])} Year - "
            f"{len(created)} student(s) waiting on your decision.",
        )

    return Response({
        "teams_sent": len(teams),
        "students": len(created),
        "skipped": skipped,
        "detail": (
            f"{len(teams)} team(s) sent to the HOD, covering "
            f"{len(created)} student(s)."
            + (f" {len(skipped)} student(s) were skipped." if skipped else "")
        ),
    }, status=status.HTTP_201_CREATED)


# ==================================================================
# ================= HOD: TEAM PROPOSALS ============================
# ==================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_team_proposals(request):
    """
    Team batches a tutor has sent, grouped by tutor and class.

    The pending MentorAllocation rows are matched back to their team by
    student, so the HOD reviews whole teams rather than 69 loose rows. Rows
    the advisor overrode are flagged, since those are the ones worth a look.

    Deciding still goes through the existing hod_decide_proposals endpoint —
    send the allocation_ids listed here, optionally with a mentor_id to swap
    the mentor while approving.
    """
    dept, setting, err = _dept_for(request)
    if err:
        return err
    ay = _year(request)

    teams = list(
        MentorTeam.objects
        .filter(academic_year=ay, submitted_at__isnull=False)
        .select_related("course", "mentor", "mentor_was_suggested", "proposed_by")
        .prefetch_related("members__student")
        .order_by("proposed_by_id", "number")
    )

    pending = {
        a.student_id: a
        for a in MentorAllocation.objects
        .filter(department=dept, academic_year=ay, status="pending")
        .select_related("student", "mentor")
    }
    if not pending:
        return Response({
            "academic_year": ay,
            "department": {"id": dept.id, "name": dept.name},
            "counts": {"batches": 0, "teams": 0, "students": 0, "overridden": 0},
            "batches": [],
        })

    batches = {}
    for team in teams:
        rows, ids = [], []
        for m in team.members.all():
            a = pending.get(m.student_id)
            if not a:
                continue
            rows.append({
                "allocation_id": a.id,
                "student_id": m.student_id,
                "name": _name(m.student),
                "roll_number": m.student.roll_number,
                "band": m.band,
                "is_extra": m.is_extra,
            })
            ids.append(a.id)

        if not rows:
            continue          # already decided, nothing waiting for this team

        changed = bool(
            team.mentor_id and team.mentor_was_suggested_id
            and team.mentor_id != team.mentor_was_suggested_id
        )

        key = (team.proposed_by_id or 0, team.course_id, team.year)
        b = batches.setdefault(key, {
            "key": f"advisor-{team.proposed_by_id}-{team.course_id}-{team.year}",
            "advisor_id": team.proposed_by_id,
            "advisor_name": _name(team.proposed_by) if team.proposed_by_id
                            else "Unknown advisor",
            "course_id": team.course_id,
            "course_name": team.course.name,
            "year": team.year,
            "year_label": YEAR_LABEL.get(team.year, team.year),
            "sent_at": team.submitted_at,
            "teams": [],
            "students": 0,
            "overridden": 0,
            "allocation_ids": [],
        })

        b["teams"].append({
            "team_id": team.id,
            "number": team.number,
            "mentor_id": team.mentor_id,
            "mentor_name": _name(team.mentor) if team.mentor_id else "",
            "suggested_name": (
                _name(team.mentor_was_suggested)
                if team.mentor_was_suggested_id else ""
            ),
            "advisor_overrode": changed,
            "size": len(rows),
            "has_extra": any(r["is_extra"] for r in rows),
            "a": [r for r in rows if r["band"] == "A"],
            "b": [r for r in rows if r["band"] == "B"],
            "c": [r for r in rows if r["band"] == "C"],
            "unbanded": [r for r in rows if not r["band"]],
            "allocation_ids": ids,
        })
        b["students"] += len(rows)
        b["overridden"] += 1 if changed else 0
        b["allocation_ids"].extend(ids)
        if team.submitted_at and team.submitted_at < b["sent_at"]:
            b["sent_at"] = team.submitted_at

    rows_out = sorted(batches.values(), key=lambda x: -x["students"])

    mentor_rows, _mentors, _loads = _mentor_rows(dept, setting, ay)

    return Response({
        "academic_year": ay,
        "department": {"id": dept.id, "name": dept.name},
        "counts": {
            "batches": len(rows_out),
            "teams": sum(len(b["teams"]) for b in rows_out),
            "students": sum(b["students"] for b in rows_out),
            "overridden": sum(b["overridden"] for b in rows_out),
        },
        "mentor_options": [
            {
                "id": m["id"],
                "name": m["name"],
                "assigned": m["assigned"],
                "capacity": m["capacity"],
                "available": m["available"],
            }
            for m in mentor_rows
        ],
        "how_to_decide": (
            "POST the allocation_ids to /api/mentoring/hod/decide-proposals/ "
            "with decision approve or reject. Add mentor_id to approve with a "
            "different mentor than the advisor proposed."
        ),
        "batches": rows_out,
    })