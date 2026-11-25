"""
PLATFORM CONSOLE TESTS - KB Technosoft's own login and college management.

The test runner already puts every test inside the college "test"
(address "testserver"). These tests add the platform address "localhost".

Run:  python manage.py test core.tenants.tests_platform -v 2
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import Client, TestCase
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College, Domain, PlatformAdmin

PLATFORM = "localhost"
KB_PASSWORD = "Platform@12345"
COLLEGE_PASSWORD = "College@12345"


class PlatformTestBase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = connection.tenant                     # the runner's "test" college
        connection.set_schema_to_public()
        public = College.objects.get(schema_name=get_public_schema_name())
        Domain.objects.get_or_create(domain=PLATFORM, defaults={"tenant": public})
        cls.kb = PlatformAdmin(username="kbadmin", email="kb@example.com")
        cls.kb.set_password(KB_PASSWORD)
        cls.kb.save()
        connection.set_tenant(cls.home)

    @classmethod
    def tearDownClass(cls):
        connection.set_tenant(cls.home)
        super().tearDownClass()

    def setUp(self):
        self.college = College.objects.get(schema_name="test")
        get_user_model().objects.create_superuser("principal", "", COLLEGE_PASSWORD)

    def tearDown(self):
        connection.set_tenant(self.home)

    # ---------- helpers ----------
    def platform_token(self):
        r = Client(HTTP_HOST=PLATFORM).post(
            "/api/platform/login/", {"username": "kbadmin", "password": KB_PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def college_token(self):
        r = Client(HTTP_HOST="testserver").post(
            "/api/users/login/", {"username": "principal", "password": COLLEGE_PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def api(self, method, path, token, data=None, host=PLATFORM):
        c = Client(HTTP_HOST=host)
        kwargs = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        if data is not None:
            kwargs.update(data=data, content_type="application/json")
        return getattr(c, method)(path, **kwargs)


# =====================================================================
#  1) SIGNING IN AS KB TECHNOSOFT
# =====================================================================
class PlatformLoginTests(PlatformTestBase):

    def test_platform_admin_signs_in_at_the_platform_address(self):
        r = self.api("get", "/api/platform/me/", self.platform_token())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["username"], "kbadmin")

    def test_wrong_password_is_refused(self):
        r = Client(HTTP_HOST=PLATFORM).post(
            "/api/platform/login/", {"username": "kbadmin", "password": "wrong"},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_platform_login_does_not_exist_at_a_college_address(self):
        r = Client(HTTP_HOST="testserver").post(
            "/api/platform/login/", {"username": "kbadmin", "password": KB_PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_a_college_admin_cannot_sign_in_to_the_platform(self):
        r = Client(HTTP_HOST=PLATFORM).post(
            "/api/platform/login/", {"username": "principal", "password": COLLEGE_PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_no_token_means_no_access(self):
        self.assertEqual(self.api("get", "/api/platform/colleges/", None).status_code, 401)

    def test_a_college_token_is_refused_on_the_platform(self):
        r = self.api("get", "/api/platform/colleges/", self.college_token())
        self.assertEqual(r.status_code, 401)

    def test_a_platform_token_is_refused_at_a_college(self):
        r = self.api("get", "/api/users/admin-dashboard/", self.platform_token(), host="testserver")
        self.assertEqual(r.status_code, 401)

    def test_a_switched_off_platform_account_is_refused(self):
        token = self.platform_token()
        with schema_context(get_public_schema_name()):
            PlatformAdmin.objects.filter(username="kbadmin").update(is_active=False)
        self.assertEqual(self.api("get", "/api/platform/me/", token).status_code, 401)


# =====================================================================
#  2) THE COLLEGES LIST AND DETAILS
# =====================================================================
class CollegeListTests(PlatformTestBase):

    def test_list_shows_colleges_with_totals_only(self):
        from core.users.models import Department
        Department.objects.create(name="Mechanical", code="ME")
        get_user_model().objects.create_user("stu1", password="x", role="student")

        r = self.api("get", "/api/platform/colleges/", self.platform_token())
        self.assertEqual(r.status_code, 200)
        test = next(c for c in r.json() if c["code"] == "test")
        self.assertEqual(test["counts"], {"students": 1, "teachers": 0, "parents": 0, "departments": 1})
        self.assertEqual(test["admins"], ["principal"])
        self.assertTrue(test["is_active"])
        # totals only - no student appears by name
        self.assertNotIn("stu1", r.content.decode())

    def test_the_platform_itself_is_not_listed_as_a_college(self):
        r = self.api("get", "/api/platform/colleges/", self.platform_token())
        self.assertNotIn("public", [c["code"] for c in r.json()])

    def test_one_college_details(self):
        r = self.api("get", f"/api/platform/colleges/{self.college.id}/", self.platform_token())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["domain"], "testserver")

    def test_unknown_college_is_404(self):
        r = self.api("get", "/api/platform/colleges/99999/", self.platform_token())
        self.assertEqual(r.status_code, 404)


# =====================================================================
#  3) ADDING A COLLEGE FROM THE CONSOLE
# =====================================================================
class AddCollegeTests(PlatformTestBase):

    def test_add_college_builds_it_and_its_admin(self):
        r = self.api("post", "/api/platform/colleges/", self.platform_token(), {
            "name": "PQR Engineering College", "code": "pqr",
            "admin_username": "pqradmin", "admin_password": COLLEGE_PASSWORD,
        })
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["domain"], "pqr.localhost")
        self.assertEqual(r.json()["admins"], ["pqradmin"])
        # the new admin signs in at the new address
        login = Client(HTTP_HOST="pqr.localhost").post(
            "/api/users/login/", {"username": "pqradmin", "password": COLLEGE_PASSWORD},
            content_type="application/json")
        self.assertEqual(login.status_code, 200)
        # adding the same code again is refused
        again = self.api("post", "/api/platform/colleges/", self.platform_token(),
                         {"name": "PQR again", "code": "pqr"})
        self.assertEqual(again.status_code, 400)
        self.assertIn("already exists", again.json()["detail"])

    def test_bad_input_is_explained_and_creates_nothing(self):
        token = self.platform_token()
        cases = [
            ({"name": "", "code": "pqr"}, "name is required"),
            ({"name": "X", "code": "1bad"}, "Code must be"),
            ({"name": "X", "code": "test"}, "Code must be"),          # reserved code
            ({"name": "X", "code": "pqr", "admin_username": "a"}, "password is required"),
            ({"name": "X", "code": "pqr", "admin_username": "a", "admin_password": "123"}, "too short"),
        ]
        for data, words in cases:
            r = self.api("post", "/api/platform/colleges/", token, data)
            self.assertEqual(r.status_code, 400, data)
            self.assertIn(words, r.json()["detail"], data)
        self.assertFalse(College.objects.filter(schema_name="pqr").exists())

    def test_command_and_console_share_the_same_rules(self):
        with self.assertRaises(CommandError):
            call_command("create_college", "1bad", "Bad College", stdout=StringIO())


# =====================================================================
#  4) SWITCHING A COLLEGE OFF / ON, AND HELPING ITS ADMIN
# =====================================================================
class SwitchAndResetTests(PlatformTestBase):

    def switch(self, on):
        r = self.api("patch", f"/api/platform/colleges/{self.college.id}/", self.platform_token(),
                     {"is_active": on})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["is_active"], on)

    def test_switched_off_college_is_refused_then_works_again(self):
        token = self.college_token()
        self.switch(False)
        r = self.api("get", "/api/users/admin-dashboard/", token, host="testserver")
        self.assertEqual(r.status_code, 403)
        self.assertIn("switched off", r.json()["detail"])
        # the login page can still explain it
        info = Client(HTTP_HOST="testserver").get("/api/college/").json()
        self.assertFalse(info["active"])

        self.switch(True)
        r = self.api("get", "/api/users/admin-dashboard/", token, host="testserver")
        self.assertEqual(r.status_code, 200)

    def test_rename_a_college(self):
        r = self.api("patch", f"/api/platform/colleges/{self.college.id}/", self.platform_token(),
                     {"name": "Test College (renamed)"})
        self.assertEqual(r.json()["name"], "Test College (renamed)")

    def test_reset_a_college_admins_password(self):
        r = self.api("post", f"/api/platform/colleges/{self.college.id}/reset-admin-password/",
                     self.platform_token(), {"username": "principal", "new_password": "Fresh@12345"})
        self.assertEqual(r.status_code, 200, r.content)
        login = Client(HTTP_HOST="testserver").post(
            "/api/users/login/", {"username": "principal", "password": "Fresh@12345"},
            content_type="application/json")
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["must_change_password"])

    def test_cannot_reset_a_students_password(self):
        get_user_model().objects.create_user("stu1", password="x", role="student")
        r = self.api("post", f"/api/platform/colleges/{self.college.id}/reset-admin-password/",
                     self.platform_token(), {"username": "stu1", "new_password": "Fresh@12345"})
        self.assertEqual(r.status_code, 404)


# =====================================================================
#  5) THE create_platform_admin COMMAND
# =====================================================================
class CreatePlatformAdminCommandTests(PlatformTestBase):

    def test_creates_an_account_that_can_sign_in(self):
        call_command("create_platform_admin", "owner", "--password", "Owner@12345", stdout=StringIO())
        r = Client(HTTP_HOST=PLATFORM).post(
            "/api/platform/login/", {"username": "owner", "password": "Owner@12345"},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_refuses_a_weak_password(self):
        with self.assertRaises(CommandError):
            call_command("create_platform_admin", "owner", "--password", "123", stdout=StringIO())
