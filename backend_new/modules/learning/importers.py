"""
WAVE 3 PART 3b - question bank import / export (shared engine in core/dataio).
Registered from LearningConfig.ready(), so it only exists when the learning
module is on.

One file = one subject's question bank (the subject is chosen on the page).
Each row is one question of any type. Rows are ADDED to the bank; existing
questions are never changed by a file. Every row passes through
online_tests.clean_question - the same check as a question typed on the page.

(This replaces the old one-quiz MCQ import: quizzes became online tests, and
their questions now live in the subject's question bank.)
"""

from core.dataio import fields as F
from core.dataio.engine import Importer, OptionError, RowError

LETTERS = "ABCDEFGH"
KIND_TEXT = {
    "mcq": "mcq", "mcq - one answer": "mcq", "one answer": "mcq", "single": "mcq",
    "multi": "multi", "mcq - many answers": "multi", "many answers": "multi", "multiple": "multi",
    "tf": "tf", "true/false": "tf", "true / false": "tf", "true false": "tf",
    "short": "short", "short answer": "short", "long": "long", "long answer": "long",
}
KIND_OUT = {"mcq": "MCQ", "multi": "Many answers", "tf": "True/False", "short": "Short", "long": "Long"}
DIFF = {"easy": "easy", "e": "easy", "medium": "medium", "m": "medium", "hard": "hard", "h": "hard"}
BLOOM = {b: b for b in ("remember", "understand", "apply", "analyse", "evaluate", "create")}
BLOOM.update({"analyze": "analyse"})


def _answer(kind, text, n_options):
    """'B' / 'A, C' / 'True' -> the stored answer."""
    t = str(text or "").strip()
    if kind == "tf":
        v = {"true": True, "t": True, "false": False, "f": False}.get(t.lower())
        if v is None:
            raise RowError(["Answer must be True or False"])
        return v
    if kind in ("short", "long"):
        return None
    parts = [p.strip().upper() for p in t.replace(";", ",").replace(" ", ",").split(",") if p.strip()]
    if not parts:
        raise RowError(["Give the right answer as a letter, like B (or A, C for many answers)"])
    out = []
    for p in parts:
        if len(p) != 1 or p not in LETTERS[:n_options]:
            raise RowError([f"Answer '{p}' is not one of the options A-{LETTERS[n_options - 1]}"])
        out.append(LETTERS.index(p))
    return sorted(set(out))


