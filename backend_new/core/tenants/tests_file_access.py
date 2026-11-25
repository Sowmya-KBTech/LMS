"""
PHASE 5, PART 2 TESTS - inside one college, a file opens only for the people
who should see THAT file.

Cast (all in the test college):
  stu_a     the owner of most files below          parent_a  stu_a's parent
  stu_b     a classmate who must be refused         parent_b  stu_b's parent
  teacher   teaches the subject (stu_a enrolled)    tutor     stu_a's class tutor
  hod       HOD of the department                   stranger  a teacher with no link
  admin     the college admin

Run:  python manage.py test core.tenants.tests_file_access -v 2
"""
import datetime
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.db import connection
from django.test import Client, TestCase, override_settings

from core.academics.models import Course, Enrollment, Subject, TeachingAssignment, Year, YearTutor
from core.users.models import (Department, FacultyParticipation, FacultyProfile, ParentProfile,
                               StudentProfile, User)
from modules.attendance.models import ODRequest, StaffLeaveRequest
from modules.classgroups.models import ClassGroup, ClassMessage
from modules.learning.models import Assignment, Lecture, StudyMaterial, Submission
from modules.messaging.models import ConversationMessage
from modules.placement.models import Application, Company, Drive, JobRole, Offer

TODAY = datetime.date(2026, 12, 1)
CODE = "test"


