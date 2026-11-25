"""
PHASE 4 TESTS - every college's uploaded files stay in that college.

The test runner puts every test inside the college "test" (address
"testserver"). These tests add a second college, "mediaother"
(mediaother.localhost). Files are written to a temporary folder, never to
the real media folder.

Run:  python manage.py test core.tenants.tests_media -v 2
"""
import os
import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django_tenants.utils import schema_context

from core.tenants.models import College, Domain
from core.users.models import StudentProfile

PASSWORD = "Strong@12345"
HOME, HOME_CODE = "testserver", "test"
OTHER, OTHER_CODE = "mediaother.localhost", "mediaother"


class MediaTestBase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = connection.tenant
        connection.set_schema_to_public()
        cls.other = College.objects.create(schema_name=OTHER_CODE, name="Other College")
        Domain.objects.create(domain=OTHER, tenant=cls.other, is_primary=True)
        connection.set_tenant(cls.home)

    @classmethod
    def tearDownClass(cls):
        connection.set_tenant(cls.home)
        super().tearDownClass()

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="kbtc-media-")
        # MULTITENANT_RELATIVE_MEDIA_ROOT is set again so the storage forgets its cached folder
        self.media = override_settings(MEDIA_ROOT=self.media_root,
                                       MULTITENANT_RELATIVE_MEDIA_ROOT="%s")
        self.media.enable()
        User = get_user_model()
        self.student = User.objects.create_user("stu1", password=PASSWORD, role="student")
        with schema_context(OTHER_CODE):
            User.objects.create_user("stu1", password=PASSWORD, role="student")

    def tearDown(self):
        connection.set_tenant(self.home)
        self.media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    # ---------- helpers ----------
    def upload_photo(self, user, content=b"PHOTO", name="ravi.jpg"):
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        profile.photo.save(name, ContentFile(content), save=True)
        return profile

    def signed_in(self, host=HOME):
        c = Client(HTTP_HOST=host)
        r = c.post("/api/users/login/", {"username": "stu1", "password": PASSWORD},
                   content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return c

    @staticmethod
    def body(response):
        return b"".join(response.streaming_content) if response.streaming else response.content


# =====================================================================
#  1) SAVING: each college writes into its own folder
# =====================================================================
class SavingTests(MediaTestBase):

    def test_upload_goes_into_this_colleges_folder(self):
        profile = self.upload_photo(self.student)
        self.assertEqual(profile.photo.name, "student_photos/ravi.jpg")       # short name in the database
        self.assertTrue(os.path.isfile(
            os.path.join(self.media_root, HOME_CODE, "student_photos", "ravi.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.media_root, "student_photos")))
        self.assertEqual(profile.photo.url, f"/media/{HOME_CODE}/student_photos/ravi.jpg")

    def test_two_colleges_same_file_name_never_collide(self):
        self.upload_photo(self.student, b"HOME")
        with schema_context(OTHER_CODE):
            other_student = get_user_model().objects.get(username="stu1")
            self.upload_photo(other_student, b"OTHER")
        with open(os.path.join(self.media_root, HOME_CODE, "student_photos", "ravi.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"HOME")
        with open(os.path.join(self.media_root, OTHER_CODE, "student_photos", "ravi.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"OTHER")


# =====================================================================
#  2) SERVING: only this college's files, only when signed in here
# =====================================================================
class ServingTests(MediaTestBase):

    def test_signed_in_user_gets_their_colleges_file(self):
        profile = self.upload_photo(self.student, b"HOME")
        r = self.signed_in().get(profile.photo.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.body(r), b"HOME")
        self.assertIn("private", r["Cache-Control"])

    def test_not_signed_in_is_refused(self):
        profile = self.upload_photo(self.student)
        r = Client(HTTP_HOST=HOME).get(profile.photo.url)
        self.assertEqual(r.status_code, 403)

    def test_token_also_works(self):
        profile = self.upload_photo(self.student)
        c = Client(HTTP_HOST=HOME)
        token = c.post("/api/users/login/", {"username": "stu1", "password": PASSWORD},
                       content_type="application/json").json()["access"]
        r = Client(HTTP_HOST=HOME).get(profile.photo.url, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 200)

    def test_another_colleges_link_does_not_exist_here(self):
        with schema_context(OTHER_CODE):
            other_student = get_user_model().objects.get(username="stu1")
            url = self.upload_photo(other_student, b"OTHER").photo.url     # /media/mediaother/...
        r = self.signed_in(HOME).get(url)                                   # asked at the HOME address
        self.assertEqual(r.status_code, 404)

    def test_another_colleges_login_cannot_open_this_colleges_file(self):
        url = self.upload_photo(self.student).photo.url                     # /media/test/...
        r = self.signed_in(OTHER).get(url)                                  # asked at the OTHER address
        self.assertEqual(r.status_code, 404)

    def test_path_tricks_are_refused(self):
        self.upload_photo(self.student)
        with schema_context(OTHER_CODE):
            self.upload_photo(get_user_model().objects.get(username="stu1"), b"OTHER")
        c = self.signed_in()
        for url in (f"/media/{HOME_CODE}/../{OTHER_CODE}/student_photos/ravi.jpg",
                    f"/media/{HOME_CODE}/..%2F{OTHER_CODE}/student_photos/ravi.jpg",
                    "/media/../config/settings.py",
                    f"/media/{HOME_CODE}",
                    f"/media/{HOME_CODE}/"):
            self.assertIn(c.get(url).status_code, (400, 404), url)

    def test_missing_file_is_404(self):
        r = self.signed_in().get(f"/media/{HOME_CODE}/student_photos/nothing.jpg")
        self.assertEqual(r.status_code, 404)

    def test_platform_address_serves_no_files(self):
        self.upload_photo(self.student)
        connection.set_schema_to_public()
        from django_tenants.utils import get_public_schema_name
        public = College.objects.get(schema_name=get_public_schema_name())
        Domain.objects.get_or_create(domain="localhost", defaults={"tenant": public})
        connection.set_tenant(self.home)
        r = Client(HTTP_HOST="localhost").get(f"/media/{HOME_CODE}/student_photos/ravi.jpg")
        self.assertEqual(r.status_code, 404)

    def test_switched_off_college_files_are_refused(self):
        profile = self.upload_photo(self.student)
        c = self.signed_in()
        College.objects.filter(schema_name=HOME_CODE).update(is_active=False)
        try:
            self.assertEqual(c.get(profile.photo.url).status_code, 403)
        finally:
            College.objects.filter(schema_name=HOME_CODE).update(is_active=True)

    def test_nginx_mode_hands_the_file_to_nginx(self):
        profile = self.upload_photo(self.student)
        with override_settings(MEDIA_ACCEL_REDIRECT_PREFIX="/protected-media/"):
            r = self.signed_in().get(profile.photo.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-Accel-Redirect"], f"/protected-media/{HOME_CODE}/student_photos/ravi.jpg")


# =====================================================================
#  3) MOVING THE FILES THAT WERE SAVED BEFORE PHASE 4
# =====================================================================
class MoveCommandTests(MediaTestBase):

    def old_shared_file(self, name, content):
        path = os.path.join(self.media_root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def point_to(self, user, name):
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        StudentProfile.objects.filter(pk=profile.pk).update(photo=name)   # as an old record would be

    def run_move(self, *args):
        out = StringIO()
        call_command("move_media_to_colleges", *args, stdout=out)
        return out.getvalue()

    def test_report_mode_changes_nothing(self):
        old = self.old_shared_file("student_photos/old.jpg", b"OLD")
        self.point_to(self.student, "student_photos/old.jpg")
        out = self.run_move("--only", HOME_CODE)
        self.assertIn("would copy student_photos/old.jpg", out)
        self.assertTrue(os.path.isfile(old))
        self.assertFalse(os.path.exists(os.path.join(self.media_root, HOME_CODE)))

    def test_apply_copies_into_each_colleges_folder(self):
        self.old_shared_file("student_photos/old.jpg", b"OLD")
        self.point_to(self.student, "student_photos/old.jpg")
        out = self.run_move("--apply", "--only", HOME_CODE)
        self.assertIn("1 copied", out)
        moved = os.path.join(self.media_root, HOME_CODE, "student_photos", "old.jpg")
        self.assertTrue(os.path.isfile(moved))
        # the record did not change, and the file now opens through the college address
        profile = StudentProfile.objects.get(user=self.student)
        self.assertEqual(profile.photo.name, "student_photos/old.jpg")
        r = self.signed_in().get(profile.photo.url)
        self.assertEqual(self.body(r), b"OLD")

    def test_running_again_is_safe(self):
        self.old_shared_file("student_photos/old.jpg", b"OLD")
        self.point_to(self.student, "student_photos/old.jpg")
        self.run_move("--apply", "--only", HOME_CODE)
        out = self.run_move("--apply", "--only", HOME_CODE)
        self.assertIn("0 copied, 1 already in place", out)

    def test_remove_old_deletes_the_shared_copy(self):
        old = self.old_shared_file("student_photos/old.jpg", b"OLD")
        self.point_to(self.student, "student_photos/old.jpg")
        self.run_move("--apply", "--remove-old", "--only", HOME_CODE)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(os.path.join(self.media_root, HOME_CODE, "student_photos", "old.jpg")))

    def test_missing_files_are_reported(self):
        self.point_to(self.student, "student_photos/gone.jpg")
        out = self.run_move("--only", HOME_CODE)
        self.assertIn("file not found: student_photos/gone.jpg", out)
