"""GET /api/semester/all/ - every semester, newest first (parent "previous semesters")."""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from core.users.models import User
from modules.timetable.models import Semester


class SemesterAllTests(TestCase):

    def setUp(self):
        Semester.objects.create(name="Odd 2025", start_date=datetime.date(2025, 7, 1),
                                end_date=datetime.date(2025, 11, 30), is_active=False)
        Semester.objects.create(name="Even 2026", start_date=datetime.date(2026, 1, 5),
                                end_date=datetime.date(2026, 5, 30), is_active=False)
        Semester.objects.create(name="Odd 2026", start_date=datetime.date(2026, 7, 1),
                                end_date=datetime.date(2026, 11, 30), is_active=True)
        self.parent = User.objects.create_user(username="sa_p", password="x", role="parent")
        self.client = APIClient()

    def test_lists_all_semesters_newest_first(self):
        self.client.force_authenticate(user=self.parent)
        r = self.client.get("/api/semester/all/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([s["name"] for s in r.json()], ["Odd 2026", "Even 2026", "Odd 2025"])
        self.assertEqual([s["is_active"] for s in r.json()], [True, False, False])
        self.assertEqual(r.json()[0]["start_date"], "2026-07-01")

    def test_read_only(self):
        self.client.force_authenticate(user=self.parent)
        r = self.client.post("/api/semester/all/", {"name": "x"}, format="json")
        self.assertEqual(r.status_code, 405)

    def test_needs_login(self):
        self.assertEqual(self.client.get("/api/semester/all/").status_code, 401)

    def test_active_semester_endpoint_unchanged(self):
        self.client.force_authenticate(user=self.parent)
        r = self.client.get("/api/semester/")
        self.assertEqual([s["name"] for s in r.json()], ["Odd 2026"])