"""
WAVE 2 - ready-made surveys. Choosing one fills the survey builder; everything
can still be edited before publishing.

The wording is our own. The NAAC-style template follows the areas NAAC's
Student Satisfaction Survey asks about (teaching, learning, evaluation,
mentoring, facilities); if your IQAC uses NAAC's exact questions, edit them in
the builder before publishing.
"""

def _r(text):
    return {"kind": "rating", "text": text, "required": True, "options": []}


def _t(text, required=False):
    return {"kind": "text", "text": text, "required": required, "options": []}


TEMPLATES = [
    {
        "key": "course_end",
        "title": "Course-end feedback",
        "description": "How the course went this semester. Your answers are anonymous.",
        "audience": "students",
        "anonymous": True,
        "questions": [
            _r("The syllabus was covered fully and on time."),
            _r("Concepts were explained clearly."),
            _r("Classes started and ended on time."),
            _r("Examples, problems and applications helped me understand."),
            _r("Assignments and tests matched what was taught."),
            _r("Marked work was returned with useful comments."),
            _r("Doubts were answered in or after class."),
            _r("Overall, I am satisfied with this course."),
            _t("What should be kept the same?"),
            _t("What should be improved?"),
        ],
    },
    {
        "key": "student_satisfaction",
        "title": "Student satisfaction survey (NAAC-style)",
        "description": "The college's teaching, learning and support. Your answers are anonymous and help the "
                       "college improve.",
        "audience": "students",
        "anonymous": True,
        "questions": [
            _r("The syllabus for each subject was shared at the start of the semester."),
            _r("Teachers came prepared for class."),
            _r("Teachers explained clearly and checked that we understood."),
            _r("Teaching used examples, activities, projects or industry links, not only lectures."),
            _r("Internal assessment was fair and marks were shared on time."),
            _r("I could see my answer scripts / get feedback on my performance."),
            _r("My mentor helped me with academic and personal concerns."),
            _r("The college encouraged us to take part in seminars, workshops and competitions."),
            _r("Laboratories and equipment were available and working."),
            _r("The library and online resources met my needs."),
            _r("Classrooms, Wi-Fi and other facilities were adequate."),
            _r("Complaints and requests were handled fairly and quickly."),
            {"kind": "choice", "text": "Overall, how would you rate the quality of teaching and learning?",
             "required": True, "options": ["Excellent", "Very good", "Good", "Fair", "Poor"]},
            _t("Any suggestions to improve the college?"),
        ],
    },
    {
        "key": "curriculum_staff",
        "title": "Curriculum feedback from teachers",
        "description": "Your view of the syllabus you teach (used for curriculum review).",
        "audience": "staff",
        "anonymous": False,
        "questions": [
            _r("The syllabus is relevant to industry and current technology."),
            _r("The number of units and hours is right for the content."),
            _r("Course outcomes are clear and measurable."),
            _r("Recommended textbooks and references are adequate and current."),
            _r("Lab experiments match the theory courses."),
            _r("The syllabus leaves room for projects, case studies and self-learning."),
            {"kind": "multi", "text": "Which areas need the most change?", "required": False,
             "options": ["Course content", "Lab experiments", "Textbooks", "Assessment pattern",
                         "Electives offered", "Hours / credits"]},
            _t("Topics to add or remove, and why", required=False),
        ],
    },
]

BY_KEY = {t["key"]: t for t in TEMPLATES}
