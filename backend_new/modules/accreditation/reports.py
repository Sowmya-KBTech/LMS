"""
WAVE 2 - ACCREDITATION REPORTS: the numbers NAAC / NBA ask for, counted from
data the college already keeps. Read-only: nothing here writes to the database.

Every report gets a Scope (academic year + department) and returns:
    {"key", "title", "supports", "note", "columns": [...], "rows": [...],
     "total": {...} | None, "headline": "...", "available": True | False}

An academic year runs 1 June - 31 May (same rule as mentoring). A report whose
module is switched off comes back with available=False and a reason.

The "supports" line names the NAAC / NBA area a report feeds. Criterion
numbers change between NAAC / NBA cycles, so it names the area, not a number.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from django.apps import apps
from django.db.models import Count, Q
from django.utils import timezone

from core.users.models import Department, User

LOW_ATTENDANCE = 75.0


# ---------------------------------------------------------------- scope
@dataclass
class Scope:
    year: int                       # 2025 means academic year 2025-26
    department: Optional[Department]   # None = all departments (Optional: works on Python 3.9)

    @property
    def label(self):
        return f"{self.year}-{str(self.year + 1)[-2:]}"

    @property
    def start(self):
        return date(self.year, 6, 1)

    @property
    def end(self):
        return date(self.year + 1, 5, 31)

    def dt_range(self):
        tz = timezone.get_current_timezone()
        return (timezone.make_aware(datetime.combine(self.start, time.min), tz),
                timezone.make_aware(datetime.combine(self.end, time.max), tz))

    def students(self):
        qs = User.objects.filter(role="student", is_active=True)
        return qs.filter(department=self.department) if self.department else qs

    def teachers(self):
        qs = User.objects.filter(role="teacher", is_active=True)
        return qs.filter(department=self.department) if self.department else qs


def current_year(today=None):
    today = today or timezone.localdate()
    return today.year if today.month >= 6 else today.year - 1


def _pct(a, b):
    return round(a * 100.0 / b, 1) if b else None


def _dept_name(d_id, names):
    return names.get(d_id, "No department")


def _col(key, label, kind="text"):
    return {"key": key, "label": label, "type": kind}


def _missing(key, title, supports, why):
    return {"key": key, "title": title, "supports": supports, "note": why, "columns": [], "rows": [],
            "total": None, "headline": "Not available", "available": False}


def _names():
    return dict(Department.objects.values_list("id", "name"))


# ---------------------------------------------------------------- 1. student strength
def student_strength(scope):
    title, supports = "Student strength", "NAAC: student enrolment · NBA: student intake"
    names = _names()
    rows = defaultdict(int)
    for d_id, course, year in scope.students().values_list("department_id", "course__name", "year"):
        rows[(_dept_name(d_id, names), course or "No programme", year or 0)] += 1
    out = [{"department": d, "programme": c, "year": y or "—", "students": n}
           for (d, c, y), n in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))]
    total = sum(r["students"] for r in out)
    return {
        "key": "student-strength", "title": title, "supports": supports, "available": True,
        "note": "Active students as of today, by programme and year of study.",
        "columns": [_col("department", "Department"), _col("programme", "Programme"),
                    _col("year", "Year", "num"), _col("students", "Students", "num")],
        "rows": out, "total": {"department": "Total", "students": total},
        "headline": f"{total} students",
    }


# ---------------------------------------------------------------- 2. pass percentage
def pass_percentage(scope):
    title, supports = "Pass percentage", "NAAC: student performance · NBA: success rate"
    if not apps.is_installed("modules.exams"):
        return _missing("pass-percentage", title, supports, "The exams module is switched off.")
    from modules.exams.models import SemesterResult
    lo, hi = scope.dt_range()
    names = _names()
    qs = (SemesterResult.objects.filter(is_published=True, created_at__range=(lo, hi),
                                        student__in=scope.students())
          .annotate(fails=Count("entries", filter=Q(entries__is_pass=False)))
          .values_list("student__department_id", "student__course__name", "semester", "fails"))
    groups = defaultdict(lambda: [0, 0])
    for d_id, course, sem, fails in qs:
        g = groups[(_dept_name(d_id, names), course or "No programme", sem)]
        g[0] += 1
        if not fails:
            g[1] += 1
    out = [{"department": d, "programme": c, "semester": s, "appeared": a, "passed": p, "pass_percent": _pct(p, a)}
           for (d, c, s), (a, p) in sorted(groups.items())]
    a = sum(r["appeared"] for r in out)
    p = sum(r["passed"] for r in out)
    return {
        "key": "pass-percentage", "title": title, "supports": supports, "available": True,
        "note": "Published semester results added during the academic year. Passed = cleared every subject "
                "in that semester (no arrears).",
        "columns": [_col("department", "Department"), _col("programme", "Programme"),
                    _col("semester", "Semester", "num"), _col("appeared", "Appeared", "num"),
                    _col("passed", "Passed all subjects", "num"), _col("pass_percent", "Pass %", "pct")],
        "rows": out, "total": {"department": "Total", "appeared": a, "passed": p, "pass_percent": _pct(p, a)},
        "headline": f"{_pct(p, a)}% pass" if a else "No published results",
    }


# ---------------------------------------------------------------- 3 & 4. surveys
def _survey_rows(scope, templates):
    """Rating questions of published surveys started from these templates, within the year."""
    from modules.surveys.models import Answer, Participation, Survey
    from modules.surveys.views import eligible_users
    qs = (Survey.objects.filter(template__in=templates).exclude(status=Survey.Status.DRAFT)
          .filter(start_date__range=(scope.start, scope.end)).prefetch_related("questions"))
    # a department view shows only surveys aimed at that department: answers to a
    # college-wide (often anonymous) survey can't be split by department
    qs = qs.filter(department=scope.department) if scope.department else qs
    rows, all_ratings, eligible_total, answered_total = [], [], 0, 0
    for s in qs.order_by("start_date", "id"):
        eligible = eligible_users(s).count()
        answered = Participation.objects.filter(survey=s).count()
        eligible_total += eligible
        answered_total += answered
        who = "Teachers" if s.audience == Survey.Audience.STAFF else "Students"
        for q in s.questions.all():
            if q.kind != "rating":
                continue
            ratings = list(Answer.objects.filter(question=q, rating__isnull=False).values_list("rating", flat=True))
            all_ratings += ratings
            rows.append({"survey": s.title, "from": who, "question": q.text, "answers": len(ratings),
                         "average": round(sum(ratings) / len(ratings), 2) if ratings else None,
                         "agree_percent": _pct(sum(1 for r in ratings if r >= 4), len(ratings)),
                         "response_rate": _pct(answered, eligible)})
    return rows, all_ratings, qs.count(), _pct(answered_total, eligible_total)


def _survey_report(scope, key, title, supports, templates, template_names):
    if not apps.is_installed("modules.surveys"):
        return _missing(key, title, supports, "The surveys module is switched off.")
    rows, ratings, n, rate = _survey_rows(scope, templates)
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None
    return {
        "key": key, "title": title, "supports": supports, "available": True,
        "note": f"Surveys started from the {template_names} template that opened during the academic year. "
                "Rating questions only (1 = strongly disagree … 5 = strongly agree). Agree % = answers of 4 or 5."
                + ("" if not scope.department else
                   " This department view shows only surveys aimed at this department."),
        "columns": [_col("survey", "Survey"), _col("from", "From"), _col("question", "Question"),
                    _col("answers", "Answers", "num"), _col("average", "Average (of 5)", "num"),
                    _col("agree_percent", "Agree %", "pct"), _col("response_rate", "Response rate", "pct")],
        "rows": rows,
        "total": {"survey": f"All ({n} survey{'s' if n != 1 else ''})", "answers": len(ratings), "average": avg,
                  "agree_percent": _pct(sum(1 for r in ratings if r >= 4), len(ratings)), "response_rate": rate},
        "headline": f"Average {avg} of 5" if avg is not None else "No survey answers",
    }


def student_satisfaction(scope):
    return _survey_report(scope, "student-satisfaction", "Student satisfaction",
                          "NAAC: student satisfaction survey", ["student_satisfaction"],
                          "“Student satisfaction survey”")


def curriculum_feedback(scope):
    return _survey_report(scope, "curriculum-feedback", "Feedback on curriculum",
                          "NAAC: feedback on curriculum · NBA: course and programme feedback",
                          ["course_end", "curriculum_staff"],
                          "“Course-end feedback” or “Curriculum feedback from teachers”")


# ---------------------------------------------------------------- 5. mentor ratio
def mentor_ratio(scope):
    title, supports = "Mentor to student ratio", "NAAC: student mentoring · NBA: student support"
    if not apps.is_installed("modules.mentoring"):
        return _missing("mentor-ratio", title, supports, "The mentoring module is switched off.")
    from modules.mentoring.models import MentorAllocation
    names = _names()
    students = defaultdict(int)
    for d_id in scope.students().values_list("department_id", flat=True):
        students[d_id] += 1
    mentored, mentors = defaultdict(set), defaultdict(set)
    for d_id, sid, mid in (MentorAllocation.objects.filter(is_active=True, student__in=scope.students())
                           .values_list("student__department_id", "student_id", "mentor_id")):
        mentored[d_id].add(sid)
        mentors[d_id].add(mid)
    out = []
    for d_id in sorted(students, key=lambda i: _dept_name(i, names)):
        m = len(mentors[d_id])
        out.append({"department": _dept_name(d_id, names), "students": students[d_id],
                    "mentored": len(mentored[d_id]), "not_mentored": students[d_id] - len(mentored[d_id]),
                    "mentors": m, "ratio": f"1 : {round(len(mentored[d_id]) / m, 1)}" if m else "—"})
    s = sum(r["students"] for r in out)
    md = sum(r["mentored"] for r in out)
    m = len(set().union(*mentors.values())) if mentors else 0
    return {
        "key": "mentor-ratio", "title": title, "supports": supports, "available": True,
        "note": "Current mentor allocations (as of today). Ratio = mentored students per mentor.",
        "columns": [_col("department", "Department"), _col("students", "Students", "num"),
                    _col("mentored", "With a mentor", "num"), _col("not_mentored", "Without a mentor", "num"),
                    _col("mentors", "Mentors", "num"), _col("ratio", "Mentor : students")],
        "rows": out,
        "total": {"department": "Total", "students": s, "mentored": md, "not_mentored": s - md, "mentors": m,
                  "ratio": f"1 : {round(md / m, 1)}" if m else "—"},
        "headline": f"1 mentor : {round(md / m, 1)} students" if m else "No mentors allocated",
    }


# ---------------------------------------------------------------- 6. faculty development
FDP_GROUPS = [
    ("fdp", "FDP / training", ["fdp"]),
    ("workshops", "Workshops attended", ["workshop_attended"]),
    ("conducted", "Workshops conducted", ["workshop_conducted"]),
    ("papers", "Conference papers", ["conference"]),
    ("journals", "Journal papers", ["journal"]),
    ("certifications", "Certifications / MOOCs", ["certification"]),
    ("other", "Other", ["guest_lecture", "committee", "project", "other"]),
]


def faculty_development(scope):
    title, supports = "Faculty development", "NAAC: faculty development and research · NBA: faculty contributions"
    from core.users.models import FacultyParticipation
    names = _names()
    group_of = {cat: key for key, _, cats in FDP_GROUPS for cat in cats}
    teachers = defaultdict(int)
    for d_id in scope.teachers().values_list("department_id", flat=True):
        teachers[d_id] += 1
    counts = defaultdict(lambda: defaultdict(int))
    active = defaultdict(set)
    for d_id, fid, cat in (FacultyParticipation.objects
                           .filter(date__range=(scope.start, scope.end), faculty__in=scope.teachers(),
                                   status="verified")      # HRIS PART B: verified entries only
                           .values_list("faculty__department_id", "faculty_id", "category")):
        counts[d_id][group_of.get(cat, "other")] += 1
        active[d_id].add(fid)
    out = []
    for d_id in sorted(set(teachers) | set(counts), key=lambda i: _dept_name(i, names)):
        row = {"department": _dept_name(d_id, names), "teachers": teachers[d_id],
               "active": len(active[d_id])}
        for key, _, _ in FDP_GROUPS:
            row[key] = counts[d_id][key]
        row["total"] = sum(counts[d_id].values())
        out.append(row)
    total = {"department": "Total", "teachers": sum(r["teachers"] for r in out),
             "active": sum(r["active"] for r in out), "total": sum(r["total"] for r in out)}
    for key, _, _ in FDP_GROUPS:
        total[key] = sum(r[key] for r in out)
    return {
        "key": "faculty-development", "title": title, "supports": supports, "available": True,
        "note": "Entries teachers added under My Contributions and their HOD verified, dated within the academic year. "
                "Active = teachers with at least one entry.",
        "columns": [_col("department", "Department"), _col("teachers", "Teachers", "num"),
                    _col("active", "Active", "num")]
                   + [_col(key, label, "num") for key, label, _ in FDP_GROUPS] + [_col("total", "Total", "num")],
        "rows": out, "total": total,
        "headline": f"{total['total']} activities by {total['active']} teachers",
    }


# ---------------------------------------------------------------- 7. placement
def placement(scope):
    title, supports = "Placement and higher studies", "NAAC: placement and progression · NBA: placement"
    if not apps.is_installed("modules.placement"):
        return _missing("placement", title, supports, "The placement module is switched off.")
    import statistics
    from modules.placement.models import HigherStudies, Offer
    from modules.placement.views_reports import _passing_years

    passing_year = scope.year + 1          # the batch that finishes in this academic year
    students = list(scope.students().select_related("department", "course"))
    years_of = _passing_years(students)
    batch = [s for s in students if years_of.get(s.id) == passing_year]
    ids = [s.id for s in batch]
    best = {}
    for sid, pkg in (Offer.objects.filter(application__student_id__in=ids, status="accepted")
                     .values_list("application__student_id", "package_lpa")):
        if sid not in best or (pkg is not None and (best[sid] is None or pkg > best[sid])):
            best[sid] = pkg
    higher = set(HigherStudies.objects.filter(student_id__in=ids).values_list("student_id", flat=True))

    def row(label, members):
        mids = [m.id for m in members]
        placed = [i for i in mids if i in best]
        pkgs = [float(best[i]) for i in placed if best[i] is not None]
        n = len(mids)
        hs = len([i for i in mids if i in higher])
        return {"department": label, "students": n, "placed": len(placed), "placed_percent": _pct(len(placed), n),
                "higher_studies": hs, "progression_percent": _pct(len(placed) + hs, n),
                "median_lpa": round(statistics.median(pkgs), 2) if pkgs else None,
                "highest_lpa": round(max(pkgs), 2) if pkgs else None}

    groups = defaultdict(list)
    for s in batch:
        groups[s.department.name if s.department_id else "No department"].append(s)
    out = [row(k, v) for k, v in sorted(groups.items())]
    total = row("Total", batch)
    return {
        "key": "placement", "title": title, "supports": supports, "available": True,
        "note": f"Students graduating in {passing_year} (joining year + course length). Placed = an accepted "
                "offer; the same counting as the placement module's NIRF report.",
        "columns": [_col("department", "Department"), _col("students", "Final-year students", "num"),
                    _col("placed", "Placed", "num"), _col("placed_percent", "Placed %", "pct"),
                    _col("higher_studies", "Higher studies", "num"),
                    _col("progression_percent", "Placed + higher studies %", "pct"),
                    _col("median_lpa", "Median package (LPA)", "num"),
                    _col("highest_lpa", "Highest package (LPA)", "num")],
        "rows": out, "total": total,
        "headline": f"{total['placed_percent']}% placed" if batch else f"No students graduating in {passing_year}",
    }


# ---------------------------------------------------------------- 8. attendance
def attendance_summary(scope):
    title, supports = "Attendance summary", "Supporting data for student performance and mentoring"
    if not apps.is_installed("modules.attendance"):
        return _missing("attendance", title, supports, "The attendance module is switched off.")
    from modules.attendance.models import Attendance
    names = _names()
    per_student = defaultdict(lambda: [0, 0])
    info = {}
    for sid, d_id, course, yr, status, n in (
            Attendance.objects.filter(date__range=(scope.start, scope.end), student__in=scope.students())
            .values_list("student_id", "student__department_id", "student__course__name", "student__year", "status")
            .annotate(n=Count("id"))):
        per_student[sid][1] += n
        if status in ("present", "duty_leave"):
            per_student[sid][0] += n
        info[sid] = (_dept_name(d_id, names), course or "No programme", yr or 0)
    groups = defaultdict(lambda: {"students": 0, "hours": 0, "attended": 0, "low": 0})
    for sid, (att, tot) in per_student.items():
        g = groups[info[sid]]
        g["students"] += 1
        g["hours"] += tot
        g["attended"] += att
        if tot and att * 100.0 / tot < LOW_ATTENDANCE:
            g["low"] += 1
    out = [{"department": d, "programme": c, "year": y or "—", "students": g["students"], "hours": g["hours"],
            "attendance_percent": _pct(g["attended"], g["hours"]), "below_75": g["low"]}
           for (d, c, y), g in sorted(groups.items())]
    hours = sum(g["hours"] for g in groups.values())
    att = sum(g["attended"] for g in groups.values())
    return {
        "key": "attendance", "title": title, "supports": supports, "available": True,
        "note": "Hours marked during the academic year. Present and on duty count as attended; "
                "approved leave does not.",
        "columns": [_col("department", "Department"), _col("programme", "Programme"), _col("year", "Year", "num"),
                    _col("students", "Students", "num"), _col("hours", "Hours marked", "num"),
                    _col("attendance_percent", "Attendance %", "pct"), _col("below_75", "Below 75%", "num")],
        "rows": out,
        "total": {"department": "Total", "students": sum(r["students"] for r in out), "hours": hours,
                  "attendance_percent": _pct(att, hours), "below_75": sum(r["below_75"] for r in out)},
        "headline": f"{_pct(att, hours)}% attendance" if hours else "No attendance marked",
    }


REPORTS = [
    ("student-strength", student_strength),
    ("pass-percentage", pass_percentage),
    ("student-satisfaction", student_satisfaction),
    ("curriculum-feedback", curriculum_feedback),
    ("mentor-ratio", mentor_ratio),
    ("faculty-development", faculty_development),
    ("placement", placement),
    ("attendance", attendance_summary),
]
BY_KEY = dict(REPORTS)
