"""
Cache key rules for KB Tech Campus (from the Redis/Celery work, made
multi-college).

Every cache key (Redis or the in-memory fallback) looks like:

    lms:<college>:<key>          e.g.  lms:abc:notifications:unread:101

<college> is the schema of the college this request (or background job) is
working in, so user 101 of one college never gets user 101 of another
college's cached data. Outside any college (the platform pages) it is
"platform".
"""
from django.db import connection


def college_code():
    """Which college this cache entry belongs to: the current schema."""
    from django_tenants.utils import get_public_schema_name
    schema = getattr(connection, "schema_name", "") or ""
    if not schema or schema == get_public_schema_name():
        return "platform"
    return schema


def make_key(key, key_prefix, version):
    """Django calls this to build every cache key (KEY_FUNCTION)."""
    base = f"lms:{college_code()}:{key}"
    if int(version) == 1:
        return base
    return f"{base}:v{version}"
