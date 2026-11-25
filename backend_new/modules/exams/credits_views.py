"""
WAVE 3 PART 1B - results under the regulation (CBCS).

  GET /api/results/credits/me/                 the signed-in student's credits, SGPA/CGPA,
                                               arrears and every semester's results
  GET /api/results/credits/<student_id>/       the same for one student - the student,
                                               their parent, class in-charge, mentor, HOD,
                                               the Principal, college admins (as the
                                               progress report)
  GET /api/results/entry-rules/?subject=&course=&year=&semester=
                                               exam admin: each student's regulation rule
                                               for this subject, so the entry grid can show
                                               the grade before saving (the server grades again)
  GET /api/results/arrear-roster/?subject=     exam admin: students with an arrear in this
                                               subject, for entering a re-exam
"""
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users.models import User

from .grading import rules_for, semester_summary
from .models import ResultEntry
from .report_views import _can_see_student
from .views import is_exam_admin


def _student_payload(student, published_only=True):
    data = semester_summary(student, published_only=published_only)
    data["student"] = {
        "id": student.id, "name": student.display_name, "roll_number": student.roll_number or "",
        "course": student.course.name if getattr(student, "course_id", None) else "",
        "batch_year": student.batch_year, "semester": student.semester,
    }
    return data


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_credits(request):
    if request.user.role != "student":
        return Response({"detail": "Only a student has their own credits page."}, status=403)
    return Response(_student_payload(request.user))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_credits(request, student_id):
    student = get_object_or_404(User, pk=student_id, role="student")
    if not _can_see_student(request.user, student):
        return Response({"detail": "You can't see this student's results."}, status=403)
    # the exam admin may also see results not published yet
    return Response(_student_payload(student, published_only=not is_exam_admin(request.user)))


def _rule_payload(rules):
    r, reg = rules["rule"], rules["regulation"]
    return {
        "regulation": reg.name, "kind": r.kind,
        "internal_max": r.internal_max, "end_max": r.end_max,
        "min_end_pct": float(r.min_end_pct), "min_total_pct": float(r.min_total_pct),
        "reattempt_internal": reg.reattempt_internal,
        "grades": [{"code": g.code, "outcome": g.outcome,
                    "min_mark": None if g.min_mark is None else float(g.min_mark),
                    "points": None if g.points is None else float(g.points)} for g in rules["grades"]],
        "hand_grades": [g.code for g in rules["grades"] if g.outcome in ("arrear", "excluded")],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def entry_rules(request):
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)
    from core.academics.models import Subject
    subject = get_object_or_404(Subject, pk=request.query_params.get("subject"))
    students = User.objects.filter(role="student")
    p = request.query_params
    if p.get("ids"):
        students = students.filter(id__in=[int(x) for x in p["ids"].split(",") if x.isdigit()])
    elif p.get("course") and p.get("year") and p.get("semester"):
        students = students.filter(course_id=p["course"], year=p["year"], semester=p["semester"])
    else:
        return Response({"detail": "Give the class (course, year, semester) or the student ids."}, status=400)
    rules, by_student = {}, {}
    for s in students:
        r = rules_for(s, subject)
        if r is None:
            by_student[s.id] = None
            continue
        key = r["regulation"].id
        rules.setdefault(key, _rule_payload(r))
        by_student[s.id] = key
    return Response({"subject": {"id": subject.id, "name": subject.name, "kind": subject.kind},
                     "rules": rules, "students": by_student})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def arrear_roster(request):
    if not is_exam_admin(request.user):
        return Response({"detail": "Only admin or exam admin."}, status=403)
    from core.academics.models import Subject
    subject = get_object_or_404(Subject, pk=request.query_params.get("subject"))
    entries = (ResultEntry.objects.filter(subject=subject, is_pass=False, result__is_published=True)
               .exclude(outcome="excluded").select_related("result__student")
               .order_by("result__student__roll_number"))
    return Response({
        "subject": {"id": subject.id, "name": subject.name, "semester": subject.semester},
        "students": [{
            "student": e.result.student_id, "student_name": e.result.student.display_name,
            "student_roll_no": e.result.student.roll_number or "", "semester": e.result.semester,
            "attempt": e.attempt, "exam_session": e.exam_session, "grade": e.grade,
            "internal_marks": e.internal_marks, "end_marks": e.end_marks, "marks_obtained": e.marks_obtained,
        } for e in entries],
    })
