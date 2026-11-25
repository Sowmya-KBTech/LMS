"""
SAAS PHASE 1 - a login token belongs to ONE college.

Every college has its own users table, so user id 1 exists in ABC AND in XYZ.
A plain JWT says only "user 1", so ABC's token would be accepted at XYZ as
XYZ's user 1. Two pieces stop that:

  TenantRefreshToken      - adds "tenant": <schema> to every token at login
                            (the access token copies it from the refresh token)
  TenantJWTAuthentication - refuses a token whose "tenant" is not the college
                            of the address the request came to

PHASE 5 PART 4 - a token also stops working when it should:
  * signed out (POST /api/users/logout/)       -> refused at once
  * password changed, by anyone, any device    -> every older token refused
  (see core/security/tokens.py)
"""
from django.db import connection
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.security.tokens import PASSWORD_CLAIM, is_revoked, password_stamp, stamp_matches

TENANT_CLAIM = "tenant"


class TenantRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token[TENANT_CLAIM] = connection.schema_name
        token[PASSWORD_CLAIM] = password_stamp(user.password)     # PHASE 5 PART 4
        return token


class TenantJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if token.get(TENANT_CLAIM) != connection.schema_name:
            raise InvalidToken("This login belongs to a different college. Please sign in here.")
        if is_revoked(token):                                      # PHASE 5 PART 4
            raise AuthenticationFailed("You have signed out. Please sign in again.",
                                       code="signed_out")
        return token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not stamp_matches(validated_token, user.password):      # PHASE 5 PART 4
            raise AuthenticationFailed("Your password was changed. Please sign in again.",
                                       code="password_changed")
        return user
