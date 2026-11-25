"""
COURSE PLAN (Part A) TESTS - the new session columns and the submit rules.

Run:  python manage.py test modules.teachingplan -v 2
"""
from django.test import TestCase
from rest_framework.test import APIClient

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year
from core.users.models import Department, User
from modules.teachingplan.models import PlanUnit, TeachingPlan


class CoursePlanBase(TestCase):
    """Shared setup: hod (of ME), teacher ravi (assigned), another teacher, a student."""

    def setUp(self):
        mk = User.objects.create_user
        self.hod = mk("hodme", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.teacher = mk("ravi", password="x", role="teacher", department=self.dept)
        self.other = mk("meena", password="x", role="teacher", department=self.dept)
        course = Course.objects.create(name="B.E Mech")
        year = Year.objects.create(course=course, year_number=2)
        self.subject = Subject.objects.create(name="Thermodynamics", code="ME301", year=year, semester=3)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=course, year=year,
                                                    subject=self.subject)
        self.student = mk("asha", password="x", role="student", department=self.dept, course=course, year=2,
                          semester=3)
        Enrollment.objects.create(student=self.student, teaching_assignment=self.ta)

    def c(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def session(self, **over):
        s = {"topic": "First law", "hours": 1, "due": "2026-11-19", "period_no": 1, "unit_no": 2,
             "notes": "Closed systems", "mode": "lecture", "method": "case_study",
             "class_activity": "quiz", "beyond_activity": "industrial_visit"}
        s.update(over)
        return s

    def post(self, status, units, user=None):
        return self.c(user or self.teacher).post("/api/teaching-plans/", {
            "subject": self.subject.id, "semester": "Semester 3", "allotted_hours": 60,
            "status": status, "units": units}, format="json")



class CoursePlanTests(CoursePlanBase):

    # ---------------------------------------------------------------- saving
    def test_new_columns_are_saved_and_returned(self):
        r = self.post("draft", [self.session()])
        self.assertEqual(r.status_code, 201, r.content)
        u = PlanUnit.objects.get()
        self.assertEqual((u.unit_no, u.notes, u.mode, u.method, u.class_activity, u.beyond_activity),
                         (2, "Closed systems", "lecture", "case_study", "quiz", "industrial_visit"))
        mine = self.c(self.teacher).get("/api/teaching-plans/my/").json()[0]["units"][0]
        self.assertEqual((mine["unit_no"], mine["mode_label"], mine["method_label"],
                          mine["class_activity_label"], mine["beyond_activity_label"]),
                         (2, "Lecture", "Case study", "Quiz", "Industrial visit"))

    def test_draft_may_be_incomplete(self):
        r = self.post("draft", [self.session(unit_no=None, mode="", method="", class_activity="",
                                             beyond_activity="")])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PlanUnit.objects.get().mode, "")

    def test_bad_choices_are_refused(self):
        self.assertEqual(self.post("draft", [self.session(mode="dance")]).status_code, 400)
        self.assertEqual(self.post("draft", [self.session(unit_no=11)]).status_code, 400)
        self.assertEqual(self.post("draft", [self.session(unit_no=0)]).status_code, 400)

    # ---------------------------------------------------------------- sending to the HOD
    def test_submit_needs_unit_and_mode_on_planned_sessions(self):
        r = self.post("submitted", [self.session(mode="")])
        self.assertEqual(r.status_code, 400)
        self.assertIn("19-11-2026 needs a teaching mode", str(r.json()))
        r = self.post("submitted", [self.session(unit_no=None, mode="")])
        self.assertIn("needs a unit and a teaching mode", str(r.json()))
        self.assertFalse(TeachingPlan.objects.exists())                    # nothing half-saved

    def test_sessions_without_a_topic_are_not_sent(self):
        # "not yet planned" sessions stay on the page only; a blank topic is refused
        r = self.post("draft", [self.session(), self.session(topic="", due="2026-11-20")])
        self.assertEqual(r.status_code, 400)
        r = self.post("submitted", [self.session()])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(TeachingPlan.objects.get().status, "submitted")

    def test_submit_needs_at_least_one_planned_session(self):
        r = self.post("submitted", [])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Plan at least one session", str(r.json()))

    # ---------------------------------------------------------------- HOD and student see the columns
    def test_hod_and_student_see_the_new_columns(self):
        self.post("submitted", [self.session()])
        dept = self.c(self.hod).get("/api/teaching-plans/department/").json()
        self.assertEqual(dept[0]["units"][0]["mode_label"], "Lecture")
        plan = TeachingPlan.objects.get()
        self.assertEqual(self.c(self.hod).post(f"/api/teaching-plans/{plan.id}/approve/").status_code, 200)
        seen = self.c(self.student).get("/api/teaching-plans/student/").json()
        self.assertEqual((seen[0]["units"][0]["unit_no"], seen[0]["units"][0]["mode_label"]), (2, "Lecture"))

    def test_field_options(self):
        data = self.c(self.teacher).get("/api/teaching-plans/field_options/").json()
        self.assertEqual((data["units"][0], data["units"][-1], data["default_units"]), (1, 10, 5))
        self.assertIn({"value": "lab", "label": "Lab / practical"}, data["modes"])
        for key in ("methods", "class_activities", "beyond_activities"):
            self.assertTrue(data[key], key)

    def test_only_the_owner_writes(self):
        self.assertEqual(self.post("draft", [self.session()], user=self.other).status_code, 400)  # not assigned
        self.assertIn(self.post("draft", [self.session()], user=self.student).status_code, (400, 403))
        self.assertFalse(TeachingPlan.objects.exists())