class FileAccessTests(TestCase):

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="kbtc-files-")
        self.media = override_settings(MEDIA_ROOT=self.media_root, MULTITENANT_RELATIVE_MEDIA_ROOT="%s")
        self.media.enable()

        mk = User.objects.create_user
        self.admin = mk("admin1", password="x", role="admin")
        self.hod = mk("hod1", password="x", role="teacher")
        self.dept = Department.objects.create(name="Mechanical", code="ME", hod=self.hod)
        self.other_dept = Department.objects.create(name="Civil", code="CE")
        self.hod.department = self.dept
        self.hod.save()
        self.course = Course.objects.create(name="B.E Mech")
        self.year = Year.objects.create(course=self.course, year_number=1)
        self.subject = Subject.objects.create(name="Thermo", code="ME101", year=self.year,
                                              semester=1, department=self.dept)

        self.teacher = mk("teach1", password="x", role="teacher", department=self.dept)
        self.tutor = mk("tutor1", password="x", role="teacher", department=self.dept)
        self.stranger = mk("teach9", password="x", role="teacher", department=self.other_dept)
        self.stu_a = mk("stu_a", password="x", role="student", department=self.dept,
                        course=self.course, year=1, semester=1)
        self.stu_b = mk("stu_b", password="x", role="student", department=self.dept,
                        course=self.course, year=1, semester=1)
        self.parent_a = mk("par_a", password="x", role="parent")
        self.parent_b = mk("par_b", password="x", role="parent")
        ParentProfile.objects.create(user=self.parent_a).children.add(self.stu_a)
        ParentProfile.objects.create(user=self.parent_b).children.add(self.stu_b)

        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=self.course,
                                                    year=self.year, subject=self.subject)
        Enrollment.objects.create(student=self.stu_a, teaching_assignment=self.ta)   # stu_b NOT enrolled
        YearTutor.objects.create(teacher=self.tutor, course=self.course, year=self.year)

        self.urls = {}

    def tearDown(self):
        connection.set_tenant(connection.tenant)
        self.media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    # ---------- helpers ----------
    def store(self, record, field, filename):
        getattr(record, field).save(filename, ContentFile(b"SECRET-" + filename.encode()), save=True)
        return getattr(record, field).url

    def opens(self, user, url):
        c = Client(HTTP_HOST="testserver")
        c.force_login(user)
        return c.get(url).status_code == 200

    def check(self, url, allowed, refused):
        for user in allowed:
            self.assertTrue(self.opens(user, url), f"{user.username} should open {url}")
        for user in refused:
            self.assertFalse(self.opens(user, url), f"{user.username} must NOT open {url}")

    # ---------- one test per kind of file ----------
    def test_student_photo(self):
        url = self.store(StudentProfile.objects.create(user=self.stu_a), "photo", "a.jpg")
        self.check(url, allowed=[self.stu_a, self.parent_a, self.teacher, self.stranger, self.admin],
                   refused=[self.stu_b, self.parent_b])

    def test_staff_photo_is_for_everyone_here(self):
        url = self.store(FacultyProfile.objects.create(user=self.teacher), "photo", "t.jpg")
        self.check(url, allowed=[self.stu_b, self.parent_b, self.stranger], refused=[])

    def test_faculty_participation_proof(self):
        rec = FacultyParticipation.objects.create(faculty=self.teacher, category="fdp",
                                                  title="FDP", date=TODAY)
        url = self.store(rec, "proof", "fdp.pdf")
        iqac = User.objects.create_user("iqac1", password="x", role="admin", sub_role="iqac_admin")
        self.check(url, allowed=[self.teacher, self.hod, self.admin, iqac],
                   refused=[self.stranger, self.tutor, self.stu_a, self.parent_a])

    def test_subject_files_lecture_assignment_material(self):
        for model, field, extra in (
                (Lecture, "video", {"title": "L1", "created_by": self.teacher}),
                (Assignment, "file", {"title": "A1", "created_by": self.teacher}),
                (StudyMaterial, "file", {"title": "M1", "uploaded_by": self.teacher})):
            kw = dict(extra, teaching_assignment=self.ta)
            if model is StudyMaterial:
                kw["file"] = "placeholder"
            rec = model.objects.create(**kw)
            url = self.store(rec, field, f"{model.__name__.lower()}.pdf")
            self.check(url, allowed=[self.stu_a, self.teacher, self.hod, self.admin],
                       refused=[self.stu_b, self.parent_b, self.stranger])

    def test_submission(self):
        assignment = Assignment.objects.create(title="A1", teaching_assignment=self.ta, created_by=self.teacher)
        rec = Submission.objects.create(assignment=assignment, student=self.stu_a, file="placeholder")
        url = self.store(rec, "file", "answer.pdf")
        self.check(url, allowed=[self.stu_a, self.parent_a, self.teacher, self.hod, self.admin],
                   refused=[self.stu_b, self.parent_b, self.stranger, self.tutor])

    def test_od_proof(self):
        rec = ODRequest.objects.create(student=self.stu_a, from_date=TODAY, to_date=TODAY,
                                       category="sports", reason="match")
        url = self.store(rec, "proof", "medical.pdf")
        self.check(url, allowed=[self.stu_a, self.parent_a, self.tutor, self.hod, self.admin],
                   refused=[self.stu_b, self.parent_b, self.stranger, self.teacher])

    def test_staff_leave_proof(self):
        rec = StaffLeaveRequest.objects.create(teacher=self.teacher, department=self.dept,
                                               leave_type="medical", from_date=TODAY, to_date=TODAY,
                                               reason="fever")
        url = self.store(rec, "proof", "leave.pdf")
        self.check(url, allowed=[self.teacher, self.hod, self.admin],
                   refused=[self.stranger, self.tutor, self.stu_a, self.parent_a])

    def test_offer_letter(self):
        drive = Drive.objects.create(company=Company.objects.create(name="Acme"))
        app = Application.objects.create(student=self.stu_a,
                                         job_role=JobRole.objects.create(drive=drive, title="GET"))
        url = self.store(Offer.objects.create(application=app), "offer_letter", "offer.pdf")
        officer = User.objects.create_user("place1", password="x", role="admin", sub_role="placement_officer")
        self.check(url, allowed=[self.stu_a, self.parent_a, officer, self.admin],
                   refused=[self.stu_b, self.parent_b, self.teacher, self.hod])

    def test_private_message_only_the_two_people(self):
        rec = ConversationMessage.objects.create(sender=self.parent_a, receiver=self.teacher, text="hi")
        url = self.store(rec, "attachment", "note.pdf")
        self.check(url, allowed=[self.parent_a, self.teacher],
                   refused=[self.admin, self.hod, self.stu_a, self.stu_b, self.stranger])

    def test_class_group_file(self):
        group = ClassGroup.objects.create(kind=ClassGroup.CLASS, course=self.course, year=self.year,
                                          academic_year="2026-2027")
        url = self.store(ClassMessage.objects.create(group=group, sender=self.tutor), "attachment", "notes.pdf")
        outsider = User.objects.create_user("stu_x", password="x", role="student",
                                            course=Course.objects.create(name="B.E Civil"), year=1)
        self.check(url, allowed=[self.stu_a, self.stu_b, self.tutor, self.admin],
                   refused=[outsider, self.stranger, self.parent_a])

    # ---------- default deny ----------
    def test_unknown_folder_is_admin_only(self):
        from django.core.files.storage import default_storage
        name = default_storage.save("misc/unlisted.pdf", ContentFile(b"x"))
        url = f"/media/{CODE}/{name}"
        self.check(url, allowed=[self.admin], refused=[self.stu_a, self.teacher, self.hod])

    def test_file_no_record_points_to_is_closed(self):
        from django.core.files.storage import default_storage
        name = default_storage.save("od_proofs/orphan.pdf", ContentFile(b"x"))
        url = f"/media/{CODE}/{name}"
        self.check(url, allowed=[], refused=[self.stu_a, self.teacher, self.hod])

    def test_refusal_message(self):
        rec = ODRequest.objects.create(student=self.stu_a, from_date=TODAY, to_date=TODAY,
                                       category="sports", reason="match")
        url = self.store(rec, "proof", "medical.pdf")
        c = Client(HTTP_HOST="testserver")
        c.force_login(self.stu_b)
        r = c.get(url)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], "You don't have access to this file.")
