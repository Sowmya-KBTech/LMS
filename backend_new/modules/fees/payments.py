"""
The only file in the project that talks to Razorpay.

Everything else - views, signals, admin - calls the functions here. If the
product ever needs a second gateway (some colleges will insist on their
bank's own), this is the file that changes and nothing else does.

PHASE 3 - every function uses THIS college's own Razorpay keys
(PaymentSettings, stored in the college's schema), never one global set from
.env. The college comes from the address the request arrived at, so a payment
at abc.kbtechcampus.in always goes to ABC's Razorpay account.
"""

import hashlib
import hmac
from decimal import Decimal

import razorpay


NOT_CONFIGURED_MESSAGE = (
    "Online payment isn't set up for this college yet. "
    "Please contact the college office."
)


class PaymentsNotConfigured(Exception):
    """This college has not saved its Razorpay keys yet (or they can't be read)."""

    def __init__(self, message=NOT_CONFIGURED_MESSAGE):
        super().__init__(message)


class GatewayError(Exception):
    """Razorpay refused the request or could not be reached."""


def college_keys():
    """
    (key_id, key_secret) of the college this request belongs to.
    Raises PaymentsNotConfigured when the college has not set them.
    """
    from modules.fees.crypto import SecretUnreadable
    from modules.fees.models import PaymentSettings

    ps = PaymentSettings.current()
    if not ps.is_configured:
        raise PaymentsNotConfigured()
    try:
        return ps.key_id, ps.key_secret
    except SecretUnreadable as exc:
        raise PaymentsNotConfigured(str(exc))


def get_client(key_id=None, key_secret=None):
    """A Razorpay client for this college (or for the keys given)."""
    if key_id is None:
        key_id, key_secret = college_keys()
    return razorpay.Client(auth=(key_id, key_secret))


def public_key_id():
    """The Key ID the checkout popup needs. Public - the secret never leaves the server."""
    return college_keys()[0]


def to_paise(amount_in_rupees):
    """
    Razorpay counts in paise, the database counts in rupees.

    The conversion happens here and nowhere else, so there is exactly one
    place where money changes representation. 45000.50 -> 4500050.
    """
    return int(Decimal(str(amount_in_rupees)) * 100)


def create_order(amount_in_rupees, receipt):
    """
    Ask Razorpay to open an order in THIS college's account and return it.

    'receipt' is our own reference so a Razorpay order can be traced back
    to a row in our database.
    Raises PaymentsNotConfigured or GatewayError.
    """
    client = get_client()
    try:
        return client.order.create({
            "amount": to_paise(amount_in_rupees),
            "currency": "INR",
            "receipt": str(receipt),
            "payment_capture": 1,
        })
    except razorpay.errors.BadRequestError as exc:
        raise GatewayError(f"Razorpay refused the payment: {exc}")
    except Exception:
        raise GatewayError("Could not reach the payment gateway. Please try again in a minute.")


def test_connection(key_id, key_secret):
    """
    Check a pair of keys with Razorpay before the college relies on them.
    Returns (ok, message). Makes one harmless read-only call (list 1 order).
    """
    try:
        razorpay.Client(auth=(key_id, key_secret)).order.all({"count": 1})
        return True, "Razorpay accepted these keys."
    except razorpay.errors.BadRequestError:
        return False, "Razorpay rejected these keys. Check the Key ID and Key Secret."
    except Exception:
        return False, "Could not reach Razorpay. Check the internet connection and try again."


def verify_payment_signature(order_id, payment_id, signature):
    """
    Check the signature the browser sent back after checkout.

    Razorpay signs 'order_id|payment_id' with THIS college's key secret.
    Anyone can POST to our verify endpoint claiming a payment succeeded;
    only Razorpay can produce a signature that matches. Returns True or
    False - never raises, so callers can treat a bad signature (or a
    college with no keys) as an ordinary rejection.
    """
    try:
        _, key_secret = college_keys()
    except PaymentsNotConfigured:
        return False

    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        key_secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()

    # compare_digest, not ==, so the comparison takes the same time whether
    # the signature is wrong at the first character or the last
    return hmac.compare_digest(expected, signature or "")


def webhook_secret():
    """This college's webhook secret, or '' when not set."""
    from modules.fees.crypto import SecretUnreadable
    from modules.fees.models import PaymentSettings

    try:
        return PaymentSettings.current().webhook_secret
    except SecretUnreadable:
        return ""


def verify_webhook_signature(raw_body, signature):
    """
    Check a webhook sent by Razorpay directly to our server.

    Different secret from the one above, because this proves a different
    thing: not 'the student really paid' but 'this message really came
    from Razorpay'. Each college's webhook URL is on its own address
    (abc.kbtechcampus.in/...), so this is checked with THAT college's secret.

    raw_body must be the exact bytes received. Re-encoding the parsed JSON
    changes whitespace and key order, and the hash then never matches.
    """
    secret = webhook_secret()
    if not secret:
        return False

    expected = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature or "")
