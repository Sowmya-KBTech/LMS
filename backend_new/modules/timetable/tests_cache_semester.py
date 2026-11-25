"""Step 5.2 - tests for the shared active-semester cache."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from core.tenants.jwt import TenantRefreshToken as RefreshToken   # multi-college token

from config.shared_cache import shared_key
from modules.timetable.models import Semester

User = get_user_model()
URL = "/api/semester/"


class SemesterCacheTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user("sem_admin", "a@example.com", "pw", role="admin")
        self.student = User.objects.create_user("sem_student", "s@example.com", "pw", role="student")
        cache.delete(shared_key("semester"))
        self.addCleanup(cache.delete, shared_key("semester"))
        self.sem = Semester.objects.create(name="Odd 2026", start_date=datetime.date(2026, 7, 1),
                                           end_date=datetime.date(2026, 11, 30), is_active=True)

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(user).access_token}"}

    def get(self, user):
        return self.client.get(URL, **self.auth(user))

    def post_new_semester(self, user, name="Even 2027"):
        return self.client.post(URL, {"name": name, "start_date": "2026-12-01",
                                      "end_date": "2027-04-30"},
                                content_type="application/json", **self.auth(user))

    def test_first_call_misses_then_hits_with_same_data(self):
        r1, r2 = self.get(self.student), self.get(self.student)
        self.assertEqual((r1["X-Cache"], r2["X-Cache"]), ("MISS", "HIT"))
        self.assertEqual(r1.json(), r2.json())
        self.assertEqual(r2.json()[0]["name"], "Odd 2026")

    def test_cache_hit_uses_fewer_queries(self):
        with CaptureQueriesContext(connection) as miss:
            self.get(self.student)
        with CaptureQueriesContext(connection) as hit:
            self.get(self.student)
        self.assertLess(len(hit), len(miss))
        # multi-college: the hit still runs the college lookup and the sign-in
        # checks (security phase), but never reads the cached data itself
        read = [q["sql"] for q in hit.captured_queries if any(t in q["sql"] for t in ['timetable_semester'])]
        self.assertEqual(read, [])

    def test_everyone_shares_one_cache_entry(self):
        self.get(self.student)
        self.assertEqual(self.get(self.admin)["X-Cache"], "HIT")

    def test_no_active_semester_is_cached_as_empty_list(self):
        Semester.objects.update(is_active=False)   # no signal; start from a clean cache
        cache.delete(shared_key("semester"))
        r1, r2 = self.get(self.student), self.get(self.student)
        self.assertEqual(r1.json(), [])
        self.assertEqual(r2["X-Cache"], "HIT")
        self.assertEqual(r2.json(), [])

    def test_admin_sets_new_semester_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.post_new_semester(self.admin)
        self.assertEqual(r.status_code, 201)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        names = [row["name"] for row in r.json()]
        self.assertEqual(names, ["Even 2027"])        # old one no longer active

    def test_change_outside_the_api_also_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):   # e.g. Django admin / shell
            self.sem.name = "Odd 2026 (renamed)"
            self.sem.save()
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(r.json()[0]["name"], "Odd 2026 (renamed)")

    def test_delete_clears_cache(self):
        self.get(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.sem.delete()
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "MISS")
        self.assertEqual(r.json(), [])

    def test_student_still_cannot_set_semester(self):
        self.get(self.student)
        r = self.post_new_semester(self.student)
        self.assertEqual(r.status_code, 403)
        r = self.get(self.student)
        self.assertEqual(r["X-Cache"], "HIT")          # nothing changed
        self.assertEqual(r.json()[0]["name"], "Odd 2026")