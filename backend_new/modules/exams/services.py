# ===================== GRADING =====================
# Single source of truth for grade bands and pass mark.
# Change these and every result re-grades consistently.
PASS_PERCENT = 40
GRADE_BANDS = [
    (90, "O"),
    (80, "A+"),
    (70, "A"),
    (60, "B+"),
    (50, "B"),
    (40, "C"),
    (0,  "F"),
]


def compute_grade(marks_obtained, max_marks):
    """
    Returns (grade_letter, is_pass) from a score.
    Absent or blank -> ('F', False).
    """
    if marks_obtained is None or max_marks in (None, 0):
        return ("F", False)
    pct = (float(marks_obtained) / float(max_marks)) * 100
    for threshold, letter in GRADE_BANDS:
        if pct >= threshold:
            grade = letter
            break
    else:
        grade = "F"
    is_pass = pct >= PASS_PERCENT
    return (grade, is_pass)


# ===================== GRADE POINTS =====================
# Keyed by the SAME letters as GRADE_BANDS above.
# Do NOT keep this as a parallel ordered list -- if a band is ever added
# here without a point value, the lookup raises instead of silently
# scoring it 0.
GRADE_POINTS = {
    "O":  10,
    "A+": 9,
    "A":  8,
    "B+": 7,
    "B":  6,
    "C":  5,
    "F":  0,
}


def grade_point(letter):
    """
    Returns the numeric point for a grade letter.
    Unknown letter -> None (caller decides what to do; never assume 0).
    """
    if not letter:
        return None
    return GRADE_POINTS.get(letter.strip().upper())


# ===================== CGPA =====================
# CGPA is ALWAYS computed live, never stored.
# Two reasons it must never be cached on another model:
#   1. Revaluation rewrites ResultEntry.marks_obtained after publication.
#   2. Publishing a new semester changes it.
# Any stored copy goes stale silently.
def get_cgpa(student):
    """
    Returns (cgpa, reason).

    cgpa   -- float rounded to 2 places, or None when it cannot be trusted
    reason -- None on success, otherwise a short machine-readable code:
                'no_results'   no published semester results yet
                'no_credits'   at least one graded subject has credits = 0
                'bad_grade'    a grade letter with no point mapping

    Only PUBLISHED semesters are counted. Unpublished marks must never
    reach eligibility checks.

    On 'no_credits' this deliberately refuses to return a number.
    A CGPA computed while some subjects carry credits = 0 looks perfectly
    plausible and is wrong -- it silently weights the syllabus by whichever
    subjects happen to have been filled in.
    """
    from .models import SemesterResult

    entries = []
    results = SemesterResult.objects.filter(
        student=student,
        is_published=True,
    ).prefetch_related("entries__subject")

    for result in results:
        for entry in result.entries.all():
            entries.append(entry)

    if not entries:
        return (None, "no_results")
 
    # WAVE 3 PART 1B: one calculation for everything (CGPA, placement, reports):
    # the student's regulation decides how arrears count; with no regulation
    # set up it gives the same numbers as before.
    from .grading import semester_summary
    summary = semester_summary(student)
    return (summary["cgpa"], summary["cgpa_problem"])


# ===================== ARREARS =====================
def get_arrear_count(student):
    """
    Number of CURRENT standing arrears across published semesters.

    NOTE: this is current standing only, not history.
    SemesterResult is unique per (student, semester), so a re-exam can only
    overwrite the existing ResultEntry -- the fact that a subject was ever
    failed is not recoverable from the schema.
    """
    from .models import ResultEntry

    return ResultEntry.objects.filter(
        result__student=student,
        result__is_published=True,
        is_pass=False,
    ).exclude(outcome="excluded").count()      # WAVE 3: a withdrawn subject (W) is not an arrear


# ===================== PASSING YEAR =====================
def get_passing_year(student):
    """
    Expected year of graduation.

    Derived, never stored: batch_year (admission year) + the number of
    Year rows configured for the student's course.

    Returns None when batch_year or course is missing rather than guessing.
    """
    batch = getattr(student, "batch_year", None)
    course = getattr(student, "course", None)

    if not batch or not course:
        return None

    # FIX #34: use the highest year number (4 for a B.E.), not the number of
    # Year rows. With only Year 1 and Year 4 created, count() gave 2 and a
    # 2023 batch showed "passing out 2025" instead of 2027.
    from django.db.models import Max
    duration = course.years.aggregate(m=Max("year_number"))["m"] or 0
    if duration <= 0:
        return None

    return batch + duration


# ===================== ACADEMIC STANDING (one call) =====================
def get_academic_standing(student):
    """
    Everything the placement eligibility check needs about a student's
    academics, in one call and one round of queries.

    Returns a dict:
        {
          'cgpa': float|None,
          'cgpa_reason': str|None,
          'arrears': int,
          'passing_year': int|None,
        }

    Placement (and IQAC, transcripts, anything else) should call THIS
    rather than re-deriving any of these values locally.
    """
    cgpa, reason = get_cgpa(student)
    return {
        "cgpa": cgpa,
        "cgpa_reason": reason,
        "arrears": get_arrear_count(student),
        "passing_year": get_passing_year(student),
    }


# ===================== LATEST EXAMINATION (revaluation) =====================
def latest_published_semester(student):
    """
    The student's LATEST examination: the highest semester whose results
    have been published for them. Revaluation is allowed for this semester
    only (review item 4.6) - and the student's screen shows only this one
    (4.7), by asking the server rather than working it out itself.

    Returns the semester number, or None if nothing is published yet.
    A student whose newest semester isn't published yet gets the previous
    one - that is the latest exam whose marks they can see.
    """
    from django.db.models import Max
    from .models import SemesterResult
    return (
        SemesterResult.objects.filter(student=student, is_published=True)
        .aggregate(m=Max("semester"))["m"]
    )


def revaluation_eligible_students(semester):
    """
    How many active students have `semester` as their LATEST published
    examination. Revaluation can only be opened for a semester where this is
    above zero (meeting point 4): opening it for an older semester would let
    nobody apply, and opening it before results are out would be a mistake.
    Same rule as latest_published_semester(), counted across students.
    """
    from django.db.models import Exists, OuterRef
    from .models import SemesterResult
    later = SemesterResult.objects.filter(
        student=OuterRef("student"),
        is_published=True,
        semester__gt=semester,
    )
    return (
        SemesterResult.objects
        .filter(semester=semester, is_published=True, student__is_active=True)
        .exclude(Exists(later))
        .values("student").distinct().count()
    )
