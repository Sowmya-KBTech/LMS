"""
PHASE 5, PART 4 TESTS - login protection.

  A. Too many wrong passwords -> wait (college sign-in and platform sign-in)
  B. Log out                 -> that token stops working at once
  C. Password changed        -> every older token stops working, on every device

Run:  python manage.py test core.security -v 2
"""
from datetime import timedelta

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django_tenants.utils import schema_context

from core.security.models import LoginFailure, RevokedToken
from core.tenants.tests_platform import KB_PASSWORD, PLATFORM, PlatformTestBase
from core.users.models import User

PASSWORD = "Right@12345"
HOST = "testserver"


def login(username, password, ip="10.0.0.1", **extra):
    return Client(HTTP_HOST=HOST, REMOTE_ADDR=ip).post(
        "/api/users/login/", {"username": username, "password": password},
        content_type="application/json", **extra)


def call(method, path, token, data=None, host=HOST):
    kwargs = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(Client(HTTP_HOST=host), method)(path, **kwargs)


# =====================================================================
#  A. TOO MANY WRONG PASSWORDS (college sign-in)
# =====================================================================
class LoginLimitTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("stu1", password=PASSWORD, role="student")

    def wrong(self, n, username="stu1", ip="10.0.0.1"):
        for _ in range(n):
            self.assertEqual(login(username, "bad-guess", ip).status_code, 400)

    def test_five_wrong_then_even_the_right_password_waits(self):
        self.wrong(5)
        r = login("stu1", PASSWORD)
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("access", r.json())
        self.assertIn("Too many wrong passwords", r.json()["error"])   # Login.jsx shows "error"
        self.assertTrue(1 <= int(r["Retry-After"]) <= 15 * 60)

    def test_four_wrong_still_lets_you_in_and_resets_the_count(self):
        self.wrong(4)
        self.assertEqual(login("stu1", PASSWORD).status_code, 200)
        self.wrong(4)                                   # counting starts again
        self.assertEqual(login("stu1", PASSWORD).status_code, 200)

    def test_blocked_tries_are_not_checked_and_not_counted(self):
        self.wrong(5)
        before = LoginFailure.objects.count()
        for _ in range(3):
            self.assertEqual(login("stu1", "bad-guess").status_code, 429)
        self.assertEqual(LoginFailure.objects.count(), before)

    def test_the_wait_ends_by_itself(self):
        self.wrong(5)
        LoginFailure.objects.update(at=timezone.now() - timedelta(minutes=16))
        self.assertEqual(login("stu1", PASSWORD).status_code, 200)

    def test_capital_letters_do_not_give_extra_tries(self):
        for name in ("stu1", "STU1", "Stu1", "sTu1", "stU1"):
            login(name, "bad-guess")
        self.assertEqual(login("stu1", PASSWORD).status_code, 429)

    def test_another_computer_is_not_blocked_by_the_first(self):
        self.wrong(5, ip="10.0.0.1")
        self.assertEqual(login("stu1", PASSWORD, ip="10.0.0.2").status_code, 200)

    def test_guessing_one_account_from_many_computers_is_stopped(self):
        for i in range(5):                              # 5 computers x 4 wrong = 20
            self.wrong(4, ip=f"10.0.1.{i}")
        r = login("stu1", PASSWORD, ip="10.0.9.9")      # a brand-new computer
        self.assertEqual(r.status_code, 429)

    @override_settings(LOGIN_LIMIT_PER_IP=6)
    def test_one_computer_guessing_many_accounts_is_stopped(self):
        for i in range(6):
            login(f"nobody{i}", "bad-guess", ip="10.0.0.7")
        self.assertEqual(login("stu1", PASSWORD, ip="10.0.0.7").status_code, 429)
        self.assertEqual(login("stu1", PASSWORD, ip="10.0.0.8").status_code, 200)

    def test_a_faked_forwarded_address_does_not_give_extra_tries(self):
        for i in range(5):
            login("stu1", "bad-guess", HTTP_X_FORWARDED_FOR=f"1.2.3.{i}")
        self.assertEqual(login("stu1", PASSWORD, HTTP_X_FORWARDED_FOR="9.9.9.9").status_code, 429)

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_behind_nginx_the_real_address_is_used(self):
        # Nginx puts the caller's real address last; one lab user's mistakes
        # must not block another user behind the same Nginx.
        for _ in range(5):
            login("stu1", "bad-guess", ip="127.0.0.1", HTTP_X_FORWARDED_FOR="5.5.5.5")
        self.assertEqual(login("stu1", PASSWORD, ip="127.0.0.1",
                               HTTP_X_FORWARDED_FOR="6.6.6.6").status_code, 200)
        self.assertEqual(login("stu1", PASSWORD, ip="127.0.0.1",
                               HTTP_X_FORWARDED_FOR="7.7.7.7, 5.5.5.5").status_code, 429)


