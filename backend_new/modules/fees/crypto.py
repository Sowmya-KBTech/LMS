"""
PHASE 3 - encrypting each college's Razorpay secrets.

The Key Secret and Webhook Secret are stored ENCRYPTED in the college's own
schema, so someone who reads the database (a backup, a support query) still
cannot use them. Only this server, holding the encryption key, can read them.

The encryption key comes from:
  1. PAYMENT_ENCRYPTION_KEY in .env, if set (recommended on the server); or
  2. a key derived from DJANGO_SECRET_KEY (fine on a laptop).

IMPORTANT: if that key changes, saved secrets can no longer be read. The
college admin then simply enters the Razorpay keys again - nothing else breaks.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SecretUnreadable(Exception):
    """The stored secret was encrypted with a different key."""


def _fernet():
    configured = getattr(settings, "PAYMENT_ENCRYPTION_KEY", "") or ""
    if configured:
        key = configured.encode()
    else:
        digest = hashlib.sha256(("kbtc-payments:" + settings.SECRET_KEY).encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plain):
    """'' stays '' so 'not set' is easy to see."""
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise SecretUnreadable(
            "The saved Razorpay secret can't be read on this server. "
            "Please enter the Razorpay keys again in Payment settings.")
