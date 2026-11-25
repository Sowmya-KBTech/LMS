"""
WAVE 3 PART 3 TESTS - online tests (the quiz, upgraded): question bank, test
builder, writing a test, marking MCQ / true-false, time limits.

Run:  python manage.py test modules.learning.tests_online -v 2
"""
import datetime
import importlib

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.notifications.models import Notification
from core.users.models import Department, User
from modules.learning.models import BankQuestion, Question, Quiz, QuizAttempt, QuizSection
from modules.teachingplan.models import CourseOutcome


class Base(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.dept = Department.objects.create(name="Mechanical", code="ME")
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=2)
        self.subject = Subject.objects.create(name="Thermodynamics", code="ME301", year=self.year, semester=3, credits=4)
        self.other_subject = Subject.objects.create(name="Fluids", code="ME302", year=self.year, semester=3, credits=4)
        self.teacher = mk("kavya", password="x", role="teacher", department=self.dept)
        self.other_teacher = mk("anand", password="x", role="teacher", department=self.dept)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.year,
                                                    subject=self.subject)
        TeachingAssignment.objects.create(teacher=self.other_teacher, course=self.course, year=self.year,
                                          subject=self.other_subject)
        self.s1 = mk("divya", password="x", role="student", course=self.course, year=2, semester=3, roll_number="R04")
        self.s2 = mk("ravi", password="x", role="student", course=self.course, year=2, semester=3, roll_number="R01")
        self.outsider = mk("zara", password="x", role="student", course=self.course, year=2, semester=3, roll_number="R09")
        for s in (self.s1, self.s2):
            Enrollment.objects.create(student=s, teaching_assignment=self.ta)
        self.co1 = CourseOutcome.objects.create(subject=self.subject, code="CO1", text="Apply the first law", order=1)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def add(self, **kw):
        data = {"subject": self.subject.id, "kind": "mcq", "text": "Q", "options": ["a", "b", "c", "d"],
                "answer": [1], "marks": 1, "difficulty": "easy", "unit": 1}
        data.update(kw)
        r = self.c(self.teacher).post("/api/online-tests/bank/", data, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data["questions"][0]["id"]

    def make_test(self, sections, publish=True, **kw):
        data = {"teaching_assignment": self.ta.id, "title": "Unit 1 test", "duration": 30,
                "shuffle_questions": False, "shuffle_options": False, "sections": sections}
        data.update(kw)
        r = self.c(self.teacher).post("/api/online-tests/tests/", data, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        tid = r.data["id"]
        if publish:
            p = self.c(self.teacher).post(f"/api/online-tests/tests/{tid}/publish/")
            self.assertEqual(p.status_code, 200, p.content)
        return tid

    def start(self, tid, user=None):
        return self.c(user or self.s1).post(f"/api/online-tests/tests/{tid}/start/")


class BankTests(Base):

    def test_teacher_adds_and_filters_questions(self):
        self.add(text="Which law is energy conservation?", outcome=self.co1.id, bloom="remember")
        self.add(kind="tf", text="Entropy can fall", options=[], answer=False, unit=2)
        self.add(kind="short", text="State the zeroth law", options=[], answer=None, model_answer="...", marks=2)
        r = self.c(self.teacher).get("/api/online-tests/bank/", {"subject": self.subject.id, "unit": 1})
        self.assertEqual(len(r.data), 2)
        self.assertEqual(r.data[0]["outcome_code"], "CO1")
        meta = self.c(self.teacher).get("/api/online-tests/bank/meta/", {"subject": self.subject.id}).data
        self.assertEqual((meta["count"], meta["units"], meta["by_kind"]["tf"]), (3, [1, 2], 1))

    def test_questions_are_checked(self):
        c = self.c(self.teacher)
        bad = [
            {"kind": "mcq", "text": "Q", "options": ["a", "b"], "answer": [0, 1]},
            {"kind": "mcq", "text": "Q", "options": ["a", ""], "answer": [0]},
            {"kind": "multi", "text": "Q", "options": ["a", "a"], "answer": [0]},
            {"kind": "tf", "text": "Q", "answer": "maybe"},
            {"kind": "mcq", "text": "", "options": ["a", "b"], "answer": [0]},
            {"kind": "mcq", "text": "Q", "options": ["a", "b"], "answer": [5]},
        ]
        for row in bad:
            r = c.post("/api/online-tests/bank/", {"subject": self.subject.id, **row}, format="json")
            self.assertEqual(r.status_code, 400, row)
        # all-or-nothing for several at once
        r = c.post("/api/online-tests/bank/", {"subject": self.subject.id, "questions": [
            {"kind": "tf", "text": "ok", "answer": True}, bad[0]]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(r.data["errors"]), 1)
        self.assertFalse(BankQuestion.objects.exists())

    def test_only_the_subjects_teachers_use_its_bank(self):
        r = self.c(self.other_teacher).get("/api/online-tests/bank/", {"subject": self.subject.id})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.c(self.s1).get("/api/online-tests/bank/", {"subject": self.subject.id}).status_code, 403)
        qid = self.add()
        self.assertEqual(self.c(self.other_teacher).delete(f"/api/online-tests/bank/{qid}/").status_code, 403)

    def test_a_used_question_is_archived_and_its_answer_locked(self):
        qid = self.add()
        self.make_test([{"pick": "fixed", "question_ids": [qid]}])
        r = self.c(self.teacher).patch(f"/api/online-tests/bank/{qid}/", {"answer": [2]}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.c(self.teacher).patch(f"/api/online-tests/bank/{qid}/", {"text": "Better wording"}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.c(self.teacher).delete(f"/api/online-tests/bank/{qid}/")
        self.assertTrue(r.data["archived"])
        self.assertFalse(BankQuestion.objects.get(pk=qid).is_active)


class BuilderTests(Base):

    def test_random_section_needs_marks_each_and_enough_questions(self):
        for _ in range(3):
            self.add(difficulty="easy")
        self.add(difficulty="hard")
        c = self.c(self.teacher)
        r = c.post("/api/online-tests/tests/check/", {"teaching_assignment": self.ta.id, "sections": [
            {"pick": "random", "count": 2}]}, format="json")
        self.assertEqual(r.status_code, 400)          # no marks_each
        r = c.post("/api/online-tests/tests/check/", {"teaching_assignment": self.ta.id, "sections": [
            {"pick": "random", "count": 3, "easy": 1, "hard": 2, "marks_each": 1}]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["ok"])
        self.assertIn("hard (1 short)", r.data["sections"][0]["problem"])
        tid = self.make_test([{"pick": "random", "count": 3, "easy": 1, "hard": 2, "marks_each": 1}], publish=False)
        r = c.post(f"/api/online-tests/tests/{tid}/publish/")
        self.assertEqual(r.status_code, 400)
        self.add(difficulty="hard")
        self.assertEqual(c.post(f"/api/online-tests/tests/{tid}/publish/").status_code, 200)
        self.assertEqual(Quiz.objects.get(pk=tid).total_marks, 3)

    def test_drafts_are_hidden_and_publishing_tells_students(self):
        qid = self.add()
        tid = self.make_test([{"pick": "fixed", "question_ids": [qid]}], publish=False)
        self.assertEqual(self.c(self.s1).get("/api/online-tests/tests/", {"teaching_assignment": self.ta.id}).data, [])
        self.assertEqual(self.c(self.s1).get("/api/quizzes/").data if isinstance(self.c(self.s1).get("/api/quizzes/").data, list)
                         else self.c(self.s1).get("/api/quizzes/").data["results"], [])
        self.assertEqual(self.start(tid).status_code, 404)
        self.c(self.teacher).post(f"/api/online-tests/tests/{tid}/publish/")
        self.assertEqual(Notification.objects.filter(title="New online test").count(), 2)
        self.assertEqual(len(self.c(self.s1).get("/api/online-tests/tests/").data), 1)

    def test_other_teachers_cannot_touch_the_test(self):
        qid = self.add()
        tid = self.make_test([{"pick": "fixed", "question_ids": [qid]}], publish=False)
        self.assertEqual(self.c(self.other_teacher).get(f"/api/online-tests/tests/{tid}/").status_code, 403)
        r = self.c(self.other_teacher).post("/api/online-tests/tests/", {"teaching_assignment": self.ta.id,
                                                                         "title": "x", "duration": 5, "sections": []},
                                            format="json")
        self.assertEqual(r.status_code, 403)

    def test_after_students_start_only_small_changes(self):
        qid = self.add()
        tid = self.make_test([{"pick": "fixed", "question_ids": [qid]}])
        self.start(tid)
        c = self.c(self.teacher)
        self.assertEqual(c.patch(f"/api/online-tests/tests/{tid}/", {"duration": 99}, format="json").status_code, 400)
        self.assertEqual(c.patch(f"/api/online-tests/tests/{tid}/", {"title": "Renamed"}, format="json").status_code, 200)
        self.assertEqual(c.delete(f"/api/online-tests/tests/{tid}/").status_code, 400)
        self.assertEqual(c.post(f"/api/online-tests/tests/{tid}/unpublish/").status_code, 400)


class WritingTests(Base):

    def setUp(self):
        super().setUp()
        self.q_mcq = self.add(text="mcq", answer=[2], marks=2, negative_marks="0.5")
        self.q_multi = self.add(kind="multi", text="multi", answer=[0, 3], marks=2)
        self.q_tf = self.add(kind="tf", text="tf", options=[], answer=True)
        self.q_short = self.add(kind="short", text="short", options=[], answer=None, marks=3)
        for i in range(4):
            self.add(text=f"pool {i}", unit=2, difficulty="medium")
        self.tid = self.make_test([
            {"pick": "fixed", "question_ids": [self.q_mcq, self.q_multi, self.q_tf]},
            {"pick": "random", "count": 2, "units": [2], "marks_each": 1},
        ])

    def test_start_gives_a_paper_without_answers(self):
        r = self.start(self.tid)
        self.assertEqual(r.status_code, 201)
        qs = r.data["questions"]
        self.assertEqual(len(qs), 5)
        self.assertTrue(all("answer" not in q and "model_answer" not in q for q in qs))
        self.assertEqual(qs[0]["options"][2], {"i": 2, "t": "c"})
        # starting again returns the same sitting
        again = self.start(self.tid)
        self.assertEqual((again.status_code, again.data["id"]), (200, r.data["id"]))
        self.assertEqual(self.start(self.tid, self.outsider).status_code, 404)

    def test_options_are_shuffled_per_student_but_answers_still_mark(self):
        Quiz.objects.filter(pk=self.tid).update(shuffle_options=True, shuffle_questions=True)
        a = self.start(self.tid).data
        mcq = next(q for q in a["questions"] if q["id"] == self.q_mcq)
        self.assertEqual(sorted(o["i"] for o in mcq["options"]), [0, 1, 2, 3])
        self.c(self.s1).post(f"/api/online-tests/attempts/{a['id']}/submit/",
                             {"answers": {str(self.q_mcq): 2}}, format="json")
        self.assertEqual(QuizAttempt.objects.get(pk=a["id"]).awarded[str(self.q_mcq)], 2.0)

    def test_autosave_marks_and_hides_score_until_written_answers_are_marked(self):
        a = self.start(self.tid).data
        c = self.c(self.s1)
        url = f"/api/online-tests/attempts/{a['id']}"
        r = c.post(f"{url}/save/", {"answers": {str(self.q_mcq): 0, str(self.q_multi): [3, 0], str(self.q_tf): "true",
                                                "999": 1, str(self.q_tf + 1000): 0}, "flagged": [self.q_tf], "left": 1},
                   format="json")
        self.assertEqual((r.status_code, r.data["answered"], r.data["tab_leaves"]), (200, 3, 1))
        c.post(f"{url}/save/", {"left": 2}, format="json")
        att = QuizAttempt.objects.get(pk=a["id"])
        self.assertEqual((att.tab_leaves, att.flagged, att.answers[str(self.q_multi)]), (3, [self.q_tf], [0, 3]))
        # not a result yet: grades list and progress don't see it
        self.assertEqual(len(c.get("/api/quiz-attempts/").data if isinstance(c.get("/api/quiz-attempts/").data, list)
                             else c.get("/api/quiz-attempts/").data["results"]), 0)
        r = c.post(f"{url}/submit/", format="json")
        # mcq wrong: no negative marking on this test -> 0; multi 2; tf 1
        self.assertEqual(r.data["score"], 3.0)
        self.assertFalse(r.data["being_marked"])
        self.assertEqual(c.post(f"{url}/save/", {"answers": {}}, format="json").status_code, 400)
        self.assertEqual(self.start(self.tid).status_code, 400)

    def test_negative_marks_and_written_answers(self):
        tid = self.make_test([{"pick": "fixed", "question_ids": [self.q_mcq, self.q_short]}],
                             negative_marking=True, title="With short answer")
        self.assertFalse(Quiz.objects.get(pk=tid).results_released)
        a = self.start(tid).data
        r = self.c(self.s1).post(f"/api/online-tests/attempts/{a['id']}/submit/",
                                 {"answers": {str(self.q_mcq): 1, str(self.q_short): "Heat equals work"}}, format="json")
        self.assertEqual((r.data["score"], r.data["being_marked"]), (None, True))
        att = QuizAttempt.objects.get(pk=a["id"])
        self.assertEqual((att.score, att.written_pending, att.awarded[str(self.q_short)]), (-0.5, True, None))
        lst = self.c(self.s1).get("/api/online-tests/tests/", {"teaching_assignment": self.ta.id}).data
        mine = next(t for t in lst if t["id"] == tid)["attempt"]
        self.assertEqual((mine["score"], mine["being_marked"]), (None, True))

    def test_time_up_submits_what_was_saved(self):
        a = self.start(self.tid).data
        c = self.c(self.s1)
        c.post(f"/api/online-tests/attempts/{a['id']}/save/", {"answers": {str(self.q_tf): True}}, format="json")
        QuizAttempt.objects.filter(pk=a["id"]).update(ends_at=timezone.now() - datetime.timedelta(minutes=5))
        r = c.post(f"/api/online-tests/attempts/{a['id']}/save/", {"answers": {str(self.q_mcq): 2}}, format="json")
        self.assertEqual((r.status_code, r.data["status"]), (400, "submitted"))
        att = QuizAttempt.objects.get(pk=a["id"])
        self.assertEqual((att.status, att.score), ("submitted", 1.0))
        self.assertEqual(Notification.objects.filter(recipient=self.teacher, title="Online test submitted").count(), 1)

    def test_closed_and_upcoming_tests_cannot_be_started(self):
        Quiz.objects.filter(pk=self.tid).update(opens_at=timezone.now() + datetime.timedelta(hours=2))
        self.assertIn("opens at", self.start(self.tid).data["detail"])
        Quiz.objects.filter(pk=self.tid).update(opens_at=None, due_date=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(self.start(self.tid).data["detail"], "This test is closed.")

    def test_review_only_when_the_teacher_allows(self):
        a = self.start(self.tid).data
        c = self.c(self.s1)
        c.post(f"/api/online-tests/attempts/{a['id']}/submit/", format="json")
        self.assertEqual(c.get(f"/api/online-tests/attempts/{a['id']}/review/").status_code, 403)
        Quiz.objects.filter(pk=self.tid).update(show_answers=True)
        r = c.get(f"/api/online-tests/attempts/{a['id']}/review/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(next(q for q in r.data["questions"] if q["id"] == self.q_mcq)["answer"], [2])
        self.assertEqual(self.c(self.s2).get(f"/api/online-tests/attempts/{a['id']}/review/").status_code, 404)

    def test_teacher_sees_who_started(self):
        self.start(self.tid)
        r = self.c(self.teacher).get(f"/api/online-tests/tests/{self.tid}/attempts/")
        self.assertEqual([x["roll_number"] for x in r.data["attempts"]], ["R04"])
        self.assertEqual([x["roll_number"] for x in r.data["not_started"]], ["R01"])
        self.assertEqual(r.data["test"]["writing"], 1)


class LegacyQuizTests(Base):

    def test_old_quizzes_move_into_the_bank_and_still_work(self):
        quiz = Quiz.objects.create(title="Old quiz", teaching_assignment=self.ta, created_by=self.teacher,
                                   duration=10, total_marks=3)
        Question.objects.create(quiz=quiz, text="Old Q1", option1="w", option2="x", option3="y", option4="z",
                                correct_answer=2, marks=2)
        Question.objects.create(quiz=quiz, text="Old Q2", option1="w", option2="x", option3="y", option4="z",
                                correct_answer=4, marks=1)
        mig = importlib.import_module("modules.learning.migrations.0002_online_tests")
        mig.legacy_quizzes_to_bank(django_apps, None)
        sec = QuizSection.objects.get(quiz=quiz)
        bank = list(BankQuestion.objects.filter(id__in=sec.question_ids).order_by("id"))
        self.assertEqual([(b.text, b.answer, b.marks) for b in bank], [("Old Q1", [1], 2), ("Old Q2", [3], 1)])
        Quiz.objects.filter(pk=quiz.id).update(shuffle_questions=False, shuffle_options=False)
        a = self.start(quiz.id).data
        r = self.c(self.s1).post(f"/api/online-tests/attempts/{a['id']}/submit/",
                                 {"answers": {str(bank[0].id): 1, str(bank[1].id): 0}}, format="json")
        self.assertEqual(r.data["score"], 2.0)


# ============================================================ WAVE 3 PART 3b
class MarkingTests(Base):

    def setUp(self):
        super().setUp()
        self.q_mcq = self.add(text="mcq", answer=[1], marks=2, outcome=self.co1.id)
        self.q_short = self.add(kind="short", text="short", options=[], answer=None, marks=3, outcome=self.co1.id)
        self.q_long = self.add(kind="long", text="long", options=[], answer=None, marks=5)
        self.tid = self.make_test([{"pick": "fixed", "question_ids": [self.q_mcq, self.q_short, self.q_long]}])
        self.a1 = self.start(self.tid, self.s1).data["id"]
        self.a2 = self.start(self.tid, self.s2).data["id"]
        self.c(self.s1).post(f"/api/online-tests/attempts/{self.a1}/submit/", {"answers": {
            str(self.q_mcq): 1, str(self.q_short): "dU = 30 kJ", str(self.q_long): "Carnot..."}}, format="json")
        self.c(self.s2).post(f"/api/online-tests/attempts/{self.a2}/submit/", {"answers": {
            str(self.q_mcq): 0, str(self.q_short): "no idea"}}, format="json")       # long left blank
        self.base = f"/api/online-tests/tests/{self.tid}"

    def mark(self, attempt, qid, marks, comment=""):
        return self.c(self.teacher).post(f"{self.base}/marking/{qid}/", {"attempt": attempt, "marks": marks,
                                                                         "comment": comment}, format="json")

    def test_overview_counts_written_answers(self):
        r = self.c(self.teacher).get(f"{self.base}/marking/")
        rows = {x["id"]: (x["answers"], x["marked"], x["marks"]) for x in r.data["questions"]}
        self.assertEqual(rows, {self.q_short: (2, 0, 3), self.q_long: (1, 0, 5)})     # a blank answer needs no marking
        self.assertEqual(r.data["left"], 3)
        self.assertEqual(self.c(self.other_teacher).get(f"{self.base}/marking/").status_code, 403)

    def test_marks_are_checked_and_totals_update(self):
        for bad in (-1, 3.5, 2.3, "x"):
            self.assertEqual(self.mark(self.a1, self.q_short, bad).status_code, 400, bad)
        self.assertEqual(self.mark(self.a2, self.q_long, 1).status_code, 400)     # blank answer stays 0
        r = self.mark(self.a1, self.q_short, 2.5, "Unit missing")
        self.assertEqual((r.status_code, r.data["score"], r.data["pending"]), (200, 4.5, True))
        r = self.mark(self.a1, self.q_long, 4)
        self.assertEqual((r.data["score"], r.data["pending"]), (8.5, False))
        a = QuizAttempt.objects.get(pk=self.a1)
        self.assertEqual(a.feedback, {str(self.q_short): "Unit missing"})
        lst = self.c(self.teacher).get(f"{self.base}/marking/{self.q_short}/").data["answers"]
        self.assertEqual([(x["roll_number"], x["marks"]) for x in lst], [("R01", None), ("R04", 2.5)])

    def test_release_needs_every_answer_marked_then_tells_students(self):
        self.assertEqual(self.c(self.teacher).post(f"{self.base}/release/").status_code, 400)
        mine = lambda: next(t for t in self.c(self.s1).get("/api/online-tests/tests/").data if t["id"] == self.tid)["attempt"]
        self.assertEqual((mine()["score"], mine()["being_marked"]), (None, True))
        self.mark(self.a1, self.q_short, 3)
        self.mark(self.a1, self.q_long, 5)
        self.mark(self.a2, self.q_short, 0)
        r = self.c(self.teacher).post(f"{self.base}/release/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((mine()["score"], mine()["being_marked"]), (10.0, False))
        self.assertEqual(Notification.objects.filter(title="Online test results").count(), 2)
        # released twice -> told once
        self.c(self.teacher).post(f"{self.base}/release/")
        self.assertEqual(Notification.objects.filter(title="Online test results").count(), 2)

    def test_results_by_student_outcome_and_hardest(self):
        self.mark(self.a1, self.q_short, 3)
        self.mark(self.a1, self.q_long, 5)
        self.mark(self.a2, self.q_short, 1)
        r = self.c(self.teacher).get(f"{self.base}/results/").data
        st = {x["roll_number"]: x for x in r["students"]}
        self.assertEqual((st["R04"]["score"], st["R04"]["sections"]), (10.0, [10.0]))
        self.assertEqual(st["R01"]["score"], 1.0)
        self.assertEqual((r["summary"]["wrote"], r["summary"]["average"], r["summary"]["highest"]), (2, 5.5, 10.0))
        co = {x["code"]: x["pct"] for x in r["by_outcome"]}
        self.assertEqual(co["CO1"], 60.0)          # (2 + 3 + 0 + 1) / (2 + 3 + 2 + 3)
        self.assertEqual(r["hardest"][0]["id"], self.q_mcq)     # 50% vs short 66.7% vs long 50% (by order)
        one = self.c(self.teacher).get(f"{self.base}/attempts/{self.a1}/").data
        self.assertEqual(next(q for q in one["questions"] if q["id"] == self.q_short)["given"], "dU = 30 kJ")

    def test_marking_does_not_notify_parents_until_release(self):
        from core.users.models import ParentProfile
        parent = User.objects.create_user("p1", password="x", role="parent")
        pp = ParentProfile.objects.create(user=parent) if hasattr(ParentProfile, "user") else None
        if pp is None:
            self.skipTest("no parent profile")
        pp.children.add(self.s1)
        self.mark(self.a1, self.q_short, 3)
        self.mark(self.a1, self.q_long, 5)
        self.mark(self.a2, self.q_short, 1)
        self.assertEqual(Notification.objects.filter(recipient=parent).count(), 0)
        self.c(self.teacher).post(f"{self.base}/release/")
        self.assertEqual(Notification.objects.filter(recipient=parent).count(), 1)

    def test_review_shows_teacher_comments(self):
        Quiz.objects.filter(pk=self.tid).update(show_answers=True)
        self.mark(self.a1, self.q_short, 3, "Well done")
        self.mark(self.a1, self.q_long, 5)
        self.mark(self.a2, self.q_short, 1)
        self.c(self.teacher).post(f"{self.base}/release/")
        r = self.c(self.s1).get(f"/api/online-tests/attempts/{self.a1}/review/")
        self.assertEqual(next(q for q in r.data["questions"] if q["id"] == self.q_short)["comment"], "Well done")


    def test_students_never_get_the_model_answer(self):
        Quiz.objects.filter(pk=self.tid).update(show_answers=True)
        self.mark(self.a1, self.q_short, 3)
        self.mark(self.a1, self.q_long, 5)
        self.mark(self.a2, self.q_short, 1)
        self.c(self.teacher).post(f"{self.base}/release/")
        r = self.c(self.s1).get(f"/api/online-tests/attempts/{self.a1}/review/")
        self.assertTrue(all("model_answer" not in q for q in r.data["questions"]))


class BankImportTests(Base):

    def upload(self, rows, commit=True):
        import io
        from openpyxl import Workbook, load_workbook
        c = self.c(self.teacher)
        t = c.get("/api/dataio/question_bank/template/", {"subject": self.subject.id})
        self.assertEqual(t.status_code, 200, getattr(t, "data", t.content[:200]))
        headers = [x.value for x in next(load_workbook(io.BytesIO(t.content)).active.iter_rows(max_row=1))]
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "bank.xlsx"
        from core.dataio.tests import post_upload    # the waiting /import/ URL was removed
        return post_upload(c, "question_bank", {"subject": self.subject.id, "mode": "add", "file": buf}, commit)

    def test_import_adds_every_type_and_export_round_trips(self):
        rows = [
            ["MCQ", "Energy law?", "Zeroth", "First", "Second", "Third", "", "", "B", 1, 1, "co1", "Remember", "Easy", 0.5, "", "Conservation"],
            ["Many answers", "Intensive properties?", "Pressure", "Volume", "Temperature", "Mass", "", "", "A, C", 2, 1, "", "", "", "", "", ""],
            ["True/False", "Entropy can fall", "", "", "", "", "", "", "False", 1, 2, "", "", "Hard", "", "", ""],
            ["Long", "Derive Carnot efficiency", "", "", "", "", "", "", "", 10, 2, "", "Analyse", "", "", "Points...", ""],
        ]
        r = self.upload(rows)
        self.assertEqual(r.status_code, 200, getattr(r, "data", r.content[:400]))
        self.assertTrue(r.data.get("saved"), r.data)
        got = {b.text: b for b in BankQuestion.objects.filter(subject=self.subject)}
        self.assertEqual((got["Energy law?"].answer, got["Energy law?"].outcome_id, float(got["Energy law?"].negative_marks)),
                         ([1], self.co1.id, 0.5))
        self.assertEqual(got["Intensive properties?"].answer, [0, 2])
        self.assertEqual((got["Entropy can fall"].answer, got["Entropy can fall"].difficulty), (False, "hard"))
        self.assertEqual((got["Derive Carnot efficiency"].kind, got["Derive Carnot efficiency"].bloom), ("long", "analyse"))
        exp = self.c(self.teacher).get("/api/dataio/question_bank/export/", {"subject": self.subject.id})
        self.assertEqual(exp.status_code, 200)

    def test_bad_rows_are_refused_with_reasons(self):
        rows = [
            ["MCQ", "Two answers?", "a", "b", "", "", "", "", "A, B", 1, "", "", "", "", "", "", ""],
            ["MCQ", "Answer off the end", "a", "b", "", "", "", "", "D", 1, "", "", "", "", "", "", ""],
            ["True/False", "Blank answer", "", "", "", "", "", "", "", 1, "", "", "", "", "", "", ""],
            ["MCQ", "Unknown CO", "a", "b", "", "", "", "", "A", 1, "", "CO9", "", "", "", "", ""],
        ]
        r = self.upload(rows)
        self.assertFalse(r.data.get("saved"))
        self.assertFalse(BankQuestion.objects.exists())

    def test_only_the_subjects_teachers_can_import(self):
        r = self.c(self.other_teacher).get("/api/dataio/question_bank/template/", {"subject": self.subject.id})
        self.assertEqual(r.status_code, 403)

