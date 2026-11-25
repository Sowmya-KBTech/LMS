"""Step 5.1 - tests for the shared timeslots cache."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from config.shared_cache import shared_key
from modules.timetable.models import TimeSlot

User = get_user_model()
URL = "/api/timeslots/"


class TimeslotsCacheTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user("ts_admin", "a@example.com", "pw", role="admin")
        self.student = User.objects.create_user("ts_student", "s@example.com", "pw", role="student")
        cache.delete(shared_key("timeslots"))
        self.addCleanup(cache.delete, shared_key("timeslots"))
        self.p1 = TimeSlot.objects.create(period_no=1, start_time=datetime.time(9, 0),
                                          end_time=datetime.time(9, 50))
        TimeSlot.objects.create(period_no=2, start_time=datetime.time(10, 0),
                                end_time=datetime.time(10, 50))

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(user).access_token}"}

    def get(self, user):
        return self.client.get(URL, **self.auth(user))

    def test_first_call_misses_then_hits_with_same_data(self):
        r1, r2 = self.get(self.student), self.get(self.student)
        self.assertEqual((r1["X-Cache"], r2["X-Cache"]), ("MISS", "HIT"))
        self.assertEqual(r1.json(), r2.json())
        self.assertEqual(len(r2.json()), 2)

    def test_cache_hit_uses_fewer_queries(self):
        with CaptureQueriesContext(connection) as miss:
            self.get(self.student)
        with CaptureQueriesContext(connection) as hit:
            self.get(self.student)
        self.assertLess(len(hit), len(miss))
        # multi-college: the hit still runs the college lookup and the sign-in
        # checks (security phase), but never reads the cached data itself
        read = [q["sql"] for q in hit.captured_queries if any(t in q["sql"] for t in ['timetable_timeslot'])]
        self.assertEqual(read, [])

    def test_everyone_shares_one_cache_entry(self):
        self.get(self.student)
        r = self.get(self.admin)
        self.assertEqual(r["X-Cache"], "HIT")

    def test_key_has_college_prefix(self):
        # multi-college: the prefix is the schema of the college ("test" in tests)
        self.assertEqual(cache.make_key(shared_key("timeslots")), "lms:test:shared:timeslots")

    def test_admin_create_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(URL, {"period_no": 3, "start_time": "11:00", "end_time": "11:50"},
                                 content_type="application/json", **self.auth(self.admin))
        self.assertEqual(r.status_code, 201)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 3)

    def test_admin_update_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f"{URL}{self.p1.pk}/", {"label": "Morning"},
                              content_type="application/json", **self.auth(self.admin))
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertIn("Morning", [row["label"] for row in r.json()])

    def test_admin_delete_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(f"{URL}{self.p1.pk}/", **self.auth(self.admin))
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(len(r.json()), 1)

    def test_change_outside_the_api_also_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):   # e.g. Django admin / shell
            TimeSlot.objects.create(period_no=4, start_time=datetime.time(12, 0),
                                    end_time=datetime.time(12, 50))
        self.assertEqual(self.get(self.student)["X-Cache"], "MISS")

    def test_student_still_cannot_create(self):
        r = self.client.post(URL, {"period_no": 5, "start_time": "13:00", "end_time": "13:50"},
                             content_type="application/json", **self.auth(self.student))
        self.assertEqual(r.status_code, 403)