# ============================================================================
# COURSE PLAN (Part B): course outcomes and planned vs delivered
# ============================================================================
from datetime import date, time, timedelta  # noqa: E402

from modules.teachingplan.models import CourseOutcome, SessionDelivery  # noqa: E402


class OutcomeTests(CoursePlanBase):

    def add_co(self, text="Apply the first law to closed systems", user=None, level="apply", subject=None):
        return self.c(user or self.teacher).post("/api/course-outcomes/", {
            "subject": (subject or self.subject).id, "text": text, "level": level}, format="json")

    def test_codes_are_numbered_and_listed(self):
        self.assertEqual(self.add_co().json()["code"], "CO1")
        self.assertEqual(self.add_co("Explain entropy and its meaning").json()["code"], "CO2")
        data = self.c(self.teacher).get(f"/api/course-outcomes/?subject={self.subject.id}").json()
        self.assertEqual([o["code"] for o in data["outcomes"]], ["CO1", "CO2"])
        self.assertEqual(data["outcomes"][0]["level_label"], "Apply")
        self.assertTrue(data["can_edit"])

    def test_who_may_edit(self):
        self.assertEqual(self.add_co(user=self.hod).status_code, 201)            # HOD of a teaching department
        self.assertEqual(self.add_co(user=self.other).status_code, 403)          # not teaching this subject
        self.assertEqual(self.add_co(user=self.student).status_code, 403)
        co = CourseOutcome.objects.get()
        self.assertEqual(self.c(self.other).patch(f"/api/course-outcomes/{co.id}/", {"text": "Changed text here"},
                                                  format="json").status_code, 403)
        self.assertEqual(self.c(self.other).delete(f"/api/course-outcomes/{co.id}/").status_code, 403)
        self.assertEqual(self.c(self.student).get(f"/api/course-outcomes/?subject={self.subject.id}")
                         .json()["outcomes"], [])
        self.assertEqual(self.c(self.teacher).patch(f"/api/course-outcomes/{co.id}/", {"level": "analyse"},
                                                    format="json").json()["level_label"], "Analyse")

    def test_bad_outcomes_are_refused(self):
        self.assertEqual(self.add_co(text="ab").status_code, 400)
        self.assertEqual(self.add_co(level="memorise").status_code, 400)

    def test_sessions_link_outcomes_of_their_own_subject_only(self):
        co = CourseOutcome.objects.create(subject=self.subject, code="CO1", text="Apply the first law")
        r = self.post("draft", [self.session(outcomes=[co.id])])
        self.assertEqual(r.status_code, 201, r.content)
        unit = self.c(self.teacher).get("/api/teaching-plans/my/").json()[0]["units"][0]
        self.assertEqual((unit["outcomes"], unit["outcome_codes"]), ([co.id], ["CO1"]))
        listed = self.c(self.teacher).get(f"/api/course-outcomes/?subject={self.subject.id}").json()
        self.assertEqual(listed["outcomes"][0]["sessions"], 1)
        other_subject = Subject.objects.create(name="Fluids", code="ME302", year=self.subject.year, semester=3)
        foreign = CourseOutcome.objects.create(subject=other_subject, code="CO1", text="Fluid statics")
        r = self.post("draft", [self.session(outcomes=[foreign.id])])
        self.assertEqual(r.status_code, 400)
        self.assertIn("another subject", str(r.json()))


