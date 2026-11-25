"""
PHASE 5 PART 4 - stop password guessing at the sign-in screens.

Wrong passwords are counted over the last 15 minutes (settings can change it):

  same username from the same computer (IP)    5 wrong  -> that pair waits
  same username from anywhere                 20 wrong  -> that username waits
  same computer (IP), any usernames          100 wrong  -> that IP waits

The wait ends by itself when the old attempts age out of the 15 minutes.
While blocked, the password is NOT checked at all, so guessing gets nothing.
A correct sign-in clears that username + IP's count.

Why three rules: one college lab shares one IP, so the IP limit is high; one
attacker using many IPs is stopped by the username limit.

Used by:  core/users/views.py login_view   (college sign-in)
          core/tenants/platform_views.py   (KB Technosoft platform sign-in)
"""
import math
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.security.models import LoginFailure


def _window():
    return timedelta(minutes=getattr(settings, "LOGIN_FAILURE_WINDOW_MINUTES", 15))


def _limits():
    return (getattr(settings, "LOGIN_LIMIT_PER_USER_AND_IP", 5),
            getattr(settings, "LOGIN_LIMIT_PER_USER", 20),
            getattr(settings, "LOGIN_LIMIT_PER_IP", 100))


def client_ip(request):
    """The caller's IP. Behind Nginx set TRUSTED_PROXY_COUNT=1 (Part 5), so the
    address Nginx saw is used and a faked X-Forwarded-For is ignored."""
    meta = getattr(request, "META", {})
    proxies = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if proxies > 0:
        chain = [p.strip() for p in meta.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if len(chain) >= proxies:
            return chain[-proxies][:64]
    return (meta.get("REMOTE_ADDR") or "")[:64]


def _key(username):
    return (username or "").strip().lower()[:150]


def seconds_blocked(username, ip):
    """0 = may try. Otherwise how many seconds until the next try is allowed."""
    now = timezone.now()
    window = _window()
    recent = LoginFailure.objects.filter(at__gte=now - window)
    user = _key(username)
    pair_limit, user_limit, ip_limit = _limits()
    checks = [(recent.filter(username=user, ip=ip), pair_limit),
              (recent.filter(username=user), user_limit)]
    if ip:
        checks.append((recent.filter(ip=ip), ip_limit))
    wait = 0.0
    for qs, limit in checks:
        times = list(qs.order_by("-at").values_list("at", flat=True)[:limit])
        if len(times) >= limit:
            wait = max(wait, (times[limit - 1] + window - now).total_seconds())
    return max(0, math.ceil(wait))


def record_failure(username, ip):
    LoginFailure.objects.create(username=_key(username), ip=ip)
    LoginFailure.objects.filter(at__lt=timezone.now() - timedelta(days=1)).delete()


def clear_failures(username, ip):
    LoginFailure.objects.filter(username=_key(username), ip=ip).delete()


def blocked_message(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many wrong passwords. Please wait {minutes} {unit} and try again."
