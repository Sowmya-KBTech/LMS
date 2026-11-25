from datetime import date


from core.users.models import Department, User
from config.module_registry import module_enabled


# ================= ACADEMIC YEAR =================
def current_academic_year(today=None):
    """June to May. 15 Aug 2026 -> '2026-2027'. 15 Feb 2027 -> '2026-2027'."""
    today = today or date.today()
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{start + 1}"


def academic_year_choices(back=3):
    """Current year plus the previous few, newest first."""
    cur = int(current_academic_year().split("-")[0])
    return [f"{y}-{y + 1}" for y in range(cur, cur - back - 1, -1)]


# ================= CGPA =================
def student_cgpa(student):
    """
    Average percentage across all PUBLISHED semester results, on a 10-point
    scale. Returns None when the student has no published result yet
    (every first year, before semester 1 results).
    """
    from modules.exams.models import ResultEntry

    entries = ResultEntry.objects.filter(
        result__student=student,
        result__is_published=True,
        marks_obtained__isnull=False,
        max_marks__gt=0,
    ).values_list("marks_obtained", "max_marks")

    entries = list(entries)
    if not entries:
        return None

    total = sum(m / mx for m, mx in entries)
    return round((total / len(entries)) * 10, 2)


def cgpa_map(students):
    """Same as student_cgpa but one query for a whole list. {student_id: cgpa|None}"""
    from modules.exams.models import ResultEntry

    ids = [s.id if hasattr(s, "id") else s for s in students]
    rows = ResultEntry.objects.filter(
        result__student_id__in=ids,
        result__is_published=True,
        marks_obtained__isnull=False,
        max_marks__gt=0,
    ).values_list("result__student_id", "marks_obtained", "max_marks")

    acc = {}
    for sid, m, mx in rows:
        got, cnt = acc.get(sid, (0.0, 0))
        acc[sid] = (got + (m / mx), cnt + 1)

    out = {sid: None for sid in ids}
    for sid, (got, cnt) in acc.items():
        out[sid] = round((got / cnt) * 10, 2)
    return out


# ================= GRADE BAND =================
def band_for_cgpa(cgpa, setting):
    """A / B / C from the department's thresholds. None when there is no CGPA."""
    if cgpa is None:
        return None
    if cgpa >= setting.band_a_min:
        return "A"
    if cgpa >= setting.band_b_min:
        return "B"
    return "C"


# ================= ATTENDANCE =================
def attendance_map(students):
    """
    {student_id: percentage|None} for the given students.

    The calculation lives in modules/attendance/services.py. If the
    attendance module is switched off, every student gets None.
    """
    if not module_enabled("attendance"):
        return {s.id if hasattr(s, "id") else s: None for s in students}
    from modules.attendance.services import attendance_map as _attendance_map
    return _attendance_map(students)


# ================= DEPARTMENT SCOPE =================
def hod_departments(user):
    """Departments where this user is the HOD right now. Empty queryset for everyone else.
    #50 ACTING HOD: with the Acting HOD feature installed (core/users/acting_hod.py,
    by the teammate) the Acting HOD counts during their dates, else the regular HOD.
    Until it is installed, only the regular HOD counts - so no HOD screen crashes
    for want of that file. Every module that asks "is this the HOD?" comes here."""
    if not getattr(user, "is_authenticated", False):
        return Department.objects.none()
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is not None:
        from core.users.acting_hod import hod_departments as _hod_departments
        return _hod_departments(user)
    return Department.objects.filter(hod=user)


def is_hod(user):
    return hod_departments(user).exists()


def department_students(department, year=None, course=None, setting=None):
    """
    Students eligible for mentoring in this department.

    `setting.allocate_from_year` decides where mentoring starts. With the
    default of 2, first years never appear anywhere in the allocation
    screens — not in the pool, not in the counts, not in the totals.
    """
    qs = User.objects.filter(role="student", department=department, is_active=True)

    if setting is not None:
        qs = qs.filter(year__gte=setting.allocate_from_year)

    if year:
        qs = qs.filter(year=year)
    if course:
        qs = qs.filter(course_id=course)
    return qs.select_related("course", "department")


