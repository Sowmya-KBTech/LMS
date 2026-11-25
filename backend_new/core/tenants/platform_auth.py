"""
PLATFORM CONSOLE - signing in as KB Technosoft.

A platform token is marked  scope="platform", tenant="public".
  * PlatformJWTAuthentication accepts ONLY such tokens, ONLY on the platform
    address - a college's token is refused here.
  * core.tenants.jwt.TenantJWTAuthentication already refuses it at every
    college address (its tenant is "public", not the college).
  PHASE 5 PART 4: sign-out and a password change end it at once, and wrong
  passwords are limited (core/security/).
"""
from django.db import connection
from django_tenants.utils import get_public_schema_name
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from core.security.tokens import PASSWORD_CLAIM, is_revoked, password_stamp, stamp_matches
from core.tenants.models import PlatformAdmin

PLATFORM_SCOPE = "platform"


def platform_token_for(admin):
    token = AccessToken()
    token["scope"] = PLATFORM_SCOPE
    token["tenant"] = get_public_schema_name()
    token["platform_admin_id"] = admin.id
    token[PASSWORD_CLAIM] = password_stamp(admin.password)     # PHASE 5 PART 4
    return str(token)


class PlatformJWTAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid sign-in header.")
        try:
            token = AccessToken(parts[1].decode())
        except (TokenError, UnicodeDecodeError):
            raise AuthenticationFailed("Your platform session has expired. Please sign in again.")

        if (connection.schema_name != get_public_schema_name()
                or token.get("scope") != PLATFORM_SCOPE):
            raise AuthenticationFailed("This is not a KB Technosoft platform login.")

        admin = PlatformAdmin.objects.filter(id=token.get("platform_admin_id"), is_active=True).first()
        if admin is None:
            raise AuthenticationFailed("This platform account is not active.")
        # PHASE 5 PART 4: signed out, or the password changed since this token
        if is_revoked(token):
            raise AuthenticationFailed("You have signed out. Please sign in again.")
        if not stamp_matches(token, admin.password):
            raise AuthenticationFailed("Your password was changed. Please sign in again.")
        return admin, token

    def authenticate_header(self, request):
        return 'Bearer realm="platform"'


class IsPlatformAdmin(BasePermission):
    message = "Only a KB Technosoft platform admin can do this."

    def has_permission(self, request, view):
        return isinstance(request.user, PlatformAdmin)
