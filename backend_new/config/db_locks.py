"""
STEP 8.2: "only one at a time" locks kept by PostgreSQL itself.

    with advisory_lock("email_queue") as got:
        if not got:
            ...another run is still busy - skip...

The lock belongs to the database connection, so it is released automatically
if the process crashes. It does not depend on Redis (Redis errors are ignored
by the cache, so a Redis lock could silently fail and let two runs overlap).
"""
import hashlib
from contextlib import contextmanager

from django.db import connection


def _key(name):
    # one number per (college, name); fits PostgreSQL's signed 64-bit lock key.
    # The college is the current schema, so college A's nightly run never
    # blocks college B's (run_for_all_colleges runs them one after another).
    college = getattr(connection, "schema_name", "") or "public"
    digest = hashlib.sha1(f"{college}:{name}".encode()).hexdigest()
    return int(digest[:15], 16)


@contextmanager
def advisory_lock(name):
    if connection.vendor != "postgresql":      # e.g. SQLite in a quick local test
        yield True
        return
    key = _key(name)
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [key])
        got = cur.fetchone()[0]
    try:
        yield got
    finally:
        if got:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [key])