class DeliveryTests(CoursePlanBase):

    def setUp(self):
        super().setUp()
        from modules.timetable.models import Semester, TimeSlot, TimetableEntry
        today = date.today()
        Semester.objects.create(name="Odd", start_date=today - timedelta(days=40),
                                end_date=today + timedelta(days=40), is_active=True)
        slot = TimeSlot.objects.create(period_no=1, start_time=time(9), end_time=time(10))
        for wd in range(5):
            TimetableEntry.objects.create(assignment=self.ta, day_of_week=wd, time_slot=slot)
        days = [d for d in self.c(self.teacher).get(
            f"/api/teaching-plans/class_days/?subject={self.subject.id}").json()["days"] if not d.get("holiday")]
        past = [d for d in days if d["date"] < today.isoformat()]
        self.d1, self.d2 = past[-3]["date"], past[-2]["date"]           # two planned past sessions
        self.free_after_d2 = [d["date"] for d in days if d["date"] > self.d2][0]   # past[-1] is free
        self.co = CourseOutcome.objects.create(subject=self.subject, code="CO1", text="Apply the first law")
        r = self.post("submitted", [self.session(due=self.d1, topic="First law", outcomes=[self.co.id]),
                                    self.session(due=self.d2, topic="Work and heat", unit_no=3)])
        self.assertEqual(r.status_code, 201, r.content)
        self.plan = TeachingPlan.objects.get()
        self.url = f"/api/teaching-plans/{self.plan.id}/delivery/"

    def record(self, user=None, **body):
        data = {"date": self.d1, "period_no": 1, "status": "as_planned"}
        data.update(body)
        return self.c(user or self.teacher).post(self.url, data, format="json")

    def test_report_before_anything_is_recorded(self):
        data = self.c(self.teacher).get(self.url).json()
        self.assertEqual([s["date"] for s in data["sessions"]], [self.d1, self.d2])
        self.assertEqual(data["counts"]["not_recorded"], 2)
        self.assertEqual(data["sessions"][0]["outcome_codes"], ["CO1"])
        self.assertEqual(data["units"], [{"unit_no": 2, "planned": 1, "done": 0}, {"unit_no": 3, "planned": 1, "done": 0}])
        self.assertTrue(data["can_record"])

    def test_record_as_planned(self):
        r = self.record()
        self.assertEqual(r.status_code, 200, r.content)
        rec = SessionDelivery.objects.get()
        self.assertEqual((rec.status, rec.covered), ("as_planned", "First law"))
        data = r.json()
        self.assertEqual((data["counts"]["held"], data["counts"]["as_planned"], data["counts"]["not_recorded"]), (1, 1, 1))
        self.assertEqual(data["units"][0]["done"], 1)
        self.assertEqual(self.plan.done_units, 1)
        self.record(status="not_held", remarks="Department seminar")          # recording again replaces it
        self.assertEqual(SessionDelivery.objects.get().status, "not_held")
        self.assertEqual(self.plan.done_units, 0)

    def test_rules(self):
        self.assertEqual(self.record(status="partly").status_code, 400)               # what was covered?
        self.assertEqual(self.record(status="not_held").status_code, 400)             # why not held?
        self.assertEqual(self.record(status="moved").status_code, 400)
        later = date.today() + timedelta(days=3)
        self.plan.units.create(topic="Entropy", hours=1, complete_by=later, period_no=1, unit_no=3, mode="lecture")
        r = self.record(date=later.isoformat())                                         # planned, but not yet
        self.assertEqual(r.status_code, 400)
        self.assertIn("on or after its day", r.json()["detail"])
        self.assertEqual(self.record(date=self.free_after_d2).status_code, 400)       # not a planned session
        self.assertFalse(SessionDelivery.objects.exists())

    def test_only_the_plans_teacher_records_and_the_hod_reads(self):
        self.assertEqual(self.record(user=self.hod).status_code, 403)
        self.assertEqual(self.record(user=self.other).status_code, 403)
        self.assertEqual(self.c(self.other).get(self.url).status_code, 403)
        self.assertEqual(self.c(self.student).get(self.url).status_code, 403)
        hod_view = self.c(self.hod).get(self.url)
        self.assertEqual(hod_view.status_code, 200)
        self.assertFalse(hod_view.json()["can_record"])

    def test_partly_covered_topic_is_carried_to_the_next_free_session(self):
        r = self.record(date=self.d2, status="partly", covered="Work only", carry_forward=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("now planned for", r.json()["message"])
        moved = self.plan.units.get(complete_by=self.free_after_d2)
        self.assertEqual((moved.topic, moved.unit_no, moved.period_no), ("Work and heat (continued)", 3, 1))
        self.assertEqual(SessionDelivery.objects.get().carried_to.isoformat(), self.free_after_d2)
        # recording the same session again does not carry it twice
        self.record(date=self.d2, status="partly", covered="Work only", carry_forward=True)
        self.assertEqual(self.plan.units.filter(topic__startswith="Work and heat (continued)").count(), 1)

    def test_carried_topic_keeps_its_outcomes(self):
        self.record(status="not_held", remarks="Holiday declared", carry_forward=True)
        moved = self.plan.units.get(notes__startswith="Carried from")
        self.assertEqual(list(moved.outcomes.values_list("code", flat=True)), ["CO1"])

    def test_attendance_from_the_register(self):
        from modules.attendance.models import Attendance
        Attendance.objects.create(teaching_assignment=self.ta, student=self.student, date=self.d1, hour=1,
                                  status="present")
        s = self.c(self.teacher).get(self.url).json()["sessions"][0]
        self.assertEqual(s["attendance"], {"present": 1, "total": 1})

    def test_approved_plan_is_behind_until_past_sessions_are_recorded(self):
        self.assertEqual(self.c(self.hod).post(f"/api/teaching-plans/{self.plan.id}/approve/").status_code, 200)
        status_of = lambda: self.c(self.hod).get("/api/teaching-plans/department/").json()[0]["status"]  # noqa: E731
        self.assertEqual(status_of(), "behind")
        self.record()
        self.record(date=self.d2, status="different", covered="Revision of unit 2")
        self.assertEqual(status_of(), "ontrack")


# ============================================================================
# COURSE PLAN (Part C): Excel template / import / export, and copying a plan
# ============================================================================
import io  # noqa: E402

from openpyxl import Workbook, load_workbook  # noqa: E402


class TimetableBase(CoursePlanBase):
    """Teacher ravi has period 1 on every weekday of a semester around today."""

    def setUp(self):
        super().setUp()
        from modules.timetable.models import Semester, TimeSlot, TimetableEntry
        today = date.today()
        Semester.objects.create(name="Odd", start_date=today - timedelta(days=20),
                                end_date=today + timedelta(days=20), is_active=True)
        slot = TimeSlot.objects.create(period_no=1, start_time=time(9), end_time=time(10))
        for wd in range(5):
            TimetableEntry.objects.create(assignment=self.ta, day_of_week=wd, time_slot=slot)
        self.days = [d["date"] for d in self.c(self.teacher).get(
            f"/api/teaching-plans/class_days/?subject={self.subject.id}").json()["days"] if not d.get("holiday")]
        self.co1 = CourseOutcome.objects.create(subject=self.subject, code="CO1", text="Apply the first law")
        self.co2 = CourseOutcome.objects.create(subject=self.subject, code="CO2", text="Explain entropy")

    @staticmethod
    def dmy(iso):
        y, m, d = iso.split("-")
        return f"{d}-{m}-{y}"


class ExcelTests(TimetableBase):
    HEAD = ["Date (DD-MM-YYYY)", "Day", "Period", "Unit", "Topic", "Notes", "Teaching mode", "Teaching method",
            "Class activity", "Beyond-class activity", "Outcomes"]

    def xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.append(self.HEAD)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "plan.xlsx"
        return buf

    def send(self, rows, commit=True, user=None):
        from core.dataio.tests import post_upload    # the waiting /import/ URL was removed
        return post_upload(self.c(user or self.teacher), "course_plan", {
            "file": self.xlsx(rows), "mode": "upsert", "subject": self.subject.id}, commit)

    def row(self, i, topic="First law", unit="Unit 2", mode="Lab / practical", outcomes="CO1, co2", **kw):
        r = [self.dmy(self.days[i]), "", 1, unit, topic, kw.get("notes", ""), mode, kw.get("method", "case_study"),
             kw.get("class_activity", "Quiz"), kw.get("beyond", ""), outcomes]
        return r

    def test_template_lists_every_session_with_what_is_planned(self):
        self.post("draft", [self.session(due=self.days[1], topic="Work and heat", mode="lab",
                                         outcomes=[self.co1.id])])
        r = self.c(self.teacher).get(f"/api/dataio/course_plan/template/?subject={self.subject.id}")
        self.assertEqual(r.status_code, 200)
        ws = load_workbook(io.BytesIO(r.content)).active
        rows = [r for r in ws.iter_rows(values_only=True) if any(r)]      # text-formatted blank rows follow
        self.assertEqual(len(rows) - 1, len(self.days))
        self.assertEqual(rows[2][0], self.dmy(self.days[1]))
        self.assertEqual((rows[2][4], rows[2][6], rows[2][10]), ("Work and heat", "Lab / practical", "CO1"))
        exp = self.c(self.teacher).get(f"/api/dataio/course_plan/export/?subject={self.subject.id}")
        self.assertEqual(exp.status_code, 200)

    def test_import_creates_the_plan(self):
        rows = [self.row(0), self.row(1, topic="Steady flow", unit="3", mode="lecture", outcomes=""),
                [self.dmy(self.days[2]), "", 1, "", "", "", "", "", "", "", ""]]       # not planned yet
        preview = self.send(rows, commit=False).json()
        self.assertEqual((preview["counts"]["new"], preview["counts"]["skip"], preview["counts"]["error"]), (2, 1, 0))
        self.assertFalse(TeachingPlan.objects.exists())                               # preview saves nothing
        r = self.send(rows)
        self.assertTrue(r.json()["saved"], r.content)
        plan = TeachingPlan.objects.get()
        self.assertEqual(plan.status, "draft")
        first = plan.units.get(complete_by=self.days[0])
        self.assertEqual((first.unit_no, first.mode, first.method, first.class_activity),
                         (2, "lab", "case_study", "quiz"))
        self.assertEqual(sorted(first.outcomes.values_list("code", flat=True)), ["CO1", "CO2"])
        self.assertEqual(plan.units.count(), 2)

    def test_problems_are_reported_and_nothing_is_saved(self):
        rows = [self.row(0),
                self.row(1, mode="Dance"),                                             # unknown mode
                self.row(2, outcomes="CO9"),                                           # not an outcome
                self.row(3, topic=""),                                                 # cells but no topic
                self.row(0, topic="Again"),                                            # same session twice
                ["01-01-2020", "", 1, "1", "Old", "", "Lecture", "", "", "", ""]]       # not in the timetable
        r = self.send(rows)
        self.assertEqual(r.status_code, 400)
        msgs = " | ".join(m for row in r.json()["rows"] for m in row["messages"])
        for text in ("not a valid teaching mode", "CO9 is not an outcome", "Write a topic",
                     "more than once", "no class in your timetable"):
            self.assertIn(text, msgs)
        self.assertFalse(TeachingPlan.objects.exists())

    def test_empty_cells_do_not_erase(self):
        self.send([self.row(0, notes="Closed systems")])
        self.send([[self.dmy(self.days[0]), "", 1, "", "First law (revised)", "", "", "", "", "", ""]])
        u = PlanUnit.objects.get()
        self.assertEqual((u.topic, u.notes, u.mode, u.unit_no), ("First law (revised)", "Closed systems", "lab", 2))
        self.assertEqual(u.outcomes.count(), 2)

    def test_locked_plan_and_other_teachers_are_refused(self):
        self.post("submitted", [self.session(due=self.days[0])])
        r = self.send([self.row(1)])
        self.assertEqual(r.status_code, 400)
        self.assertIn("with the HOD", r.json()["detail"])
        r = self.c(self.other).get(f"/api/dataio/course_plan/template/?subject={self.subject.id}")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.c(self.student).get(
            f"/api/dataio/course_plan/template/?subject={self.subject.id}").status_code, 403)


