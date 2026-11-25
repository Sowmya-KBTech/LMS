"""
Cache for lists that are the SAME for every user of a college
(time slots, the active semester, holidays ...).

  Key      : shared:<name>
             (stored as lms:<college>:shared:<name>, the prefix is added by
              config/cache_keys.py)
  Lifetime : SHARED_TIMEOUT seconds - only a safety net
  Cleared  : whenever the data changes, AFTER the database transaction
             commits, so the next request reads fresh data.

PostgreSQL stays the source of truth. If Redis is down, the list is simply
read from PostgreSQL as before.
"""
from django.core.cache import cache
from django.db import transaction

SHARED_TIMEOUT = 600  # seconds (10 minutes)


def shared_key(name):
    return f"shared:{name}"


def get_shared(name):
    return cache.get(shared_key(name))


def set_shared(name, data):
    cache.set(shared_key(name), data, SHARED_TIMEOUT)


def invalidate_shared(*names):
    """Clear these shared lists once the current database transaction commits."""
    keys = [shared_key(name) for name in names]
    transaction.on_commit(lambda: cache.delete_many(keys))