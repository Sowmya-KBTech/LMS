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