class QuestionBankImporter(Importer):
    key = "question_bank"
    label = "questions"
    description = "Questions for one subject's question bank. They are added to the bank."
    file_stem = "question-bank"
    modes = ("add",)
    match_column = None
    option_keys = ["subject"]

    columns = [
        F.Column("kind", "Type", "always", "MCQ", "MCQ, Many answers, True/False, Short or Long.",
                 F.parse_choice(KIND_TEXT, "type", "MCQ, Many answers, True/False, Short or Long")),
        F.Column("text", "Question", "always", "Which law states that energy is conserved?"),
        F.Column("option_a", "Option A", False, "Zeroth law", "MCQ and Many answers only."),
        F.Column("option_b", "Option B", False, "First law"),
        F.Column("option_c", "Option C", False, "Second law"),
        F.Column("option_d", "Option D", False, "Third law"),
        F.Column("option_e", "Option E", False, ""),
        F.Column("option_f", "Option F", False, ""),
        F.Column("answer", "Answer", False, "B",
                 "MCQ: one letter (B). Many answers: letters (A, C). True/False: True or False. Short/Long: leave blank."),
        F.Column("marks", "Marks", False, "1", "Whole number. Blank = 1.", F.parse_int(1, 100, "marks")),
        F.Column("unit", "Unit", False, "1", "Unit number.", F.parse_int(1, 20, "unit")),
        F.Column("co", "CO", False, "CO1", "Course outcome code of this subject, like CO1."),
        F.Column("bloom", "Bloom level", False, "Remember", "Remember, Understand, Apply, Analyse, Evaluate or Create.",
                 F.parse_choice(BLOOM, "Bloom level", "Remember, Understand, Apply, Analyse, Evaluate or Create")),
        F.Column("difficulty", "Difficulty", False, "Easy", "Easy, Medium or Hard. Blank = Medium.",
                 F.parse_choice(DIFF, "difficulty", "Easy, Medium or Hard")),
        F.Column("negative_marks", "Negative marks", False, "0", "Taken off for a wrong answer, if the test uses them.",
                 F.parse_half(0, 100, "negative marks")),
        F.Column("model_answer", "Model answer", False, "", "Short / Long: the marking points (only teachers see it)."),
        F.Column("explanation", "Explanation", False, "The first law is conservation of energy.",
                 "Shown to students after results, if the test allows it."),
    ]

    def can_use(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        return user.role == "teacher" or user.is_superuser or (
            user.role == "admin" and (user.sub_role or "") in ("", "super_admin", "academic_admin"))

    def resolve_options(self, user, raw):
        from core.academics.models import Subject
        from .online_tests import teaches_subject
        try:
            sid = int(raw.get("subject") or 0)
        except (TypeError, ValueError):
            sid = 0
        subject = Subject.objects.filter(id=sid).first() if sid else None
        if subject is None:
            raise OptionError("Choose a subject first.")
        if not teaches_subject(user, subject.id):
            raise OptionError("Only the subject's teachers can use its question bank.", 403)
        return {"subject": subject}

    def file_name(self, options):
        s = options.get("subject")
        return f"question-bank-{s.code or s.name}".replace(" ", "-")[:60] if s else self.file_stem

    def prepare(self, user, options=None):
        from modules.teachingplan.models import CourseOutcome
        ctx = dict(options or {})
        ctx["outcomes"] = {o.code.lower(): o.id for o in CourseOutcome.objects.filter(subject=ctx["subject"])}
        return ctx

    def row_title(self, values, existing):
        t = values.get("text", "")
        return t if len(t) <= 60 else t[:57] + "…"

    def check_row(self, values, existing, ctx, user):
        from .online_tests import Refuse, clean_question
        kind = values.get("kind", "mcq")
        options = [values.get(f"option_{c}") for c in "abcdef"]
        options = [str(o).strip() for o in options if o not in (None, "")]
        data = {"kind": kind, "text": values.get("text", ""), "options": options,
                "answer": _answer(kind, values.get("answer"), max(len(options), 1)),
                "marks": values.get("marks", 1), "unit": values.get("unit"),
                "bloom": values.get("bloom", ""), "difficulty": values.get("difficulty", "medium"),
                "negative_marks": values.get("negative_marks", 0),
                "model_answer": values.get("model_answer", ""), "explanation": values.get("explanation", "")}
        co = str(values.get("co") or "").strip().lower()
        if co:
            if co not in ctx["outcomes"]:
                raise RowError([f"{values.get('co')} is not a course outcome of this subject"])
            data["outcome"] = ctx["outcomes"][co]
        try:
            return clean_question(data, ctx["subject"])
        except Refuse as e:
            raise RowError([e.msg])

    def save_row(self, payload, existing, ctx, user):
        from .models import BankQuestion
        BankQuestion.objects.create(subject=ctx["subject"], created_by=user, **payload)
        return None

    def export_queryset(self, user, params, options=None):
        from .models import BankQuestion
        return BankQuestion.objects.filter(subject=options["subject"], is_active=True).select_related("outcome").order_by("unit", "id")

    def export_row(self, b):
        row = {"kind": KIND_OUT[b.kind], "text": b.text, "marks": b.marks, "unit": b.unit or "",
               "co": b.outcome.code if b.outcome_id else "", "bloom": b.bloom.capitalize() if b.bloom else "",
               "difficulty": b.difficulty.capitalize(), "negative_marks": float(b.negative_marks) or "",
               "model_answer": b.model_answer, "explanation": b.explanation, "answer": ""}
        if b.kind in ("mcq", "multi"):
            for i, o in enumerate(b.options[:6]):
                row[f"option_{'abcdef'[i]}"] = o
            row["answer"] = ", ".join(LETTERS[i] for i in (b.answer or []))
        elif b.kind == "tf":
            row["answer"] = "True" if b.answer else "False"
        return row

    def template_example(self):
        return [
            ["MCQ", "Which law states that energy is conserved?", "Zeroth law", "First law", "Second law", "Third law",
             "", "", "B", "1", "1", "CO1", "Remember", "Easy", "", "", "The first law is conservation of energy."],
            ["True/False", "The entropy of an isolated system can decrease.", "", "", "", "", "", "", "False", "1", "2",
             "", "Understand", "Easy", "", "", ""],
            ["Short", "State the Kelvin-Planck statement.", "", "", "", "", "", "", "", "2", "2", "", "Remember",
             "Medium", "", "No engine can turn all the heat it takes in into work.", ""],
        ]
