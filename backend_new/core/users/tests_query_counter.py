"""Tests for the development-only query counter middleware."""
from django.contrib.auth import get_user_model
from django.test import TestCase, modify_settings
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

User = get_user_model()


@modify_settings(MIDDLEWARE={"prepend": "config.query_counter.QueryCountMiddleware"})
class QueryCounterTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("qc_user", "qc@example.com", "pw", role="teacher")
        token = str(RefreshToken.for_user(self.user).access_token)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_headers_are_added(self):
        response = self.client.get("/api/notifications/?unread=true", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-DB-Queries", response)
        self.assertIn("X-DB-Time-ms", response)
        self.assertIn("X-Total-Time-ms", response)

    def test_counts_database_queries(self):
        response = self.client.get("/api/notifications/?unread=true", **self.auth)
        # at least: load the user for JWT auth + list notifications
        self.assertGreaterEqual(int(response["X-DB-Queries"]), 2)