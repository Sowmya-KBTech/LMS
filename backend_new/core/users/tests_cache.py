"""Tests for the cache setup (works with Redis on or off), multi-college."""
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase
from django_tenants.utils import schema_context


class CacheKeyTests(SimpleTestCase):

    def test_key_has_lms_and_college_prefix(self):
        # the tests run inside the college whose schema is "test"
        self.assertEqual(cache.make_key("notification_count:101"),
                         "lms:test:notification_count:101")

    def test_college_is_part_of_the_key(self):
        with schema_context("abc"):
            self.assertEqual(cache.make_key("notification_count:101"),
                             "lms:abc:notification_count:101")

    def test_outside_any_college_the_key_says_platform(self):
        with schema_context("public"):
            self.assertEqual(cache.make_key("x"), "lms:platform:x")

    def test_version_is_added_only_when_not_1(self):
        self.assertEqual(cache.make_key("x", version=2), "lms:test:x:v2")

    def test_two_colleges_never_share_a_value(self):
        with schema_context("college_a"):
            cache.set("tests_cache:same_name", "A", timeout=30)
        with schema_context("college_b"):
            self.assertIsNone(cache.get("tests_cache:same_name"))
        with schema_context("college_a"):
            self.assertEqual(cache.get("tests_cache:same_name"), "A")
            cache.delete("tests_cache:same_name")

    def test_set_get_delete_roundtrip(self):
        cache.set("tests_cache:roundtrip", {"a": 1}, timeout=30)
        self.assertEqual(cache.get("tests_cache:roundtrip"), {"a": 1})
        cache.delete("tests_cache:roundtrip")
        self.assertIsNone(cache.get("tests_cache:roundtrip"))

    def test_cache_check_command_passes(self):
        out = StringIO()
        call_command("cache_check", stdout=out)
        self.assertIn("Cache check   : OK", out.getvalue())