class CopyTests(TimetableBase):

    def setUp(self):
        super().setUp()
        # another section's approved plan of the same subject (dates from an older timetable)
        self.src = TeachingPlan.objects.create(teacher=self.other, subject=self.subject, class_section="Section B",
                                               semester="Semester 3", status="approved")
        for i, t in enumerate(["Basics", "Zeroth law", "First law"]):
            u = self.src.units.create(topic=t, hours=1, complete_by=date(2025, 7, 1 + i), period_no=2,
                                      sequence_no=i + 1, unit_no=1, mode="lecture", method="chalk_talk")
            u.outcomes.set([self.co1])
        self.draft_other = TeachingPlan.objects.create(teacher=self.other, subject=self.subject,
                                                       class_section="Section C", semester="Semester 3")
        self.draft_other.units.create(topic="Secret draft", hours=1)

    def copy(self, replace=True, source=None, user=None):
        return self.c(user or self.teacher).post("/api/teaching-plans/copy/", {
            "subject": self.subject.id, "source": source or self.src.id, "replace": replace}, format="json")

    def test_sources_are_mine_and_approved_ones(self):
        data = self.c(self.teacher).get(f"/api/teaching-plans/copy_sources/?subject={self.subject.id}").json()
        self.assertEqual([s["id"] for s in data["sources"]], [self.src.id])          # not the other's draft
        self.assertEqual(data["sources"][0]["sessions"], 3)
        self.assertEqual(self.c(self.student).get(
            f"/api/teaching-plans/copy_sources/?subject={self.subject.id}").status_code, 403)

    def test_copy_fills_this_timetable_in_order(self):
        r = self.copy()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("Copied 3 sessions", r.json()["message"])
        plan = TeachingPlan.objects.get(teacher=self.teacher)
        units = list(plan.units.order_by("complete_by"))
        self.assertEqual([(u.complete_by.isoformat(), u.topic) for u in units],
                         list(zip(self.days[:3], ["Basics", "Zeroth law", "First law"])))
        self.assertEqual((units[0].period_no, units[0].mode, units[0].unit_no), (1, "lecture", 1))
        self.assertEqual(list(units[0].outcomes.values_list("code", flat=True)), ["CO1"])
        self.assertEqual(plan.status, "draft")

    def test_keep_what_is_already_planned(self):
        self.post("draft", [self.session(due=self.days[1], topic="My own topic")])
        r = self.copy(replace=False)
        self.assertEqual((r.json()["copied"], r.json()["kept"]), (2, 1))
        plan = TeachingPlan.objects.get(teacher=self.teacher)
        self.assertEqual(plan.units.get(complete_by=self.days[1]).topic, "My own topic")
        self.copy(replace=True)
        self.assertEqual(plan.units.get(complete_by=self.days[1]).topic, "Zeroth law")

    def test_refused(self):
        self.assertEqual(self.copy(source=self.draft_other.id).status_code, 400)        # someone's draft
        self.assertEqual(self.copy(user=self.student).status_code, 403)
        self.post("submitted", [self.session(due=self.days[0])])
        r = self.copy()
        self.assertEqual(r.status_code, 400)
        self.assertIn("with the HOD", r.json()["detail"])


