"""
PHASE 5 PART 4 - make a sign-in token stop working when it should.

1. LOG OUT -> that token's id (jti) goes into RevokedToken and is refused at once
   (before: it kept working for up to 24 hours).
2. PASSWORD CHANGED -> every token carries "pv", a fingerprint of the password.
   A new password gives a new fingerprint, so EVERY older token on EVERY device
   is refused - whoever changed it, the person, the college admin or KB
   Technosoft. (The fingerprint is a keyed hash; the password cannot be read
   back from it.)
"""
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from django.utils.crypto import salted_hmac

from core.security.models import RevokedToken

PASSWORD_CLAIM = "pv"


def password_stamp(password_hash):
    return salted_hmac("kbtc.token.password", password_hash or "").hexdigest()[:16]


def stamp_matches(token, password_hash):
    return token.get(PASSWORD_CLAIM) == password_stamp(password_hash)


def is_revoked(token):
    jti = token.get("jti")
    return bool(jti) and RevokedToken.objects.filter(jti=jti).exists()


def revoke(token):
    """Sign this one token out. Also cleans up tokens that have expired anyway."""
    jti = token.get("jti")
    exp = token.get("exp")
    if not jti or not exp:
        return
    expires_at = datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)
    RevokedToken.objects.get_or_create(jti=jti, defaults={"expires_at": expires_at})
    RevokedToken.objects.filter(expires_at__lt=timezone.now()).delete()
