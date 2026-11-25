"""
UPLOAD SIZE LIMIT TESTS.

Limits are made tiny here (1-3 MB) so the tests don't build 500 MB files;
the rules are the same at the real sizes.

Run:  python manage.py test core.security.tests_uploads -v 2
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from core.academics.models import Course, Subject, TeachingAssignment, Year
from core.security.uploads import kind_of
from core.users.models import Department, User
from modules.learning.models import Lecture

MB = 1024 * 1024
SMALL = dict(VIDEO_UPLOAD_MAX_MB=3, AUDIO_UPLOAD_MAX_MB=2, IMAGE_UPLOAD_MAX_MB=1, FILE_UPLOAD_MAX_MB=2)


def upload(name, size, ctype):
    return SimpleUploadedFile(name, b"x" * size, content_type=ctype)


class KindTests(TestCase):

    def test_kinds(self):
        cases = [("talk.mp4", "video/mp4", "video"), ("note.m4a", "audio/mp4", "audio"),
                 ("voice.webm", "audio/webm", "audio"), ("class.webm", "video/webm", "video"),
                 ("me.JPG", "image/jpeg", "image"), ("proof.pdf", "application/pdf", "file"),
                 ("marks.xlsx", "application/octet-stream", "file"), ("x.mov", "", "video")]
        for name, ctype, kind in cases:
            self.assertEqual(kind_of(upload(name, 1, ctype)), kind, name)


@override_settings(**SMALL)
class UploadLimitTests(TestCase):

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="kbtc-uploads-")
        self.media = override_settings(MEDIA_ROOT=self.media_root, MULTITENANT_RELATIVE_MEDIA_ROOT="%s")
        self.media.enable()
        dept = Department.objects.create(name="Mechanical", code="ME")
        self.teacher = User.objects.create_user("teach1", password="x", role="teacher", department=dept)
        course = Course.objects.create(name="B.E Mech")
        year = Year.objects.create(course=course, year_number=1)
        subject = Subject.objects.create(name="Thermo", code="ME101", year=year, semester=1, department=dept)
        self.ta = TeachingAssignment.objects.create(teacher=self.teacher, course=course, year=year,
                                                    subject=subject)

    def tearDown(self):
        self.media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def post_lecture(self, video):
        c = APIClient(HTTP_HOST="testserver")
        c.force_authenticate(user=self.teacher)
        return c.post("/api/lectures/", {"title": "L1", "teaching_assignment": self.ta.id, "video": video},
                      format="multipart")

    def test_video_under_the_limit_is_saved(self):
        r = self.post_lecture(upload("week1.mp4", 2 * MB, "video/mp4"))
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertTrue(Lecture.objects.get().video.name.endswith(".mp4"))

    def test_video_over_the_limit_is_refused_and_nothing_saved(self):
        r = self.post_lecture(upload("week1.mp4", 4 * MB, "video/mp4"))
        self.assertEqual(r.status_code, 413)
        self.assertIn("The limit for videos is 3 MB", r.json()["detail"])
        self.assertEqual(Lecture.objects.count(), 0)

    def test_each_kind_has_its_own_limit(self):
        c = Client(HTTP_HOST="testserver")
        for name, size, ctype, ok in (
                ("proof.pdf", int(1.5 * MB), "application/pdf", True),
                ("proof.pdf", 3 * MB, "application/pdf", False),
                ("photo.jpg", int(0.5 * MB), "image/jpeg", True),
                ("photo.jpg", int(1.5 * MB), "image/jpeg", False),       # 1.5 MB photo: too big
                ("voice.m4a", int(1.5 * MB), "audio/mp4", True),
                ("voice.m4a", 3 * MB, "audio/mp4", False)):
            r = c.post("/api/lectures/", {"f": upload(name, size, ctype)})
            self.assertEqual(r.status_code == 413, not ok, f"{name} {size}")

    def test_any_file_in_the_request_counts(self):
        r = Client(HTTP_HOST="testserver").post("/api/lectures/", {
            "a": upload("ok.pdf", MB, "application/pdf"),
            "b": upload("big.pdf", 3 * MB, "application/pdf")})
        self.assertEqual(r.status_code, 413)
        self.assertIn("big.pdf", r.json()["detail"])

    def test_huge_request_is_refused_before_it_is_read(self):
        r = Client(HTTP_HOST="testserver").post(
            "/api/lectures/", {"f": upload("tiny.pdf", 10, "application/pdf")},
            CONTENT_LENGTH=str(5 * 1024 * MB))                         # claims 5 GB
        self.assertEqual(r.status_code, 413)
        self.assertIn("largest file allowed is 3 MB", r.json()["detail"])

    def test_normal_json_requests_are_untouched(self):
        c = APIClient(HTTP_HOST="testserver")
        c.force_authenticate(user=self.teacher)
        r = c.post("/api/lectures/", {"title": "No video", "teaching_assignment": self.ta.id}, format="json")
        self.assertNotEqual(r.status_code, 413)
