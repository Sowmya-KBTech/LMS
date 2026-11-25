"""Step 5.3 - tests for the shared holidays cache (Holiday + calendar holidays)."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from config.shared_cache import shared_key
from modules.events.models import CalendarEvent
from modules.timetable.models import Holiday

User = get_user_model()
URL = "/api/holidays/"
D = datetime.date


class HolidaysCacheTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user("hol_admin", "a@example.com", "pw", role="admin")
        self.student = User.objects.create_user("hol_student", "s@example.com", "pw", role="student")
        cache.delete(shared_key("holidays"))
        self.addCleanup(cache.delete, shared_key("holidays"))
        self.h1 = Holiday.objects.create(date=D(2026, 12, 25), name="Christmas")
        self.ev = CalendarEvent.objects.create(title="Pongal", event_type="holiday",
                                               start_date=D(2027, 1, 14), end_date=D(2027, 1, 15))

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(user).access_token}"}

    def get(self, user):
        return self.client.get(URL, **self.auth(user))

    def names(self, response):
        return [row["name"] for row in response.json()]

    def test_first_call_misses_then_hits_with_same_data(self):
        r1, r2 = self.get(self.student), self.get(self.student)
        self.assertEqual((r1["X-Cache"], r2["X-Cache"]), ("MISS", "HIT"))
        self.assertEqual(r1.json(), r2.json())
        # 1 timetable holiday + 2 calendar days (Pongal is 2 days)
        self.assertEqual(self.names(r2), ["Christmas", "Pongal", "Pongal"])

    def test_cache_hit_uses_fewer_queries(self):
        with CaptureQueriesContext(connection) as miss:
            self.get(self.student)
        with CaptureQueriesContext(connection) as hit:
            self.get(self.student)
        self.assertLess(len(hit), len(miss))
        # multi-college: the hit still runs the college lookup and the sign-in
        # checks (security phase), but never reads the cached data itself
        read = [q["sql"] for q in hit.captured_queries if any(t in q["sql"] for t in ['timetable_holiday', 'events_calendarevent'])]
        self.assertEqual(read, [])

    def test_everyone_shares_one_cache_entry(self):
        self.get(self.student)
        self.assertEqual(self.get(self.admin)["X-Cache"], "HIT")

    def test_admin_create_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(URL, {"date": "2026-11-01", "name": "Founders Day"},
                                 content_type="application/json", **self.auth(self.admin))
        self.assertEqual(r.status_code, 201)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertIn("Founders Day", self.names(r))

    def test_admin_delete_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.delete(f"{URL}{self.h1.pk}/", **self.auth(self.admin))
        self.assertEqual(r.status_code, 204)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertNotIn("Christmas", self.names(r))

    def test_new_calendar_holiday_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            CalendarEvent.objects.create(title="Diwali", event_type="holiday",
                                         start_date=D(2026, 11, 8))
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertIn("Diwali", self.names(r))

    def test_calendar_event_changed_from_holiday_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.ev.event_type = "event"
            self.ev.save()
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertNotIn("Pongal", self.names(r))

    def test_bulk_delete_of_calendar_holidays_clears_cache(self):
        # the Google holiday sync deletes old rows with queryset.delete()
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            CalendarEvent.objects.filter(event_type="holiday").delete()
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(self.names(r), ["Christmas"])

    def test_student_still_cannot_create(self):
        self.get(self.student)
        r = self.client.post(URL, {"date": "2026-11-02", "name": "X"},
                             content_type="application/json", **self.auth(self.student))
        self.assertEqual(r.status_code, 403)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "HIT")
        self.assertNotIn("X", self.names(r))