def department_mentors(department):
    """Teachers in this department. They are the pool a HOD can allocate from."""
    return User.objects.filter(
        role="teacher", department=department, is_active=True
    ).order_by("first_name", "username")


# ================= TUTOR =================
def advisor_for_student(student):
    """
    Your tutor is courses.YearTutor — one tutor per Year of a Course.
    Returns the teacher, or None when that year has no tutor assigned.
    """
    from core.academics.models import YearTutor

    if not student.course_id or not student.year:
        return None
    link = (
        YearTutor.objects
        .filter(course_id=student.course_id, year__year_number=student.year)
        .select_related("teacher")
        .first()
    )
    return link.teacher if link else None


# ================= MENTOR LOAD AND BEST FIT =================
def mentor_loads(department, academic_year):
    """
    {mentor_id: {"total": n, "A": n, "B": n, "C": n}} counting ACTIVE allocations
    only. Pending proposals are not load until the HOD approves them.
    """
    from .models import MentorAllocation

    rows = MentorAllocation.objects.filter(
        department=department, academic_year=academic_year, is_active=True
    ).values_list("mentor_id", "grade_band")

    out = {}
    for mid, band in rows:
        d = out.setdefault(mid, {"total": 0, "A": 0, "B": 0, "C": 0})
        d["total"] += 1
        if band in ("A", "B", "C"):
            d[band] += 1
    return out


def fit_score(load, band, setting):
    """
    Higher is better. Free places matter most; filling a missing grade band
    is weighted heavily because the composition rule depends on it.
    Returns -1 for a mentor already at capacity.
    """
    total = load["total"]
    if total >= setting.max_students_per_mentor:
        return -1

    score = (setting.max_students_per_mentor - total) * 2

    if setting.require_all_bands and band:
        if band == "A" and load["A"] == 0:
            score += 14
        elif band == "C" and load["C"] == 0:
            score += 14
        elif band == "B" and load["B"] == 0:
            score += 6

    if setting.require_all_bands and (load["A"] == 0 or load["C"] == 0):
        score += 5

    return score


def best_fit(mentors, loads, band, setting, exclude_id=None):
    """The mentor who should take a student of this band. None if all are full."""
    best, best_score = None, -1
    for m in mentors:
        if exclude_id and m.id == exclude_id:
            continue
        load = loads.get(m.id, {"total": 0, "A": 0, "B": 0, "C": 0})
        s = fit_score(load, band, setting)
        if s > best_score:
            best, best_score = m, s
    return best


def why_best_fit(mentor, loads, band, setting):
    """Plain reasons the UI shows under 'Why this mentor?'. No invented score."""
    load = loads.get(mentor.id, {"total": 0, "A": 0, "B": 0, "C": 0})
    cap = setting.max_students_per_mentor
    free = cap - load["total"]
    out = [f"{free} free place{'' if free == 1 else 's'} — currently {load['total']} of {cap}"]

    if setting.require_all_bands and band:
        if band == "A" and load["A"] == 0:
            out.append("Has no grade A student — this assignment satisfies the composition rule")
        if band == "C" and load["C"] == 0:
            out.append("Has no grade C student — this assignment satisfies the composition rule")
        if band == "B" and load["B"] == 0:
            out.append("Has no grade B student yet")

    if load["A"] == 0 or load["C"] == 0:
        out.append(
            f"Group is currently unbalanced — A {load['A']} · B {load['B']} · C {load['C']}"
        )

    lighter = sum(1 for v in loads.values() if v["total"] < load["total"])
    if lighter:
        out.append(f"{lighter} mentor(s) carry less, but this one needs the grade band more")
    else:
        out.append("Lightest load of all mentors")
    return out


