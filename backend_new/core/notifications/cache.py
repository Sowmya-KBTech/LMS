"""
Redis cache for the notification bell:  GET /api/notifications/?unread=true

The frontend asks every 10 seconds per logged-in user. Instead of reading
PostgreSQL every time, we keep each user's unread list in the cache.

  Key      : notifications:unread:<user_id>
             (stored as lms:<college>:notifications:unread:<user_id>,
              the prefix is added by config/cache_keys.py)
  Lifetime : up to UNREAD_TIMEOUT seconds
  Cleared  : whenever that user's notifications change, AFTER the database
             transaction commits (so nobody caches data that was rolled back).

PostgreSQL stays the source of truth. If Redis is down, the bell simply
reads from PostgreSQL as before.
"""
from django.core.cache import cache
from django.db import transaction

UNREAD_TIMEOUT = 20  # seconds


def unread_key(user_id):
    return f"notifications:unread:{user_id}"


def get_unread(user_id):
    return cache.get(unread_key(user_id))


def set_unread(user_id, data):
    cache.set(unread_key(user_id), data, UNREAD_TIMEOUT)


def invalidate_unread(recipients):
    """
    Clear the cached bell list for these users once the current database
    transaction commits. `recipients` may contain users and/or user ids;
    None values are ignored.
    """
    ids = {getattr(r, "pk", r) for r in recipients if r is not None}
    ids.discard(None)
    if not ids:
        return
    keys = [unread_key(user_id) for user_id in ids]
    transaction.on_commit(lambda: cache.delete_many(keys))