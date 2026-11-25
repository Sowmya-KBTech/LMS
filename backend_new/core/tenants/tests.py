"""
SAAS PHASE 1 TESTS - colleges are isolated.

The test runner (config/test_runner.py) already puts every test inside the
college "test" at the address "testserver". These tests add a SECOND college,
"other" at other.localhost, and check that the two never see each other.

Run:  python manage.py test core.tenants -v 2
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College, Domain
from core.users.models import Department

PASSWORD = "Strong@12345"


class TwoCollegeTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = connection.tenant                       # the runner's "test" college
        connection.set_schema_to_public()
        cls.public = College.objects.get(schema_name=get_public_schema_name())
        Domain.objects.get_or_create(domain="localhost", defaults={"tenant": cls.public})
        cls.other = College.objects.create(schema_name="other", name="Other College")   # builds its schema
        Domain.objects.create(domain="other.localhost", tenant=cls.other, is_primary=True)
        connection.set_tenant(cls.home)

    @classmethod
    def tearDownClass(cls):
        # the whole test transaction (colleges, domains, schemas) is rolled back
        connection.set_tenant(cls.home)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        # the same username in BOTH colleges, each with its own password
        self.home_admin = User.objects.create_superuser("principal", "", PASSWORD)
        with schema_context("other"):
            User.objects.create_superuser("principal", "", "Other@12345")

    def tearDown(self):
        connection.set_tenant(self.home)

    # ---------- helpers ----------
    def login(self, host, password):
        return Client(HTTP_HOST=host).post(
            "/api/users/login/", {"username": "principal", "password": password},
            content_type="application/json")

    def token(self):
        r = self.login("testserver", PASSWORD)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    # ---------- login ----------
    def test_login_uses_the_users_of_the_college_at_that_address(self):
        self.assertEqual(self.login("testserver", PASSWORD).status_code, 200)
        self.assertEqual(self.login("other.localhost", "Other@12345").status_code, 200)
        # home's password does not open the other college's "principal"
        self.assertEqual(self.login("other.localhost", PASSWORD).status_code, 400)

    # ---------- tokens ----------
    def test_token_works_at_its_own_college(self):
        r = Client(HTTP_HOST="testserver").get(
            "/api/users/admin-dashboard/", HTTP_AUTHORIZATION=f"Bearer {self.token()}")
        self.assertEqual(r.status_code, 200)

    def test_token_is_refused_at_another_college(self):
        r = Client(HTTP_HOST="other.localhost").get(
            "/api/users/admin-dashboard/", HTTP_AUTHORIZATION=f"Bearer {self.token()}")
        self.assertEqual(r.status_code, 401)
        self.assertIn("different college", r.json()["detail"])

    # ---------- data ----------
    def test_data_saved_in_one_college_is_not_in_the_other(self):
        Department.objects.create(name="Mechanical", code="ME")
        self.assertEqual(Department.objects.filter(name="Mechanical").count(), 1)
        with schema_context("other"):
            self.assertEqual(Department.objects.filter(name="Mechanical").count(), 0)

    def test_same_names_are_allowed_in_two_colleges(self):
        Department.objects.create(name="Mechanical", code="ME")
        with schema_context("other"):
            Department.objects.create(name="Mechanical", code="ME")       # no clash
            self.assertEqual(Department.objects.count(), 1)

    # ---------- scheduled jobs ----------
    def test_nightly_jobs_run_once_in_every_college(self):
        from modules.automation.models import JobRun
        out = StringIO()
        call_command("run_for_all_colleges", "run_daily_jobs", stdout=out, stderr=StringIO())
        self.assertIn("for 2 college(s): 2 ok, 0 failed", out.getvalue())
        self.assertTrue(JobRun.objects.filter(job="fee_due_soon").exists())          # in "test"
        with schema_context("other"):
            self.assertTrue(JobRun.objects.filter(job="fee_due_soon").exists())      # and in "other"

    # ---------- the platform address ----------
    def test_platform_status_answers_on_the_platform_address(self):
        r = Client(HTTP_HOST="localhost").get("/api/platform/status/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_college_urls_do_not_exist_on_the_platform_address(self):
        r = Client(HTTP_HOST="localhost").post(
            "/api/users/login/", {"username": "principal", "password": PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_unknown_address_is_refused(self):
        self.assertEqual(Client(HTTP_HOST="nobody.localhost").get("/api/modules/").status_code, 404)

    def test_public_schema_has_no_college_tables(self):
        with connection.cursor() as cur:
            cur.execute("SELECT table_schema FROM information_schema.tables "
                        "WHERE table_name = 'users_user' ORDER BY table_schema")
            schemas = [row[0] for row in cur.fetchall()]
        self.assertIn("other", schemas)
        self.assertNotIn("public", schemas)


class CreateCollegeCommandTests(TestCase):

    def setUp(self):
        self.home = connection.tenant

    def tearDown(self):
        connection.set_tenant(self.home)

    def run_cmd(self, *args):
        call_command("create_college", *args, stdout=StringIO())

    def test_builds_the_college_its_address_and_first_admin(self):
        self.run_cmd("pqr", "PQR Engineering College",
                     "--admin-username", "pqradmin", "--admin-password", PASSWORD)
        college = College.objects.get(schema_name="pqr")
        self.assertTrue(Domain.objects.filter(domain="pqr.localhost", tenant=college).exists())
        with schema_context("pqr"):
            admin = get_user_model().objects.get(username="pqradmin")
            self.assertEqual(admin.role, "admin")
        r = Client(HTTP_HOST="pqr.localhost").post(
            "/api/users/login/", {"username": "pqradmin", "password": PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_rejects_a_bad_or_reserved_code(self):
        # (capitals are simply lowercased: "ABC" becomes the valid code "abc")
        for bad in ("1abc", "a-b", "ab c", "public", "admin", "x"):
            with self.assertRaises(CommandError, msg=bad):
                self.run_cmd(bad, "Bad College")

    def test_rejects_a_code_that_is_taken(self):
        with self.assertRaises(CommandError):
            self.run_cmd("test", "Same code as the test college")

    def test_admin_needs_a_password(self):
        with self.assertRaises(CommandError):
            self.run_cmd("pqr", "PQR Engineering College", "--admin-username", "pqradmin")


# =====================================================================
#  SAAS PHASE 2 - the frontend at each college's own address
# =====================================================================
DEV_ORIGINS = [r"^http://([a-z0-9]+\.)?localhost:5173$"]


class CollegeAddressTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = connection.tenant
        connection.set_schema_to_public()
        public = College.objects.get(schema_name=get_public_schema_name())
        Domain.objects.get_or_create(domain="localhost", defaults={"tenant": public})
        connection.set_tenant(cls.home)

    def tearDown(self):
        connection.set_tenant(self.home)

    def test_college_info_names_the_college_of_this_address(self):
        r = Client(HTTP_HOST="testserver").get("/api/college/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"platform": False, "name": "Test College", "code": "test", "active": True,
                                    "logo_version": None})          # no logo set (COLLEGE LOGO)

    def test_college_info_on_the_platform_address_says_platform(self):
        r = Client(HTTP_HOST="localhost").get("/api/college/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["platform"])

    def test_college_info_needs_no_login_even_with_a_stale_token(self):
        r = Client(HTTP_HOST="testserver").get("/api/college/", HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(r.status_code, 200)

    @override_settings(CORS_ALLOWED_ORIGIN_REGEXES=DEV_ORIGINS)
    def test_any_college_frontend_address_is_allowed_by_cors(self):
        for origin in ("http://abc.localhost:5173", "http://xyz.localhost:5173"):
            r = Client(HTTP_HOST="testserver").get("/api/college/", HTTP_ORIGIN=origin)
            self.assertEqual(r.get("Access-Control-Allow-Origin"), origin)
            self.assertEqual(r.get("Access-Control-Allow-Credentials"), "true")

    @override_settings(CORS_ALLOWED_ORIGIN_REGEXES=DEV_ORIGINS)
    def test_other_websites_are_not_allowed_by_cors(self):
        for origin in ("http://evil.com", "http://abc.localhost.evil.com:5173", "http://abc.localhost:3000"):
            r = Client(HTTP_HOST="testserver").get("/api/college/", HTTP_ORIGIN=origin)
            self.assertIsNone(r.get("Access-Control-Allow-Origin"), origin)
