"""
PHASE 3 - the college admin's "Payment settings" screen.

  GET    /api/payments/settings/        what is saved (never the secrets)
  PUT    /api/payments/settings/        save the Key ID / secrets
  DELETE /api/payments/settings/        remove the keys (switches online payment off)
  POST   /api/payments/settings/test/   check keys with Razorpay before relying on them
  GET    /api/payments/status/          any signed-in user: can this college take online payments?

Everything here runs inside ONE college's schema (the address decides which),
so a college admin can only ever see or change their own college's keys.
"""
import re

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from modules.fees.crypto import SecretUnreadable
from modules.fees.models import PaymentSettings
from modules.fees.payments import test_connection

KEY_ID_RULE = re.compile(r"^rzp_(test|live)_[A-Za-z0-9]{6,40}$")

# who may see or change this college's Razorpay keys
ALLOWED_SUB_ROLES = {None, "", "super_admin", "accounts_admin"}


def can_manage_payments(user):
    """The college's main admin, or its accounts admin. Not other admins, staff or students."""
    if user.is_superuser:
        return True
    return user.role == "admin" and (user.sub_role or "") in ALLOWED_SUB_ROLES


def _webhook_url(request):
    return request.build_absolute_uri("/api/payments/webhook/razorpay/")


def _describe(ps, request):
    """What the screen may show. The secrets themselves are never returned."""
    return {
        "configured": ps.is_configured,
        "mode": ps.mode,                          # "test", "live" or None
        "key_id": ps.key_id,                      # public anyway (checkout shows it)
        "has_key_secret": bool(ps.key_secret_encrypted),
        "has_webhook_secret": ps.has_webhook,
        "webhook_url": _webhook_url(request),
        "updated_by": ps.updated_by.username if ps.updated_by_id else None,
        "updated_at": ps.updated_at.isoformat() if ps.updated_at else None,
    }


def _forbidden():
    return Response(
        {"detail": "Only the college admin or the accounts admin can manage payment settings."},
        status=403)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def payment_settings(request):
    if not can_manage_payments(request.user):
        return _forbidden()

    ps = PaymentSettings.current()

    if request.method == "GET":
        return Response(_describe(ps, request))

    if request.method == "DELETE":
        PaymentSettings.objects.all().delete()
        return Response(_describe(PaymentSettings.current(), request))

    # ---------- PUT: save ----------
    key_id = (request.data.get("key_id") or "").strip()
    key_secret = (request.data.get("key_secret") or "").strip()
    webhook_secret = request.data.get("webhook_secret")   # None = leave as is

    if not KEY_ID_RULE.match(key_id):
        return Response(
            {"detail": "The Key ID should look like rzp_test_XXXXXXXX or rzp_live_XXXXXXXX."},
            status=400)

    # A new Key ID needs its own secret - an old secret belongs to the old key.
    if key_id != ps.key_id and not key_secret:
        return Response(
            {"detail": "Enter the Key Secret that belongs to this Key ID."}, status=400)
    if not key_secret and not ps.key_secret_encrypted:
        return Response({"detail": "Enter the Key Secret."}, status=400)

    ps.key_id = key_id
    if key_secret:                       # blank = keep the saved one
        ps.set_key_secret(key_secret)
    if webhook_secret is not None:
        webhook_secret = webhook_secret.strip()
        if webhook_secret:
            ps.set_webhook_secret(webhook_secret)
        elif request.data.get("clear_webhook_secret"):
            ps.webhook_secret_encrypted = ""
    ps.updated_by = request.user
    ps.save()
    return Response(_describe(ps, request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_settings_test(request):
    """
    Test keys with Razorpay. Sends the keys typed on the screen; a blank
    secret means "use the saved one", so a saved setup can be re-checked.
    """
    if not can_manage_payments(request.user):
        return _forbidden()

    ps = PaymentSettings.current()
    key_id = (request.data.get("key_id") or ps.key_id or "").strip()
    key_secret = (request.data.get("key_secret") or "").strip()

    if not KEY_ID_RULE.match(key_id):
        return Response(
            {"ok": False, "detail": "The Key ID should look like rzp_test_XXXXXXXX or rzp_live_XXXXXXXX."},
            status=400)
    if not key_secret:
        if key_id != ps.key_id or not ps.key_secret_encrypted:
            return Response({"ok": False, "detail": "Enter the Key Secret to test."}, status=400)
        try:
            key_secret = ps.key_secret
        except SecretUnreadable as exc:
            return Response({"ok": False, "detail": str(exc)}, status=400)

    ok, message = test_connection(key_id, key_secret)
    return Response({"ok": ok, "detail": message}, status=200 if ok else 400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request):
    """For the Pay screen: can this college take online payments right now?"""
    ps = PaymentSettings.current()
    return Response({"online_payments": ps.is_configured, "mode": ps.mode})