# ======================================================================
# CO-PO PART A - programme outcomes, CO-PO mapping, attainment rules
# ======================================================================
class OutcomeMappingTests(CoursePlanBase):
    def setUp(self):
        super().setUp()
        from modules.teachingplan.models import CourseOutcome
        self.admin = User.objects.create_user("admin", password="x", role="admin")
        self.course = self.subject.year.course
        self.co1 = CourseOutcome.objects.create(subject=self.subject, code="CO1", text="First law", order=1)
        self.co2 = CourseOutcome.objects.create(subject=self.subject, code="CO2", text="Entropy", order=2)

    def standard(self):
        return self.c(self.admin).post("/api/outcomes/programme/standard/")

    def test_standard_pos_and_psos(self):
        self.assertEqual(self.standard().json()["added"], 12)
        self.assertEqual(self.standard().json()["added"], 0)                    # safe to run again
        self.assertEqual(self.c(self.hod).post("/api/outcomes/programme/standard/").status_code, 403)
        # the HOD of a department teaching the course adds its PSOs; a plain teacher can't
        r = self.c(self.hod).post("/api/outcomes/programme/", {"kind": "pso", "course": self.course.id,
                                                                "text": "Design thermal systems"}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (201, "PSO1"))
        self.assertEqual(self.c(self.teacher).post("/api/outcomes/programme/", {
            "kind": "pso", "course": self.course.id, "text": "x"}, format="json").status_code, 403)
        self.assertEqual(self.c(self.hod).post("/api/outcomes/programme/", {
            "kind": "po", "text": "x"}, format="json").status_code, 403)
        d = self.c(self.teacher).get(f"/api/outcomes/programme/?course={self.course.id}").json()
        self.assertEqual((len(d["pos"]), [p["code"] for p in d["psos"]]), (12, ["PSO1"]))
        self.assertFalse(d["can_edit_psos"])
        self.assertEqual(self.c(self.student).get("/api/outcomes/programme/").status_code, 403)

    def test_mapping_save_and_rules(self):
        from modules.teachingplan.models import ProgramOutcome
        self.standard()
        po1 = ProgramOutcome.objects.get(code="PO1")
        po2 = ProgramOutcome.objects.get(code="PO2")
        url = f"/api/outcomes/mapping/{self.subject.id}/"
        cells = [{"co": self.co1.id, "po": po1.id, "strength": 3}, {"co": self.co2.id, "po": po1.id, "strength": 2},
                 {"co": self.co2.id, "po": po2.id, "strength": 0}]
        r = self.c(self.teacher).put(url, {"cells": cells}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d["cells"], {f"{self.co1.id}-{po1.id}": 3, f"{self.co2.id}-{po1.id}": 2})
        self.assertEqual((d["average"][str(po1.id)], d["average"][str(po2.id)]), (2.5, None))
        # another teacher can't; a strength of 4 or a CO of another subject is refused
        self.assertEqual(self.c(self.other).put(url, {"cells": []}, format="json").status_code, 403)
        bad = self.c(self.teacher).put(url, {"cells": [{"co": self.co1.id, "po": po1.id, "strength": 4}]},
                                       format="json")
        self.assertEqual(bad.status_code, 400)
        other_sub = Subject.objects.create(name="Fluids", code="ME302", year=self.subject.year, semester=3)
        from modules.teachingplan.models import CourseOutcome
        alien = CourseOutcome.objects.create(subject=other_sub, code="CO1", text="x")
        self.assertEqual(self.c(self.teacher).put(url, {"cells": [{"co": alien.id, "po": po1.id, "strength": 1}]},
                                                  format="json").status_code, 400)
        # a PSO of a different course can't be used
        other_course = Course.objects.create(name="B.E ECE")
        pso = ProgramOutcome.objects.create(kind="pso", course=other_course, code="PSO1", text="x")
        self.assertEqual(self.c(self.teacher).put(url, {"cells": [{"co": self.co1.id, "po": pso.id, "strength": 1}]},
                                                  format="json").status_code, 400)
        # a mapped PO can't be deleted
        self.assertEqual(self.c(self.admin).delete(f"/api/outcomes/programme/{po1.id}/").status_code, 400)
        subjects = self.c(self.hod).get(f"/api/outcomes/subjects/?course={self.course.id}").json()
        me = next(s for s in subjects if s["code"] == "ME301")
        self.assertEqual((me["cos"], me["mapped"]), (2, 2))

    def test_rules_college_and_department(self):
        r = self.c(self.teacher).get("/api/outcomes/rules/").json()
        self.assertEqual((r["student_target_pct"], r["level3_pct"], r["co_target"], r["can_edit"]), (60, 70, 2.0, False))
        self.assertEqual(self.c(self.hod).put("/api/outcomes/rules/", {"level3_pct": 75}, format="json").status_code, 403)
        url = f"/api/outcomes/rules/?department={self.dept.id}"
        self.assertTrue(self.c(self.hod).get(url).json()["inherited"])
        bad = self.c(self.hod).put(url, {"level3_pct": 55}, format="json")       # below level 2
        self.assertEqual(bad.status_code, 400)
        r = self.c(self.hod).put(url, {"level3_pct": 80, "internal_share": 40, "co_target": 2.2}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["level3_pct"], r.json()["inherited"]), (80, False))
        self.assertEqual(self.c(self.admin).get("/api/outcomes/rules/").json()["level3_pct"], 70)  # college untouched
        r = self.c(self.hod).delete(url).json()
        self.assertEqual((r["inherited"], r["level3_pct"]), (True, 70))
        self.assertEqual(self.c(self.admin).put("/api/outcomes/rules/", {"use_ia": False, "use_online_tests": False},
                                                format="json").status_code, 400)
