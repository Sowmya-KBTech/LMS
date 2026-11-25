# HOD results overview and class-advisor marksheet. Moved here from users/views.py.
# URLs unchanged (/api/users/hod-results/, /api/users/my-class/marksheet/) - see exams/users_urls.py.
# ===================== IMPORTS =====================


from rest_framework.decorators import (api_view, permission_classes)
from rest_framework.response import Response
from rest_framework.permissions import (IsAuthenticated)

from core.users.models import (User, Department)


# ===================== WHO IS HOD (#50 ACTING HOD) =====================
def _hod_departments(user):
    """
    Departments this user is HOD of. With the Acting HOD feature installed
    (core/users/acting_hod.py, by the teammate) an Acting HOD counts too.
    Until it is installed, only the regular HOD (Department.hod) counts -
    so this page never crashes for want of that file.
    """
    import importlib.util
    if importlib.util.find_spec("core.users.acting_hod") is not None:
        from core.users.acting_hod import hod_departments
        return hod_departments(user)
    return Department.objects.filter(hod=user)


# ===================== HOD: DEPARTMENT RESULTS =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hod_results(request):
    """
    Results overview for the HOD's department, grouped by semester.
    For each semester: pass/fail counts + per-subject pass & fail breakdown.
    Also returns an 'all' bucket combining every semester.
    """
    user = request.user

    departments = _hod_departments(user)
    if not departments.exists():
        return Response({"is_hod": False, "departments": []})

    from modules.exams.models import SemesterResult

    def build_bucket(results_qs):
        """Compute pass/fail + subject stats for a set of SemesterResults."""
        passed_count = 0
        failed_count = 0
        subject_stats = {}

        for sr in results_qs:
            entries = list(sr.entries.all())
            if not entries:
                continue
            all_pass = all(e.is_pass for e in entries)
            if all_pass:
                passed_count += 1
            else:
                failed_count += 1
            for e in entries:
                name = e.subject.name if e.subject else "Unknown"
                if name not in subject_stats:
                    subject_stats[name] = {"pass": 0, "fail": 0}
                if e.is_pass:
                    subject_stats[name]["pass"] += 1
                else:
                    subject_stats[name]["fail"] += 1

        total_evaluated = passed_count + failed_count
        pass_pct = round((passed_count / total_evaluated) * 100, 1) if total_evaluated else 0

        subjects = []
        for name, s in subject_stats.items():
            total = s["pass"] + s["fail"]
            fail_rate = round((s["fail"] / total) * 100, 1) if total else 0
            pass_rate = round((s["pass"] / total) * 100, 1) if total else 0
            subjects.append({
                "subject": name,
                "passed": s["pass"],
                "failed": s["fail"],
                "total": total,
                "fail_rate": fail_rate,
                "pass_rate": pass_rate,
            })
        subjects.sort(key=lambda x: x["fail_rate"], reverse=True)

        return {
            "evaluated": total_evaluated,
            "passed": passed_count,
            "failed": failed_count,
            "pass_percent": pass_pct,
            "subjects": subjects,
        }

    result = []
    for dept in departments:
        students = User.objects.filter(role="student", department=dept)
        student_ids = list(students.values_list("id", flat=True))

        all_results = list(
            SemesterResult.objects
            .filter(student_id__in=student_ids, is_published=True)
            .prefetch_related("entries__subject")
        )

        # which semesters actually have data
        semesters_present = sorted({sr.semester for sr in all_results})

        # build one bucket per semester + an "all" bucket
        by_semester = {}
        for sem in semesters_present:
            sem_results = [sr for sr in all_results if sr.semester == sem]
            by_semester[str(sem)] = build_bucket(sem_results)

        all_bucket = build_bucket(all_results)

        result.append({
            "id": dept.id,
            "name": dept.name,
            "total_students": students.count(),
            "semesters": semesters_present,   # e.g. [1, 3]
            "all": all_bucket,                # combined
            "by_semester": by_semester,       # {"1": {...}, "3": {...}}
        })

    return Response({"is_hod": True, "departments": result})


# ===================== TUTOR: CLASS MARK SHEET (BY SEMESTER) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_class_marksheet(request):
    """
    Printable class mark sheet for the tutor — grouped by semester so the
    teacher can pick which semester to print. Published results only.

    Per class: list of semesters that have data, and for each semester a
    full matrix (every class student x every subject) with marks/max,
    grade, pass/fail, and an overall result per student.
    """
    user = request.user

    from core.academics.models import YearTutor
    from modules.exams.models import SemesterResult

    tutor_links = (
        YearTutor.objects.filter(teacher=user).select_related("course", "year")
    )
    if not tutor_links.exists():
        return Response({"is_tutor": False, "classes": []})

    classes = []
    for link in tutor_links:
        course = link.course
        year_number = link.year.year_number

        students = list(
            User.objects.filter(role="student", course=course, year=year_number)
            .order_by("roll_number")
        )
        student_ids = [s.id for s in students]

        # every published result for the class, any semester
        results = (
            SemesterResult.objects
            .filter(student_id__in=student_ids, is_published=True)
            .prefetch_related("entries__subject")
        )

        # group by semester: subjects seen + per-student marks
        by_sem = {}   # sem -> {"subjects": set, "per_student": {sid: {...}}}
        for sr in results:
            sem = sr.semester
            bucket = by_sem.setdefault(sem, {"subjects": set(), "per_student": {}})
            entries = list(sr.entries.all())
            marks = {}
            passed = 0
            failed = 0
            for e in entries:
                name = e.subject.name if e.subject else "Unknown"
                bucket["subjects"].add(name)
                if e.is_pass:
                    passed += 1
                else:
                    failed += 1
                marks[name] = {
                    "obtained": e.marks_obtained,   # None = absent
                    "max": e.max_marks,
                    "grade": e.grade,
                    "is_pass": e.is_pass,
                }
            bucket["per_student"][sr.student_id] = {
                "marks": marks,
                "passed": passed,
                "failed": failed,
                "has": bool(entries),
            }

        semesters = sorted(by_sem.keys())

        by_semester = {}
        for sem in semesters:
            bucket = by_sem[sem]
            subjects = sorted(bucket["subjects"])
            rows = []
            for s in students:
                ps = bucket["per_student"].get(s.id)
                if ps and ps["has"]:
                    result = "fail" if ps["failed"] > 0 else "pass"
                    rows.append({
                        "id": s.id,
                        "username": s.username,
                        "name": s.display_name,
                        "roll_number": s.roll_number,
                        "marks": ps["marks"],
                        "result": result,
                        "passed": ps["passed"],
                        "failed": ps["failed"],
                    })
                else:
                    # student has no published result for this semester
                    rows.append({
                        "id": s.id,
                        "username": s.username,
                        "name": s.display_name,
                        "roll_number": s.roll_number,
                        "marks": {},
                        "result": "pending",
                        "passed": 0,
                        "failed": 0,
                    })
            by_semester[str(sem)] = {"subjects": subjects, "students": rows}

        classes.append({
            "course_id": course.id,
            "course_name": course.name,
            "year_number": year_number,
            "semesters": semesters,         # e.g. [3, 4]
            "by_semester": by_semester,     # {"3": {...}, "4": {...}}
        })

    return Response({"is_tutor": True, "classes": classes})