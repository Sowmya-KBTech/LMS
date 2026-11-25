"""
PHASE 5 PART 5 - refuse to start an UNSAFE production server.

settings.py calls check_production_settings() when DJANGO_ENV=production.
If anything below is wrong, the server stops at start-up with the full list
of problems - before any college data is served - instead of running with
DEBUG on or a guessable secret key.

On the laptop (DJANGO_ENV unset or "development") nothing here runs.
"""
from django.core.exceptions import ImproperlyConfigured

WEAK_SECRET_WORDS = ("insecure", "secret", "changeme", "change-me", "password",
                     "devsecret", "django", "example", "xxxx")


def _weak_secret(key):
    if len(key) < 50 or len(set(key)) < 10:
        return True
    lower = key.lower()
    return any(word in lower for word in WEAK_SECRET_WORDS)


def check_production_settings(s):
    """`s` is the settings module's globals(). Returns a list of problems."""
    problems = []

    if s.get("DEBUG"):
        problems.append("DJANGO_DEBUG must be False. Debug pages show code, settings and data.")

    key = s.get("SECRET_KEY") or ""
    if _weak_secret(key):
        problems.append(
            "DJANGO_SECRET_KEY is missing or weak. Make one with:\n"
            "      python -c \"from django.core.management.utils import get_random_secret_key; "
            "print(get_random_secret_key())\"")

    hosts = s.get("ALLOWED_HOSTS") or []
    if not hosts or "*" in hosts:
        problems.append("DJANGO_ALLOWED_HOSTS must list your domains, e.g. "
                        ".kbtechcampus.in,kbtechcampus.in (never *).")
    elif any("localhost" in h or h.startswith("127.") for h in hosts):
        problems.append("DJANGO_ALLOWED_HOSTS still contains localhost/127.0.0.1.")

    if not s.get("PAYMENT_ENCRYPTION_KEY"):
        problems.append(
            "PAYMENT_ENCRYPTION_KEY must be set. Without it the colleges' Razorpay secrets "
            "depend on DJANGO_SECRET_KEY and are lost if that is ever changed. Make one with:\n"
            "      python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"")

    origins = list(s.get("CORS_ALLOWED_ORIGINS") or []) + list(s.get("CORS_ALLOWED_ORIGIN_REGEXES") or [])
    if not origins:
        problems.append("DJANGO_CORS_ORIGIN_REGEXES must allow your college addresses, e.g. "
                        r"^https://([a-z0-9-]+\.)?kbtechcampus\.in$")
    elif any("localhost" in o or "http://" in o for o in origins):
        problems.append("CORS origins still allow localhost or plain http://. Use https:// addresses only.")

    if not s.get("SESSION_COOKIE_SECURE") or not s.get("CSRF_COOKIE_SECURE"):
        problems.append("Cookies must be HTTPS-only (DJANGO_SECURE_COOKIES=True).")

    db = (s.get("DATABASES") or {}).get("default", {})
    if not db.get("PASSWORD"):
        problems.append("DB_PASSWORD is empty.")

    return problems


def raise_if_unsafe(s):
    problems = check_production_settings(s)
    if problems:
        lines = "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
        raise ImproperlyConfigured(
            "DJANGO_ENV=production but the settings are not safe yet. Fix these in .env:\n" + lines)