# =====================================================================
#  B + C. TOKENS THAT STOP WORKING (college)
# =====================================================================
class CollegeTokenTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("teach1", password=PASSWORD, role="teacher")
        self.admin = User.objects.create_user("admin1", password=PASSWORD, role="admin")

    def token(self, username="teach1", password=PASSWORD):
        r = login(username, password)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def works(self, token):
        return call("get", f"/api/users/{self.user.id}/", token).status_code == 200

    def test_logout_ends_this_token_now(self):
        laptop, phone = self.token(), self.token()
        self.assertEqual(call("post", "/api/users/logout/", laptop).status_code, 200)
        r = call("get", f"/api/users/{self.user.id}/", laptop)
        self.assertEqual(r.status_code, 401)
        self.assertIn("signed out", r.json()["detail"])
        self.assertTrue(self.works(phone))              # only THIS device signed out

    def test_logout_also_ends_the_file_session(self):
        c = Client(HTTP_HOST=HOST)
        r = c.post("/api/users/login/", {"username": "teach1", "password": PASSWORD},
                   content_type="application/json")
        self.assertIn("_auth_user_id", c.session)
        c.post("/api/users/logout/", HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertNotIn("_auth_user_id", c.session)

    def test_changing_password_signs_out_other_devices_but_not_this_one(self):
        laptop, phone = self.token(), self.token()
        r = call("post", "/api/users/change-password/", laptop,
                 {"old_password": PASSWORD, "new_password": "Brand@New123"})
        self.assertEqual(r.status_code, 200, r.content)
        fresh = r.json()["access"]

        for old in (laptop, phone):
            r = call("get", f"/api/users/{self.user.id}/", old)
            self.assertEqual(r.status_code, 401)
            self.assertIn("password was changed", r.json()["detail"])
        self.assertTrue(self.works(fresh))              # this device stays signed in

    def test_password_reset_by_the_admin_signs_the_person_out(self):
        old = self.token()
        self.user.set_password("Reset@12345")
        self.user.save()
        self.assertFalse(self.works(old))
        self.assertTrue(self.works(self.token(password="Reset@12345")))

    def test_switched_off_account_is_refused(self):
        old = self.token()
        self.user.is_active = False
        self.user.save()
        self.assertFalse(self.works(old))

    def test_token_without_the_password_stamp_is_refused(self):
        # tokens issued before this update carry no stamp: one fresh sign-in needed
        from core.tenants.jwt import TenantRefreshToken
        t = TenantRefreshToken.for_user(self.user)
        access = t.access_token
        del access["pv"]
        self.assertFalse(self.works(str(access)))

    def test_old_signed_out_tokens_are_cleaned_up(self):
        RevokedToken.objects.create(jti="long-gone", expires_at=timezone.now() - timedelta(days=2))
        call("post", "/api/users/logout/", self.token())
        self.assertFalse(RevokedToken.objects.filter(jti="long-gone").exists())
        self.assertEqual(RevokedToken.objects.count(), 1)


# =====================================================================
#  A + B + C. PLATFORM (KB Technosoft) SIGN-IN
# =====================================================================
class PlatformProtectionTests(PlatformTestBase):

    def platform_login(self, password, ip="10.0.0.1"):
        return Client(HTTP_HOST=PLATFORM, REMOTE_ADDR=ip).post(
            "/api/platform/login/", {"username": "kbadmin", "password": password},
            content_type="application/json")

    def test_platform_wrong_passwords_are_limited(self):
        for _ in range(5):
            self.assertEqual(self.platform_login("bad-guess").status_code, 400)
        r = self.platform_login(KB_PASSWORD)
        self.assertEqual(r.status_code, 429)
        self.assertIn("Too many wrong passwords", r.json()["detail"])

    def test_platform_counts_are_separate_from_the_colleges(self):
        for _ in range(5):
            self.platform_login("bad-guess")
        connection.set_tenant(self.home)
        self.assertEqual(LoginFailure.objects.count(), 0)    # nothing in the college schema
        with schema_context("public"):
            self.assertEqual(LoginFailure.objects.count(), 5)

    def test_platform_logout_ends_the_token(self):
        token = self.platform_token()
        self.assertEqual(self.api("post", "/api/platform/logout/", token).status_code, 200)
        self.assertEqual(self.api("get", "/api/platform/me/", token).status_code, 401)
        self.assertEqual(self.api("get", "/api/platform/me/", self.platform_token()).status_code, 200)

    def test_platform_password_change_ends_old_tokens(self):
        token = self.platform_token()
        with schema_context("public"):
            self.kb.refresh_from_db()
            self.kb.set_password("Another@12345")
            self.kb.save()
        r = self.api("get", "/api/platform/me/", token)
        self.assertEqual(r.status_code, 401)
        self.assertIn("password was changed", r.json()["detail"])

    def test_platform_reset_of_a_college_admin_signs_them_out(self):
        college_token = self.college_token()
        r = self.api("post", f"/api/platform/colleges/{self.college.id}/reset-admin-password/",
                     self.platform_token(), {"username": "principal", "new_password": "Fresh@Pass987"})
        self.assertEqual(r.status_code, 200, r.content)
        r = self.api("get", "/api/users/admin-dashboard/", college_token, host=HOST)
        self.assertEqual(r.status_code, 401)
