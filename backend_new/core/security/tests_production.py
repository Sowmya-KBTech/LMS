"""
PHASE 5, PART 5 TESTS - production safety settings.

  A. The server refuses to start with unsafe production settings
  B. Safe headers on every response; HTTPS behind Nginx works (no redirect loop)
  C. Password change follows the real password rules

Run:  python manage.py test core.security.tests_production -v 2
"""
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from dotenv import dotenv_values
from django.test import Client, TestCase, override_settings

from config.production import check_production_settings
from core.users.models import User

BACKEND = Path(settings.BASE_DIR)

GOOD = {
    "DEBUG": False,
    "SECRET_KEY": "q8#n2Lr!vZ0kT7wPmY4@cS9hJ6eF1xU3bG5dA&iO-R%tE*uW(K",
    "ALLOWED_HOSTS": [".kbtechcampus.in", "kbtechcampus.in"],
    "PAYMENT_ENCRYPTION_KEY": "x" * 44,
    "CORS_ALLOWED_ORIGINS": [],
    "CORS_ALLOWED_ORIGIN_REGEXES": [r"^https://([a-z0-9-]+\.)?kbtechcampus\.in$"],
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "DATABASES": {"default": {"PASSWORD": "strong-db-pass"}},
}


def problems_with(**changes):
    return check_production_settings(dict(GOOD, **changes))


# =====================================================================
#  A. UNSAFE PRODUCTION SETTINGS ARE REFUSED
# =====================================================================
class ProductionCheckTests(TestCase):

    def test_safe_settings_pass(self):
        self.assertEqual(check_production_settings(GOOD), [])

    def test_debug_on_is_refused(self):
        self.assertIn("DJANGO_DEBUG", problems_with(DEBUG=True)[0])

    def test_weak_or_missing_secret_keys_are_refused(self):
        for key in ("", "short", "devsecret-xyz", "django-insecure-" + "a1b2c3d4e5" * 5,
                    "a" * 60, "my-secret-key-" + "Z9" * 20):
            self.assertTrue(problems_with(SECRET_KEY=key), key)

    def test_hosts_must_be_real_domains(self):
        for hosts in ([], ["*"], [".localhost", "localhost"], ["127.0.0.1"]):
            self.assertTrue(problems_with(ALLOWED_HOSTS=hosts), hosts)

    def test_payment_key_is_required(self):
        self.assertIn("PAYMENT_ENCRYPTION_KEY", problems_with(PAYMENT_ENCRYPTION_KEY="")[0])

    def test_cors_must_be_https_college_addresses(self):
        self.assertTrue(problems_with(CORS_ALLOWED_ORIGIN_REGEXES=[]))
        self.assertTrue(problems_with(CORS_ALLOWED_ORIGIN_REGEXES=[r"^http://([a-z0-9]+\.)?localhost:5173$"]))
        self.assertTrue(problems_with(CORS_ALLOWED_ORIGIN_REGEXES=[r"^http://abc\.kbtechcampus\.in$"]))

    def test_cookies_and_db_password(self):
        self.assertTrue(problems_with(SESSION_COOKIE_SECURE=False))
        self.assertTrue(problems_with(DATABASES={"default": {"PASSWORD": ""}}))

    def test_every_problem_is_listed_at_once(self):
        self.assertGreaterEqual(len(problems_with(DEBUG=True, SECRET_KEY="", ALLOWED_HOSTS=["*"])), 3)

    def _start(self, **env):
        """Start Django the way the server would, with these .env values."""
        base = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "PAYMENT_"))}
        # settings.py also reads backend/.env, which would fill the removed values
        # back in (e.g. the laptop's localhost CORS). An empty value blocks that,
        # so only what this test sets counts.
        for key in dotenv_values(BACKEND / ".env"):
            if key.startswith(("DJANGO_", "PAYMENT_")):
                base[key] = ""
        base.update(env)
        return subprocess.run(
            [sys.executable, "-c", "import django; django.setup(); print('STARTED')"],
            cwd=BACKEND, env=dict(base, DJANGO_SETTINGS_MODULE="config.settings"),
            capture_output=True, text=True, timeout=120)

    def test_server_will_not_start_with_laptop_settings_in_production(self):
        r = self._start(DJANGO_ENV="production", DJANGO_DEBUG="True", DJANGO_SECRET_KEY="devsecret-xyz",
                        DJANGO_ALLOWED_HOSTS="localhost", DB_PASSWORD="x")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("STARTED", r.stdout)
        self.assertIn("not safe yet", r.stderr)
        self.assertIn("DJANGO_DEBUG must be False", r.stderr)

    def test_server_starts_with_safe_production_settings(self):
        r = self._start(DJANGO_ENV="production", DJANGO_DEBUG="False", DJANGO_SECRET_KEY=GOOD["SECRET_KEY"],
                        DJANGO_ALLOWED_HOSTS=".kbtechcampus.in", PAYMENT_ENCRYPTION_KEY="k" * 44,
                        DJANGO_CORS_ORIGIN_REGEXES=GOOD["CORS_ALLOWED_ORIGIN_REGEXES"][0],
                        DB_PASSWORD="strong-db-pass")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertIn("STARTED", r.stdout)

    def test_laptop_is_never_blocked(self):
        r = self._start(DJANGO_ENV="development", DJANGO_DEBUG="True", DJANGO_SECRET_KEY="devsecret-xyz")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


# =====================================================================
#  B. SAFE HEADERS + HTTPS BEHIND NGINX
# =====================================================================
class HeaderTests(TestCase):

    def test_every_response_has_the_safe_headers(self):
        r = Client(HTTP_HOST="testserver").get("/api/college/")
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000,
                       SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
                       SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_behind_nginx_https_is_understood_and_http_is_redirected(self):
        c = Client(HTTP_HOST="testserver")
        r = c.get("/api/college/")                                     # plain http
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://"))
        r = c.get("/api/college/", HTTP_X_FORWARDED_PROTO="https")     # via Nginx on https
        self.assertEqual(r.status_code, 200)                           # no redirect loop
        self.assertIn("max-age=31536000", r["Strict-Transport-Security"])
        self.assertIn("includeSubDomains", r["Strict-Transport-Security"])

    def test_admin_address_comes_from_settings(self):
        from django.urls import reverse
        self.assertEqual(reverse("admin:index"), "/" + settings.ADMIN_URL)


# =====================================================================
#  C. PASSWORD RULES ON CHANGE
# =====================================================================
class PasswordRuleTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("ravikumar", password="Right@12345", role="student")
        r = Client(HTTP_HOST="testserver").post(
            "/api/users/login/", {"username": "ravikumar", "password": "Right@12345"},
            content_type="application/json")
        self.token = r.json()["access"]

    def change(self, new):
        return Client(HTTP_HOST="testserver").post(
            "/api/users/change-password/", {"old_password": "Right@12345", "new_password": new},
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_weak_passwords_are_refused_with_the_reason(self):
        for weak, reason in (("abc12", "too short"), ("password", "too common"),
                             ("12345678901", "entirely numeric"), ("ravikumar1", "too similar")):
            r = self.change(weak)
            self.assertEqual(r.status_code, 400, weak)
            self.assertIn(reason, r.json()["detail"].lower(), weak)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Right@12345"))

    def test_a_good_password_is_accepted(self):
        self.assertEqual(self.change("Lotus#Garden42").status_code, 200)
