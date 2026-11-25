"""Step 4 - tests for the notification bell cache."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from core.notifications.cache import unread_key
from core.notifications.models import Notification
from core.notifications.services import notify

User = get_user_model()
BELL = "/api/notifications/?unread=true"


class BellCacheTests(TestCase):

    def setUp(self):
        self.a = User.objects.create_user("bell_a", "a@example.com", "pw", role="student")
        self.b = User.objects.create_user("bell_b", "b@example.com", "pw", role="student")
        self.keys = [unread_key(u.pk) for u in (self.a, self.b)]
        cache.delete_many(self.keys)
        self.addCleanup(cache.delete_many, self.keys)
        self.first = Notification.objects.create(recipient=self.a, title="A1", message="m")

    def get(self, user, url=BELL):
        token = str(RefreshToken.for_user(user).access_token)
        return self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def post(self, user, url):
        token = str(RefreshToken.for_user(user).access_token)
        return self.client.post(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_first_call_misses_then_hits_with_same_data(self):
        r1 = self.get(self.a)
        r2 = self.get(self.a)
        self.assertEqual(r1["X-Cache"], "MISS")
        self.assertEqual(r2["X-Cache"], "HIT")
        self.assertEqual(r1.json(), r2.json())
        self.assertEqual(len(r2.json()), 1)

    def test_cache_hit_uses_fewer_queries(self):
        with CaptureQueriesContext(connection) as miss:
            self.get(self.a)
        with CaptureQueriesContext(connection) as hit:
            self.get(self.a)
        self.assertLess(len(hit), len(miss))
        # multi-college: the hit still runs the college lookup and the sign-in
        # checks (security phase), but never reads the cached data itself
        read = [q["sql"] for q in hit.captured_queries if any(t in q["sql"] for t in ['notifications_notification'])]
        self.assertEqual(read, [])

    def test_key_has_college_prefix(self):
        # multi-college: the prefix is the schema of the college ("test" in tests)
        self.assertEqual(cache.make_key(unread_key(self.a.pk)),
                         f"lms:test:notifications:unread:{self.a.pk}")

    def test_new_notification_clears_cache(self):
        self.get(self.a)
        with self.captureOnCommitCallbacks(execute=True):
            Notification.objects.create(recipient=self.a, title="A2", message="m")
        r = self.get(self.a)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 2)

    def test_mark_read_clears_cache(self):
        self.get(self.a)
        with self.captureOnCommitCallbacks(execute=True):
            self.post(self.a, f"/api/notifications/{self.first.pk}/mark_read/")
        r = self.get(self.a)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 0)

    def test_mark_all_read_clears_cache(self):
        self.get(self.a)
        with self.captureOnCommitCallbacks(execute=True):
            self.post(self.a, "/api/notifications/mark_all_read/")
        r = self.get(self.a)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 0)

    def test_bulk_notify_clears_cache(self):
        self.get(self.a)
        with self.captureOnCommitCallbacks(execute=True):
            notify([self.a], "Bulk", "m")
        r = self.get(self.a)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 2)

    def test_each_user_has_own_cache(self):
        self.get(self.a)                      # cache A's list
        r = self.get(self.b)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 0)    # B never sees A's notifications

    def test_other_list_requests_are_not_cached(self):
        r = self.get(self.a, "/api/notifications/")
        self.assertNotIn("X-Cache", r)