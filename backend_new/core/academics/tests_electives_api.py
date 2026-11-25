"""
Electives - Step 2: the APIs (meeting point 9).

Run:  python manage.py test core.academics.tests_electives_api -v 2
"""
from rest_framework.test import APIClient

from core.academics.models import ElectiveGroup, ElectiveOption, ElectiveSetting, Enrollment, Subject, TeachingAssignment
from core.academics.tests_electives import ElectiveTestBase


class ApiBase(ElectiveTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client


# ======================================================================
class SettingApiTests(ApiBase):

    def test_everyone_reads_admin_changes(self):
        r = self.as_(self.aarthi).get("/api/electives/setting/")
        self.assertEqual(r.data["mode"], "students")
        self.assertFalse(r.data["can_edit"])
        self.assertEqual(self.as_(self.aarthi).put("/api/electives/setting/", {"mode": "staff"},
                                                   format="json").status_code, 403)
        self.assertEqual(self.as_(self.hod).put("/api/electives/setting/", {"mode": "staff"},
                                                format="json").status_code, 403)
        r = self.as_(self.admin).put("/api/electives/setting/", {"mode": "staff"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ElectiveSetting.current().students_choose)

    def test_bad_mode(self):
        r = self.as_(self.admin).put("/api/electives/setting/", {"mode": "lottery"}, format="json")
        self.assertEqual(r.status_code, 400)


# ======================================================================
class GroupApiTests(ApiBase):

    def payload(self, **extra):
        return {"course": self.course.id, "year": self.y3.id, "semester": 5,
                "name": "Open Elective I", "department": self.mech.id, **extra}

    def test_hod_creates_group_for_own_department(self):
        r = self.as_(self.hod).post("/api/electives/groups/", self.payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["department"], self.mech.id)

    def test_hod_cannot_create_for_other_department(self):
        r = self.as_(self.other_hod).post("/api/electives/groups/", self.payload(), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("own department", r.data["detail"])

    def test_student_and_teacher_cannot_create(self):
        for user in (self.aarthi, self.teacher):
            r = self.as_(user).post("/api/electives/groups/", self.payload(), format="json")
            self.assertEqual(r.status_code, 403, user.username)

    def test_wrong_semester_and_duplicate_name(self):
        r = self.as_(self.admin).post("/api/electives/groups/", self.payload(semester=2), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("semesters 5 and 6", r.data["detail"])
        r = self.as_(self.admin).post("/api/electives/groups/",
                                      self.payload(name="Professional Elective I"), format="json")
        self.assertEqual(r.status_code, 400)

    def test_hod_sees_only_own_groups(self):
        ElectiveGroup.objects.create(course=self.course, year=self.y3, semester=5, name="CS group",
                                     department=self.cse)
        names = [g["name"] for g in self.as_(self.hod).get("/api/electives/groups/").data]
        self.assertEqual(names, ["Professional Elective I"])
        self.assertEqual(len(self.as_(self.admin).get("/api/electives/groups/").data), 2)

    def test_add_option_with_seat_limit_and_list_available(self):
        sub = Subject.objects.create(name="Additive Manufacturing", code="ME5E3", year=self.y3, semester=5,
                                     is_elective=True)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=sub)
        avail = self.as_(self.hod).get(f"/api/electives/groups/{self.group.id}/available/").data
        self.assertEqual([a["teaching_assignment"] for a in avail], [ta.id])
        r = self.as_(self.hod).post(f"/api/electives/groups/{self.group.id}/options/",
                                    {"teaching_assignment": ta.id, "seat_limit": 40}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["seat_limit"], 40)
        # the same subject can't join a second group
        g2 = ElectiveGroup.objects.create(course=self.course, year=self.y3, semester=5, name="Second",
                                          department=self.mech)
        r = self.as_(self.hod).post(f"/api/electives/groups/{g2.id}/options/",
                                    {"teaching_assignment": ta.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_core_subject_cannot_be_an_option(self):
        core = Subject.objects.create(name="Heat Transfer", code="ME501", year=self.y3, semester=5)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course, year=self.y3, subject=core)
        r = self.as_(self.hod).post(f"/api/electives/groups/{self.group.id}/options/",
                                    {"teaching_assignment": ta.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not marked as an elective", r.data["detail"])

    def test_seat_limit_cannot_go_below_students_holding_it(self):
        Enrollment.objects.create(student=self.aarthi, teaching_assignment=self.robotics.teaching_assignment)
        Enrollment.objects.create(student=self.bala, teaching_assignment=self.robotics.teaching_assignment)
        r = self.as_(self.hod).patch(f"/api/electives/options/{self.robotics.id}/", {"seat_limit": 1},
                                     format="json")
        self.assertEqual(r.status_code, 400)
        r = self.as_(self.hod).patch(f"/api/electives/options/{self.robotics.id}/", {"seat_limit": 60},
                                     format="json")
        self.assertEqual(r.data["seat_limit"], 60)
        self.assertEqual(r.data["seats_taken"], 2)

    def test_cannot_delete_option_or_group_with_students(self):
        Enrollment.objects.create(student=self.aarthi, teaching_assignment=self.robotics.teaching_assignment)
        self.assertEqual(self.as_(self.hod).delete(f"/api/electives/options/{self.robotics.id}/").status_code, 400)
        self.assertEqual(self.as_(self.hod).delete(f"/api/electives/groups/{self.group.id}/").status_code, 400)
        self.assertEqual(self.as_(self.hod).delete(f"/api/electives/options/{self.composites.id}/").status_code, 204)


# ======================================================================
class AllocationApiTests(ApiBase):

    def setUp(self):
        super().setUp()
        self.staff_mode()

    def test_hod_allocates_moves_with_reason_and_history(self):
        c = self.as_(self.hod)
        r = c.post("/api/electives/allocate/", {"student": self.aarthi.id, "option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = c.post("/api/electives/allocate/", {"student": self.aarthi.id, "option": self.composites.id},
                   format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("reason", r.data["detail"])
        r = c.post("/api/electives/allocate/", {"student": self.aarthi.id, "option": self.composites.id,
                                                "reason": "Student requested the change"}, format="json")
        self.assertEqual(r.status_code, 200)
        log = c.get(f"/api/electives/groups/{self.group.id}/changes/").data
        self.assertEqual(log[0]["from"], "Robotics")
        self.assertEqual(log[0]["to"], "Composite Materials")
        self.assertEqual(log[0]["reason"], "Student requested the change")

    def test_students_list_shows_who_has_not_chosen(self):
        self.as_(self.hod).post("/api/electives/allocate/", {"student": self.aarthi.id,
                                                             "option": self.robotics.id}, format="json")
        r = self.as_(self.hod).get(f"/api/electives/groups/{self.group.id}/students/")
        self.assertEqual(r.data["not_chosen"], 1)
        aarthi = next(s for s in r.data["students"] if s["student"] == self.aarthi.id)
        self.assertEqual(aarthi["options"][0]["subject"], "Robotics")

    def test_whole_class_button(self):
        r = self.as_(self.hod).post(f"/api/electives/options/{self.robotics.id}/assign-class/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["assigned"], 2)
        self.assertIn("2 student(s) given Robotics", r.data["detail"])

    def test_whole_class_respects_seat_limit(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        r = self.as_(self.hod).post(f"/api/electives/options/{self.robotics.id}/assign-class/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("seat(s) left", r.data["detail"])

    def test_other_hod_and_students_blocked(self):
        for user, code in ((self.other_hod, 403), (self.aarthi, 403)):
            self.assertEqual(self.as_(user).get(f"/api/electives/groups/{self.group.id}/students/").status_code,
                             code, user.username)
            self.assertEqual(self.as_(user).post(f"/api/electives/options/{self.robotics.id}/assign-class/")
                             .status_code, code, user.username)
        r = self.as_(self.aarthi).post("/api/electives/allocate/", {"student": self.bala.id,
                                                                    "option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 400)


# ======================================================================
class StudentApiTests(ApiBase):

    def test_my_electives_and_choose(self):
        c = self.as_(self.aarthi)
        r = c.get("/api/electives/my/")
        self.assertTrue(r.data["students_choose"])
        self.assertTrue(r.data["groups"][0]["can_choose"])
        self.assertEqual(len(r.data["groups"][0]["options"]), 2)
        r = c.post("/api/electives/my/choose/", {"option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        chosen = [o["subject"] for o in c.get("/api/electives/my/").data["groups"][0]["options"] if o["chosen"]]
        self.assertEqual(chosen, ["Robotics"])
        c.post("/api/electives/my/drop/", {"option": self.robotics.id}, format="json")
        self.assertFalse(Enrollment.objects.filter(student=self.aarthi).exists())

    def test_full_elective_refused(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        self.as_(self.bala).post("/api/electives/my/choose/", {"option": self.robotics.id}, format="json")
        r = self.as_(self.aarthi).post("/api/electives/my/choose/", {"option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("full", r.data["detail"])

    def test_staff_mode_hides_choosing(self):
        self.staff_mode()
        r = self.as_(self.aarthi).get("/api/electives/my/")
        self.assertFalse(r.data["groups"][0]["can_choose"])
        r = self.as_(self.aarthi).post("/api/electives/my/choose/", {"option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("HOD allocates", r.data["detail"])

    def test_old_endpoint_follows_the_same_rules(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        self.as_(self.bala).post("/api/elective-enroll/", {"teaching_assignment": self.robotics.teaching_assignment_id},
                                 format="json")
        r = self.as_(self.aarthi).post("/api/elective-enroll/",
                                       {"teaching_assignment": self.robotics.teaching_assignment_id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("full", r.data["detail"])
        self.staff_mode()
        r = self.as_(self.aarthi).post("/api/elective-enroll/",
                                       {"teaching_assignment": self.composites.teaching_assignment_id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_teacher_cannot_use_student_endpoints(self):
        self.assertEqual(self.as_(self.teacher).get("/api/electives/my/").status_code, 403)


# ======================================================================
# CBCS PART A - course registration
# ======================================================================
import datetime as _dt
from decimal import Decimal as _D
from unittest import mock as _mock

from django.utils import timezone as _tz

from core.academics.models import YearTutor
from core.academics.models_electives import (
    CourseRegistration, ElectiveChange as _Change, RegistrationChoice, RegistrationWindow,
)


class CourseRegistrationBase(ApiBase):
    def setUp(self):
        super().setUp()
        for o in (self.robotics, self.composites):
            o.teaching_assignment.subject.credits = 3
            o.teaching_assignment.subject.save()
        Subject.objects.create(name="Heat Transfer", code="ME501", year=self.y3, semester=5, credits=16)
        self.tutor = self.teacher
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.y3)
        now = _tz.now()
        self.win = RegistrationWindow.objects.create(
            name="Odd 2026", semester=5, opens_at=now - _dt.timedelta(days=1),
            closes_at=now + _dt.timedelta(days=2), min_credits=18, max_credits=20)
        self.cgpa = {}
        p1 = _mock.patch("modules.mentoring.utils.cgpa_map",
                         side_effect=lambda st: {getattr(s, "id", s): self.cgpa.get(getattr(s, "id", s))
                                                 for s in st})
        p2 = _mock.patch("modules.mentoring.utils.student_cgpa", side_effect=lambda s: self.cgpa.get(s.id))
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    # ---------- helpers ----------
    def rank(self, student, *options):
        rows = [{"group": o.group_id, "option": o.id, "rank": i + 1} for i, o in enumerate(options)]
        return self.as_(student).put("/api/course-registration/me/", {"choices": rows}, format="json")

    def submit(self, student, *options):
        if options:
            self.rank(student, *options)
        return self.as_(student).post("/api/course-registration/me/submit/", {}, format="json")

    def reg(self, student):
        return CourseRegistration.objects.get(window=self.win, student=student)

    def close(self):
        self.win.closes_at = _tz.now() - _dt.timedelta(minutes=1)
        self.win.save()


class CourseRegistrationTests(CourseRegistrationBase):
    # ---------- student ----------
    def test_student_ranks_credits_and_submit(self):
        r = self.as_(self.aarthi).get("/api/course-registration/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["code"] for c in r.data["core"]], ["ME501"])
        self.assertEqual(r.data["credits"], 16)
        self.assertIn("group_missing", [i["code"] for i in r.data["issues"]])
        # submit with nothing chosen is refused
        self.assertEqual(self.as_(self.aarthi).post("/api/course-registration/me/submit/").status_code, 400)
        r = self.rank(self.aarthi, self.composites, self.robotics)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["credits"], 19)                 # 16 core + only the 1st pick counts
        ranks = {o["code"]: o["rank"] for o in r.data["groups"][0]["options"]}
        self.assertEqual(ranks, {"ME5E1": 2, "ME5E2": 1})
        r = self.submit(self.aarthi)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.reg(self.aarthi).status, "submitted")
        from core.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(recipient=self.tutor,
                                                    title="Course registration to approve").exists())

    def test_credit_limits_block_submit(self):
        self.win.min_credits = 25
        self.win.save()
        r = self.submit(self.aarthi, self.robotics)
        self.assertIn("Below 25 credits", r.data["detail"])
        self.win.min_credits, self.win.max_credits = 18, 18
        self.win.save()
        r = self.submit(self.aarthi, self.robotics)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Above 18 credits", r.data["detail"])
        # a high CGPA gets extra credits
        self.win.extra_cgpa, self.win.extra_credits = _D("8.5"), _D("3")
        self.win.save()
        self.cgpa[self.aarthi.id] = 9.1
        self.assertEqual(self.submit(self.aarthi).status_code, 200)

    def test_bad_choices_refused(self):
        other = ElectiveGroup.objects.create(course=self.course, year=self.y3, semester=6, name="Sem 6")
        x = self.option("Other sem", "ME6E1", group=other)
        self.assertEqual(self.rank(self.aarthi, x).status_code, 400)
        rows = [{"group": self.group.id, "option": self.robotics.id, "rank": 1}] * 2
        self.assertEqual(self.as_(self.aarthi).put("/api/course-registration/me/", {"choices": rows},
                                                   format="json").status_code, 400)
        self.win.max_ranks = 1
        self.win.save()
        self.assertEqual(self.rank(self.aarthi, self.robotics, self.composites).status_code, 400)

    def test_window_must_be_open(self):
        self.close()
        self.assertEqual(self.rank(self.aarthi, self.robotics).status_code, 400)

    def test_old_elective_screen_blocked_inside_a_window(self):
        r = self.as_(self.aarthi).post("/api/electives/my/choose/", {"option": self.robotics.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Course registration", r.data["detail"])

    # ---------- approvals ----------
    def test_class_incharge_approves(self):
        self.submit(self.aarthi, self.robotics)
        rows = self.as_(self.tutor).get("/api/course-registration/review/").data["rows"]
        self.assertEqual([x["name"] for x in rows], ["aarthi"])
        self.assertTrue(rows[0]["ok"])
        # a teacher who is not this class's in-charge can't
        self.assertEqual(self.as_(self.other_hod).post(
            f"/api/course-registration/{self.reg(self.aarthi).id}/approve/").status_code, 400)
        r = self.as_(self.tutor).post(f"/api/course-registration/{self.reg(self.aarthi).id}/approve/")
        self.assertEqual(r.data["status"], "approved")

    def test_hod_step_when_turned_on(self):
        self.win.hod_approval = True
        self.win.save()
        self.submit(self.aarthi, self.robotics)
        rid = self.reg(self.aarthi).id
        self.assertEqual(self.as_(self.tutor).post(f"/api/course-registration/{rid}/approve/").data["status"],
                         "with_hod")
        self.assertEqual(self.as_(self.tutor).post(f"/api/course-registration/{rid}/approve/").status_code, 400)
        waiting = self.as_(self.hod).get("/api/course-registration/review/").data
        self.assertEqual(waiting["counts"]["waiting"], 1)
        self.assertEqual(self.as_(self.hod).post(f"/api/course-registration/{rid}/approve/").data["status"],
                         "approved")

    def test_return_needs_comment_and_student_resubmits(self):
        self.submit(self.aarthi, self.robotics)
        rid = self.reg(self.aarthi).id
        self.assertEqual(self.as_(self.tutor).post(f"/api/course-registration/{rid}/return/",
                                                   {"comment": "no"}).status_code, 400)
        r = self.as_(self.tutor).post(f"/api/course-registration/{rid}/return/",
                                      {"comment": "Put Composites first"})
        self.assertEqual(r.data["status"], "returned")
        r = self.rank(self.aarthi, self.composites, self.robotics)
        self.assertEqual(r.data["status"], "draft")
        self.assertEqual(r.data["comment"], "Put Composites first")     # still visible while editing
        r = self.submit(self.aarthi)
        self.assertEqual(r.data["status"], "submitted")
        self.assertEqual(r.data["comment"], "")

    def test_bulk_approve_skips_problems(self):
        self.submit(self.aarthi, self.robotics)
        self.submit(self.bala, self.composites)
        CourseRegistration.objects.filter(student=self.bala).update(credits=0)
        RegistrationChoice.objects.filter(registration__student=self.bala).delete()   # now incomplete
        ids = list(CourseRegistration.objects.values_list("id", flat=True))
        r = self.as_(self.tutor).post("/api/course-registration/review/approve-ok/", {"ids": ids}, format="json")
        self.assertEqual((r.data["approved"], r.data["skipped"]), (1, 1))

    # ---------- allocation ----------
    def two_want_robotics(self):
        self.robotics.seat_limit = 1
        self.robotics.save()
        self.cgpa = {self.aarthi.id: 7.0, self.bala.id: 9.0}
        self.submit(self.aarthi, self.robotics, self.composites)
        self.submit(self.bala, self.robotics, self.composites)
        for s in (self.aarthi, self.bala):
            self.as_(self.tutor).post(f"/api/course-registration/{self.reg(s).id}/approve/")

    def test_allocation_by_cgpa_with_waitlist(self):
        self.two_want_robotics()
        url = f"/api/course-registration/windows/{self.win.id}/allocation/"
        trial = self.as_(self.admin).get(url).data
        rob = next(o for o in trial["options"] if o["option"] == self.robotics.id)
        self.assertEqual((rob["filled"], rob["first_choice"], rob["waitlist"]), (1, 2, 1))
        self.assertFalse(self.has(self.bala, self.robotics))                 # trial saves nothing
        self.assertEqual(self.as_(self.admin).post(url, {}, format="json").status_code, 400)   # still open
        self.close()
        self.assertEqual(self.as_(self.tutor).post(url, {}, format="json").status_code, 403)
        r = self.as_(self.admin).post(url, {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(self.has(self.bala, self.robotics))                  # higher CGPA
        self.assertTrue(self.has(self.aarthi, self.composites))
        wait = RegistrationChoice.objects.get(registration__student=self.aarthi, option=self.robotics)
        self.assertEqual((wait.result, wait.waitlist_no), ("waitlist", 1))
        self.assertTrue(_Change.objects.filter(student=self.bala, to_option=self.robotics).exists())
        self.assertEqual(self.as_(self.admin).post(url, {}, format="json").status_code, 400)  # only once
        me = self.as_(self.aarthi).get("/api/course-registration/me/").data
        rob = next(o for o in me["groups"][0]["options"] if o["id"] == self.robotics.id)
        self.assertEqual((rob["result"], rob["waitlist_no"]), ("waitlist", 1))

    def test_first_come_first_served(self):
        self.win.allocation = "fcfs"
        self.win.save()
        self.two_want_robotics()           # aarthi submitted first, lower CGPA
        self.close()
        self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/allocation/", {},
                                  format="json")
        self.assertTrue(self.has(self.aarthi, self.robotics))

    def test_cancelled_option_moves_students_on(self):
        self.two_want_robotics()
        self.close()
        r = self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/allocation/",
                                      {"skip": [self.robotics.id]}, format="json")
        self.assertEqual(r.data["skip"], [self.robotics.id])
        self.assertFalse(self.has(self.bala, self.robotics))
        self.assertTrue(self.has(self.bala, self.composites) and self.has(self.aarthi, self.composites))

    def test_waiting_ones_auto_approved_returned_left_out(self):
        self.submit(self.aarthi, self.robotics)               # never approved, but fine
        self.submit(self.bala, self.robotics)
        self.as_(self.tutor).post(f"/api/course-registration/{self.reg(self.bala).id}/return/",
                                  {"comment": "Talk to me first"})
        chitra = self.student("chitra")                       # waiting, but now incomplete
        self.submit(chitra, self.composites)
        RegistrationChoice.objects.filter(registration__student=chitra).delete()
        self.close()
        r = self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/allocation/", {},
                                      format="json")
        self.assertEqual(r.data["auto_approved"], 1)
        self.assertEqual(self.reg(self.aarthi).status, "approved")
        self.assertTrue(self.has(self.aarthi, self.robotics))
        self.assertFalse(self.has(self.bala, self.robotics))
        self.assertEqual(self.reg(chitra).status, "submitted")

    def test_fill_from_waitlist(self):
        self.two_want_robotics()
        self.close()
        self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/allocation/", {},
                                  format="json")
        Enrollment.objects.filter(student=self.bala, teaching_assignment=self.robotics.teaching_assignment).delete()
        r = self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/fill-waitlist/")
        self.assertEqual(r.data["moved"], 1)
        self.assertTrue(self.has(self.aarthi, self.robotics))
        self.assertFalse(self.has(self.aarthi, self.composites))          # left the lower choice
        report = self.as_(self.admin).get(f"/api/course-registration/windows/{self.win.id}/allocation/").data
        self.assertTrue(report["saved"])
        self.assertEqual([u["name"] for u in report["unplaced"]], ["bala"])   # bala dropped out

    # ---------- window setup ----------
    def test_window_admin(self):
        now = _tz.now()
        body = {"name": "Even", "semester": 5, "opens_at": now.isoformat(),
                "closes_at": (now + _dt.timedelta(days=3)).isoformat(), "min_credits": 20, "max_credits": 26}
        self.assertEqual(self.as_(self.hod).post("/api/course-registration/windows/", body,
                                                 format="json").status_code, 403)
        r = self.as_(self.admin).post("/api/course-registration/windows/", body, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Odd 2026", r.data["courses"])                         # same students already covered
        body.update(semester=6, closes_at=(now - _dt.timedelta(days=1)).isoformat(), max_credits=10)
        r = self.as_(self.admin).post("/api/course-registration/windows/", body, format="json")
        self.assertEqual(set(r.data), {"closes_at", "max_credits"})
        body.update(closes_at=(now + _dt.timedelta(days=1)).isoformat(), max_credits=26)
        r = self.as_(self.admin).post("/api/course-registration/windows/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["progress"]["students"], 0)
        d = self.as_(self.admin).get(f"/api/course-registration/windows/{self.win.id}/").data
        self.assertEqual(d["progress"]["not_started"], 2)


# ======================================================================
# CBCS PART B - open electives, prerequisites, degree panel, student list
# ======================================================================
class OpenElectivePrerequisiteTests(CourseRegistrationBase):
    def setUp(self):
        super().setUp()
        from core.academics.models import Course, Year
        from core.users.models import User
        self.ece = Course.objects.create(name="B.E ECE")
        self.ece_y3 = Year.objects.create(course=self.ece, year_number=3)
        self.ece_student = User.objects.create_user(username="elan", password="x", role="student",
                                                    course=self.ece, year=3, semester=5)
        self.oe = ElectiveGroup.objects.create(course=self.course, year=self.y3, semester=5, name="Open Elective I",
                                               open_elective=True, department=self.mech)
        sub = Subject.objects.create(name="Internet of Things", code="EC5O1", year=self.ece_y3, semester=5,
                                     is_elective=True, credits=3)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.ece, year=self.ece_y3, subject=sub)
        self.iot = ElectiveOption.objects.create(group=self.oe, teaching_assignment=ta)
        self.sem3 = Subject.objects.create(name="Materials Science", code="ME303", year=self.y3, semester=3)

    def test_open_elective_offered_across_courses_not_own(self):
        me = self.as_(self.aarthi).get("/api/course-registration/me/").data
        self.assertEqual([g["name"] for g in me["groups"]], ["Professional Elective I", "Open Elective I"])
        self.assertEqual(me["groups"][1]["options"][0]["blocked"], "")
        self.assertEqual(me["groups"][1]["options"][0]["course_name"], "B.E ECE")
        rows = [{"group": self.group.id, "option": self.robotics.id, "rank": 1},
                {"group": self.oe.id, "option": self.iot.id, "rank": 1}]
        r = self.as_(self.aarthi).put("/api/course-registration/me/", {"choices": rows}, format="json")
        self.assertEqual(r.data["credits"], 22)                          # 16 + 3 + 3
        # the ECE student sees only the open elective, and its ECE option is blocked
        mine = self.as_(self.ece_student).get("/api/course-registration/me/").data
        self.assertEqual([g["name"] for g in mine["groups"]], ["Open Elective I"])
        self.assertIn("own course", mine["groups"][0]["options"][0]["blocked"])
        r = self.as_(self.ece_student).put("/api/course-registration/me/",
                                           {"choices": [{"group": self.oe.id, "option": self.iot.id, "rank": 1}]},
                                           format="json")
        self.assertEqual(r.status_code, 400)
        from core.academics.electives import ElectiveError, choose
        with self.assertRaises(ElectiveError):                          # not even staff
            choose(self.ece_student, self.iot, by=self.admin)

    def test_open_to_limits_the_courses(self):
        self.oe.open_to.set([self.ece])
        me = self.as_(self.aarthi).get("/api/course-registration/me/").data
        self.assertEqual([g["name"] for g in me["groups"]], ["Professional Elective I"])

    def test_open_group_api(self):
        body = {"course": self.course.id, "year": self.y3.id, "semester": 5, "name": "Open Elective II",
                "department": self.mech.id, "open_elective": True, "open_to": [self.course.id, self.ece.id]}
        r = self.as_(self.admin).post("/api/electives/groups/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(sorted(r.data["open_to_names"]), ["B.E ECE", "B.E Mechanical"])
        gid = r.data["id"]
        sub = Subject.objects.create(name="Signals", code="EC5O2", year=self.ece_y3, semester=5, is_elective=True)
        ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.ece, year=self.ece_y3, subject=sub)
        avail = self.as_(self.admin).get(f"/api/electives/groups/{gid}/available/").data
        self.assertIn(ta.id, [a["teaching_assignment"] for a in avail])     # other course's subject offered
        r = self.as_(self.admin).post(f"/api/electives/groups/{gid}/options/", {"teaching_assignment": ta.id},
                                      format="json")
        self.assertEqual(r.status_code, 201, r.data)
        oid = r.data["id"]
        r = self.as_(self.admin).patch(f"/api/electives/groups/{gid}/", {"open_elective": False}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.as_(self.admin).post(f"/api/electives/options/{oid}/assign-class/")
        self.assertEqual(r.status_code, 400)

    def test_prerequisite_blocks_until_passed(self):
        from modules.exams.models import ResultEntry, SemesterResult
        r = self.as_(self.admin).patch(f"/api/electives/options/{self.robotics.id}/", {"requires": [self.sem3.id]},
                                       format="json")
        self.assertEqual(r.data["requires"][0]["code"], "ME303")
        later = Subject.objects.create(name="Later", code="ME601", year=self.y3, semester=6)
        self.assertEqual(self.as_(self.admin).patch(f"/api/electives/options/{self.robotics.id}/",
                                                    {"requires": [later.id]}, format="json").status_code, 400)
        choices = self.as_(self.admin).get(f"/api/electives/options/{self.robotics.id}/prerequisites/").data
        self.assertEqual([c["code"] for c in choices], ["ME303"])
        me = self.as_(self.aarthi).get("/api/course-registration/me/").data
        rob = next(o for o in me["groups"][0]["options"] if o["id"] == self.robotics.id)
        self.assertIn("ME303 Materials Science", rob["blocked"])
        self.assertEqual(self.rank(self.aarthi, self.robotics).status_code, 400)
        sr = SemesterResult.objects.create(student=self.aarthi, semester=3, is_published=True)
        entry = ResultEntry.objects.create(result=sr, subject=self.sem3, max_marks=100, marks_obtained=20,
                                           is_pass=False)
        self.assertEqual(self.rank(self.aarthi, self.robotics).status_code, 400)       # an arrear
        entry.is_pass, entry.marks_obtained = True, 70
        entry.save()
        self.assertEqual(self.rank(self.aarthi, self.robotics).status_code, 200)       # passed now

    def test_allocation_skips_a_blocked_choice(self):
        self.win.max_credits = 26
        self.win.save()
        r = self.submit(self.aarthi, self.robotics, self.composites, self.iot)
        self.assertEqual(r.status_code, 200, r.data)
        self.robotics.requires.set([self.sem3])             # rule added after she ranked it
        self.close()
        self.as_(self.admin).post(f"/api/course-registration/windows/{self.win.id}/allocation/", {},
                                  format="json")
        self.assertFalse(self.has(self.aarthi, self.robotics))
        self.assertTrue(self.has(self.aarthi, self.composites))

    def test_degree_panel(self):
        self.assertIsNone(self.as_(self.aarthi).get("/api/course-registration/me/").data["degree"])
        fake = {"regulation": {"name": "R2022"}, "credits_required": 160, "credits_earned": 94,
                "categories": [{"code": "PEC", "name": "Professional elective", "required": 18, "earned": 9}]}
        with _mock.patch("modules.exams.grading.semester_summary", return_value=fake):
            d = self.as_(self.aarthi).get("/api/course-registration/me/").data["degree"]
        self.assertEqual((d["regulation"], d["required"], d["categories"][0]["earned"]), ("R2022", 160, 9))

    def test_student_list(self):
        self.rank(self.aarthi, self.robotics, self.composites)
        url = f"/api/course-registration/windows/{self.win.id}/students/"
        self.assertEqual(self.as_(self.aarthi).get(url).status_code, 403)
        rows = {r["name"]: r for r in self.as_(self.admin).get(url).data["rows"]}
        self.assertEqual(set(rows), {"aarthi", "bala", "elan"})
        self.assertEqual(rows["aarthi"]["groups"][0]["ranked"], ["Robotics", "Composite Materials"])
        self.assertEqual(rows["bala"]["status"], "Not started")
        self.assertEqual([g["group"] for g in rows["elan"]["groups"]], ["Open Elective I"])
        # the class in-charge sees only their class
        names = {r["name"] for r in self.as_(self.tutor).get(url).data["rows"]}
        self.assertEqual(names, {"aarthi", "bala"})
