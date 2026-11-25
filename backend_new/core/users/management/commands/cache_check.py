"""
python manage.py cache_check

Checks that the cache works and shows which one is in use:
  - Redis                     (REDIS_URL set in .env)
  - In-memory, Redis off      (REDIS_URL empty)
"""
import uuid

from django.conf import settings
from django.core.cache import cache

from config.cache_keys import college_code
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check that the cache (Redis or the in-memory fallback) is working."

    def handle(self, *args, **options):
        backend = settings.CACHES["default"]["BACKEND"]
        using_redis = "redis" in backend.lower()

        self.stdout.write(f"Cache backend : {'Redis' if using_redis else 'In-memory (Redis off)'}")
        if using_redis:
            self.stdout.write(f"Redis URL     : {settings.REDIS_URL}")
        self.stdout.write(f"College       : {college_code()}")

        key = "healthcheck"
        self.stdout.write(f"Key format    : {cache.make_key(key)}")

        token = uuid.uuid4().hex
        cache.set(key, token, timeout=30)
        ok = cache.get(key) == token
        cache.delete(key)

        if ok:
            self.stdout.write(self.style.SUCCESS("Cache check   : OK"))
            return

        hint = ""
        if using_redis:
            hint = (" Is Docker Desktop running? Start Redis with:"
                    " docker start kbtech-redis")
        raise CommandError("Cache check   : FAILED - value could not be read back." + hint)