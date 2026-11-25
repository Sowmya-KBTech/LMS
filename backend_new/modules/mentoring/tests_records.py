"""
WAVE 1 TESTS - mentoring records by category.

Run:  python manage.py test modules.mentoring.tests_records -v 2
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from django.test import TestCase

from core.notifications.models import Notification
from core.users.models import Department, ParentProfile, User
from modules.mentoring.models import MentorAllocation, MentoringRecord
from modules.mentoring.utils import current_academic_year

AY = current_academic_year()
TODAY = timezone.localdate()


class MentoringRecordTests(TestCase):

    def setUp(self):
        mk = User.objects.create_user
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.other_hod = mk("hod2", password="x", role="teacher")
        Department.objects.create(name="Civil", code="CE", hod=self.other_hod)
        self.mentor = mk("mentor1", password="x", role="teacher", department=self.dept)
        self.mentor_b = mk("mentor2", password="x", role="teacher", department=self.dept)
        self.stranger = mk("teach9", password="x", role="teacher", department=self.dept)
        self.student = mk("stu1", password="x", role="student", department=self.dept, year=2)
        self.other_student = mk("stu2", password="x", role="student", department=self.dept, year=2)
        self.admin = mk("admin1", password="x", role="admin")
        self.parent = mk("par1", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent).children.add(self.student)
        self.alloc = self.allocate(self.student, self.mentor)
        self.allocate(self.other_student, self.mentor)

    def allocate(self, student, mentor):
        return MentorAllocation.objects.create(student=student, mentor=mentor, department=self.dept,
                                               academic_year=AY, status="active", is_active=True)

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def add(self, user, **over):
        body = dict(student=self.student.id, category="academic", date=str(TODAY),
                    summary="Discussed weak subjects", private_note="Family stress at home")
        body.update(over)
        return self.client_for(user).post("/api/mentoring/records/", body, format="json")

    def read(self, user, student=None):
        return self.client_for(user).get(f"/api/mentoring/records/?student={(student or self.student).id}")

    # ---------------- adding ----------------
    def test_mentor_adds_a_record_and_student_is_told_about_follow_up(self):
        r = self.add(self.mentor, category="competitive", action_points="Solve 20 GATE questions",
                     follow_up_date=str(TODAY + timedelta(days=7)))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["category_label"], "Competitive exams")
        self.assertEqual(r.json()["private_note"], "Family stress at home")
        self.assertTrue(Notification.objects.filter(recipient=self.student,
                                                    title="Mentoring session recorded").exists())

    def test_only_the_current_mentor_or_hod_can_add(self):
        self.assertEqual(self.add(self.stranger).status_code, 403)
        self.assertEqual(self.add(self.mentor_b).status_code, 403)
        self.assertEqual(self.add(self.admin).status_code, 403)
        self.assertEqual(self.add(self.other_hod).status_code, 403)
        self.assertEqual(self.add(self.student).status_code, 403)
        self.assertEqual(self.add(self.hod).status_code, 201)
        self.assertEqual(MentoringRecord.objects.count(), 1)

    def test_bad_input_is_refused_with_a_reason(self):
        for over, reason in (({"category": "gossip"}, "Choose a category"),
                             ({"summary": "  "}, "summary"),
                             ({"date": str(TODAY + timedelta(days=1))}, "future"),
                             ({"follow_up_date": str(TODAY - timedelta(days=1))}, "on or after"),
                             ({"date": "18/11/2026"}, "2026-11-18")):
            r = self.add(self.mentor, **over)
            self.assertEqual(r.status_code, 400, over)
            self.assertIn(reason, r.json()["detail"], over)

    # ---------------- reading + private notes ----------------
    def test_who_can_read_a_students_records(self):
        self.add(self.mentor)
        self.assertEqual(self.read(self.mentor).status_code, 200)
        self.assertEqual(self.read(self.hod).status_code, 200)
        for outsider in (self.stranger, self.mentor_b, self.admin, self.other_hod, self.parent, self.student):
            self.assertEqual(self.read(outsider).status_code, 403, outsider.username)

    def test_private_note_only_for_its_author_and_the_hod(self):
        self.add(self.mentor)
        self.assertEqual(self.read(self.mentor).json()["records"][0]["private_note"], "Family stress at home")
        self.assertEqual(self.read(self.hod).json()["records"][0]["private_note"], "Family stress at home")

        # the student gets a new mentor: the new mentor sees the history, not the private note
        self.alloc.is_active = False
        self.alloc.save()
        MentorAllocation.objects.filter(student=self.student).delete()
        self.allocate(self.student, self.mentor_b)
        rows = self.read(self.mentor_b).json()["records"]
        self.assertEqual(rows[0]["summary"], "Discussed weak subjects")
        self.assertNotIn("private_note", rows[0])
        # the old mentor still reads what they wrote
        self.assertEqual(self.read(self.mentor).status_code, 200)

    def test_student_sees_own_history_without_private_notes(self):
        self.add(self.mentor, category="personal")
        r = self.client_for(self.student).get("/api/mentoring/student/records/")
        self.assertEqual(r.status_code, 200)
        row = r.json()["records"][0]
        self.assertEqual(row["category_label"], "Personal & psychological")
        self.assertNotIn("private_note", row)
        self.assertNotIn("Family stress", str(r.content))
        other = self.client_for(self.other_student).get("/api/mentoring/student/records/")
        self.assertEqual(other.json()["records"], [])
        self.assertEqual(self.client_for(self.parent).get("/api/mentoring/student/records/").status_code, 403)

    def test_filter_and_category_counts(self):
        self.add(self.mentor, category="academic")
        self.add(self.mentor, category="academic")
        self.add(self.mentor, category="career")
        data = self.client_for(self.mentor).get(
            f"/api/mentoring/records/?student={self.student.id}&category=career").json()
        self.assertEqual(len(data["records"]), 1)
        counts = {c["key"]: c["count"] for c in data["categories"]}
        self.assertEqual(counts["academic"], 2)
        self.assertEqual(counts["career"], 1)
        self.assertTrue(data["can_add"])

    # ---------------- editing ----------------
    def test_only_the_author_or_hod_edits_or_deletes(self):
        rec_id = self.add(self.mentor).json()["id"]
        MentorAllocation.objects.filter(student=self.student).delete()
        self.allocate(self.student, self.mentor_b)
        url = f"/api/mentoring/records/{rec_id}/"
        self.assertEqual(self.client_for(self.mentor_b).patch(url, {"summary": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client_for(self.stranger).delete(url).status_code, 404)
        r = self.client_for(self.mentor).patch(url, {"summary": "Updated", "category": "career"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["category"], "career")
        self.assertEqual(self.client_for(self.hod).delete(url).status_code, 204)
        self.assertFalse(MentoringRecord.objects.exists())

    # ---------------- HOD summary ----------------
    def test_hod_summary_counts_and_students_not_met(self):
        self.add(self.mentor, category="academic")
        self.add(self.mentor, category="personal")
        r = self.client_for(self.hod).get("/api/mentoring/hod/records/summary/")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["total"], 2)
        counts = {c["key"]: c["count"] for c in data["by_category"]}
        self.assertEqual((counts["academic"], counts["personal"], counts["career"]), (1, 1, 0))
        row = data["mentors"][0]
        self.assertEqual((row["mentees"], row["records"], row["not_met"]), (2, 2, 1))
        self.assertEqual([s["student_id"] for s in data["not_met"]], [self.other_student.id])
        self.assertNotIn("Family stress", str(r.content))          # no notes in the summary

    def test_summary_is_for_hods_only(self):
        self.assertEqual(self.client_for(self.mentor).get("/api/mentoring/hod/records/summary/").status_code, 403)
        r = self.client_for(self.other_hod).get("/api/mentoring/hod/records/summary/")
        self.assertEqual(r.json()["total"], 0)                        # their own department only
