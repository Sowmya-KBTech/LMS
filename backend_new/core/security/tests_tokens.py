"""
SECURITY TESTS - expired and tampered sign-in tokens.

Asked for in the deployment plan ("JWT expiry") and the technical guide
("expired and tampered tokens"). A token is refused when it is:

  * expired
  * edited (role, user id or college changed) - the signature no longer matches
  * signed with someone else's key
  * using "alg: none" (no signature at all)
  * a refresh token used as an access token
  * garbage

Both the college sign-in and the KB Technosoft platform sign-in are checked.

Run:  python manage.py test core.security.tests_tokens -v 2
"""
import base64
import json
from datetime import timedelta

import jwt as pyjwt
from django.conf import settings
from django.test import Client, TestCase
from rest_framework_simplejwt.tokens import AccessToken

from core.tenants.jwt import TenantRefreshToken
from core.tenants.platform_auth import platform_token_for
from core.tenants.tests_platform import PLATFORM, PlatformTestBase
from core.users.models import User

HOST = "testserver"


def b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def parts(token):
    head, body, sig = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    return (json.loads(base64.urlsafe_b64decode(pad(head))),
            json.loads(base64.urlsafe_b64decode(pad(body))), sig)


def edited(token, **changes):
    """Change claims but keep the ORIGINAL signature - what an attacker would try."""
    head, body, sig = parts(token)
    body.update(changes)
    return f"{b64(head)}.{b64(body)}.{sig}"


class CollegeTokenTamperTests(TestCase):

    def setUp(self):
        self.student = User.objects.create_user("stu1", password="Right@12345", role="student")
        self.admin = User.objects.create_user("admin1", password="Right@12345", role="admin")
        self.good = str(TenantRefreshToken.for_user(self.student).access_token)

    def status(self, token, path):
        return Client(HTTP_HOST=HOST).get(path, HTTP_AUTHORIZATION=f"Bearer {token}").status_code

    def path(self):
        return f"/api/users/{self.student.id}/"

    def test_a_good_token_works(self):
        self.assertEqual(self.status(self.good, self.path()), 200)

    def test_expired_token_is_refused(self):
        access = TenantRefreshToken.for_user(self.student).access_token
        access.set_exp(lifetime=-timedelta(seconds=1))
        self.assertEqual(self.status(str(access), self.path()), 401)

    def test_token_lasts_only_the_configured_time(self):
        _, body, _ = parts(self.good)
        lifetime = body["exp"] - body["iat"]
        self.assertEqual(lifetime, int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()))

    def test_making_yourself_another_user_is_refused(self):
        forged = edited(self.good, user_id=self.admin.id)
        self.assertEqual(self.status(forged, f"/api/users/{self.admin.id}/"), 401)

    def test_extending_your_own_expiry_is_refused(self):
        _, body, _ = parts(self.good)
        self.assertEqual(self.status(edited(self.good, exp=body["exp"] + 365 * 86400), self.path()), 401)

    def test_changing_the_college_is_refused(self):
        self.assertEqual(self.status(edited(self.good, tenant="xyz"), self.path()), 401)

    def test_token_signed_with_another_key_is_refused(self):
        _, body, _ = parts(self.good)
        forged = pyjwt.encode(body, "not-our-secret-key-" * 4, algorithm="HS256")
        self.assertEqual(self.status(forged, self.path()), 401)

    def test_unsigned_alg_none_token_is_refused(self):
        _, body, _ = parts(self.good)
        forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(body)}."
        self.assertEqual(self.status(forged, self.path()), 401)

    def test_refresh_token_cannot_be_used_as_access(self):
        refresh = str(TenantRefreshToken.for_user(self.student))
        self.assertEqual(self.status(refresh, self.path()), 401)

    def test_garbage_is_refused(self):
        for junk in ("abc", "a.b.c", "", "Bearer", "eyJhbGciOiJIUzI1NiJ9.e30."):
            self.assertEqual(self.status(junk, self.path()), 401, junk)


class PlatformTokenTamperTests(PlatformTestBase):

    def me(self, token):
        return self.api("get", "/api/platform/me/", token).status_code

    def test_expired_platform_token_is_refused(self):
        from core.tenants.models import PlatformAdmin
        from django_tenants.utils import schema_context
        with schema_context("public"):
            admin = PlatformAdmin.objects.get(username="kbadmin")
            raw = AccessToken(platform_token_for(admin))
        raw.set_exp(lifetime=-timedelta(seconds=1))
        self.assertEqual(self.me(str(raw)), 401)

    def test_platform_token_with_edited_scope_or_admin_is_refused(self):
        good = self.platform_token()
        self.assertEqual(self.me(good), 200)
        self.assertEqual(self.me(edited(good, platform_admin_id=999)), 401)
        self.assertEqual(self.me(edited(good, exp=parts(good)[1]["exp"] + 86400)), 401)

    def test_college_token_edited_into_a_platform_token_is_refused(self):
        college = self.college_token()
        forged = edited(college, scope="platform", tenant="public", platform_admin_id=1)
        self.assertEqual(self.me(forged), 401)
