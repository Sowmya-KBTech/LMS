# courses/services.py
# ===================== ENROLLMENT HELPER =====================

def enroll_student(student):
    """
    Auto-enroll one student into all TeachingAssignments that match their
    course + year + semester. Skips duplicates. Returns the number created.

    Today every subject is core, so a student is enrolled into everything for
    their course-semester. When electives arrive (Subject.is_elective), add
    `.exclude(subject__is_elective=True)` here so only core subjects are
    auto-enrolled and electives are left for student self-enrollment.
    """
    from core.academics.models import TeachingAssignment, Enrollment

    if not student.course or not student.year or not student.semester:
        return 0

    assignments = TeachingAssignment.objects.filter(
        course=student.course,
        year__year_number=student.year,
        subject__semester=student.semester,
    ).exclude(subject__is_elective=True)

    created = 0
    for assignment in assignments:
        _, was_created = Enrollment.objects.get_or_create(
            student=student,
            teaching_assignment=assignment,
        )
        if was_created:
            created += 1

    return created