def suggest_split(students, mentors, loads, setting):
    """
    Plan for the unassigned pool. Deals A students out first, then B, then C,
    always to the current best fit, simulating the load as it goes.
    Returns {mentor_id: [student_id, ...]}.
    """
    sim = {
        m.id: dict(loads.get(m.id, {"total": 0, "A": 0, "B": 0, "C": 0}))
        for m in mentors
    }
    plan = {}

    for band in ("A", "B", "C", None):
        for s in [x for x in students if x["band"] == band]:
            pick, pick_score = None, -99
            for m in mentors:
                sc = fit_score(sim[m.id], band, setting)
                if sc > pick_score:
                    pick, pick_score = m, sc
            if pick is None:
                continue
            sim[pick.id]["total"] += 1
            if band:
                sim[pick.id][band] += 1
            plan.setdefault(pick.id, []).append(s["id"])

    return plan


def group_balance(load, setting):
    """('ok'|'warn'|'bad', message) for a mentor's group."""
    if not setting.require_all_bands:
        return "ok", "No composition rule set"
    if load["total"] == 0:
        return "warn", "No students"
    if load["A"] == 0:
        return "bad", "No grade A student"
    if load["C"] == 0:
        return "bad", "No grade C student"
    if load["C"] / load["total"] < 0.15:
        return "warn", "Low on grade C"
    if load["A"] / load["total"] < 0.15:
        return "warn", "Low on grade A"
    return "ok", "Balanced"


# ================= TEAM-BASED ALLOCATION =================
def resolve_advisor_class(teacher):
    """
    The class this teacher is the tutor for, or None.

    Returns (course, year_number). Every advisor endpoint calls this and
    refuses when it is None, so a teacher can only ever act on their own class.

    .first() is safe because users.hod_assign_tutor refuses to give a teacher a
    second class. If that rule is ever relaxed this becomes a silent bug — the
    teacher would see one class with no sign the other exists — and these
    endpoints would need a ?course= &year= selector instead.
    """
    from core.academics.models import YearTutor

    link = (
        YearTutor.objects
        .filter(teacher=teacher)
        .select_related("course", "year")
        .first()
    )
    if not link:
        return None
    return link.course, link.year.year_number


def class_students(course, year):
    """Students in one class, in name order."""
    return (
        User.objects
        .filter(role="student", course=course, year=year, is_active=True)
        .select_related("course")
        .order_by("first_name", "last_name")
    )


def student_in_team(student, academic_year):
    """The student's team membership for a year, or None."""
    from .models import MentorTeamMember

    return (
        MentorTeamMember.objects
        .filter(student=student, team__academic_year=academic_year)
        .select_related("team", "team__course")
        .first()
    )


def mentor_rule_for(department, academic_year):
    """The department's team rules for a year. Creates defaults on first read."""
    from .models import MentorRule

    rule, _ = MentorRule.objects.get_or_create(
        department=department, academic_year=academic_year
    )
    return rule


def teams_needed(student_count, rule):
    """
    How many teams a class produces. Never hard-coded — 69 students at 3 per
    team is 23, but 74 at 3 is 25 with two teams carrying a fourth.
    """
    if student_count <= 0 or rule.team_size <= 0:
        return 0
    whole, left = divmod(student_count, rule.team_size)
    if left == 0:
        return whole
    if rule.fallback == "extra_member" and whole > 0:
        # the spare students join existing teams as extra members
        return whole
    return whole + 1


# ================= WHO IS HOD NOW (#50 ACTING HOD) =================
def current_hod(department):
    """
    The person holding the HOD powers of this department today: the Acting
    HOD while one is active, otherwise the regular HOD. views.py imports this
    for its notices. Falls back to the regular HOD if the Acting HOD feature
    (core/users/acting_hod.py) is not installed, so mentoring never crashes
    for want of that file.
    """
    if department is None:
        return None
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is not None:
        from core.users.acting_hod import current_hod as _current_hod
        return _current_hod(department)
    return department.hod if department.hod_id else None