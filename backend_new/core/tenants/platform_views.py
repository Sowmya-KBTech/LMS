"""
PLATFORM CONSOLE - the API behind KB Technosoft's own screens.
Served ONLY on the platform address (config/urls_public.py).

  POST  /api/platform/login/                                  sign in
  POST  /api/platform/logout/                                 sign out (PHASE 5 PART 4)
  GET   /api/platform/me/                                     who am I
  GET   /api/platform/colleges/                               every college + totals
  POST  /api/platform/colleges/                               add a college
  GET   /api/platform/colleges/<id>/                          one college
  PATCH /api/platform/colleges/<id>/                          rename / switch on or off
  POST  /api/platform/colleges/<id>/reset-admin-password/     help a college admin sign in
  GET   /api/platform/colleges/<id>/logo/                     the college's logo (public image)
  POST / DELETE  same address                                 set or remove the logo
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.security import login_guard                                      # PHASE 5 PART 4
from core.security.tokens import revoke
from core.tenants.logos import LogoError, clean_logo
from core.tenants.models import College, CollegeLogo, PlatformAdmin
from core.tenants.platform_auth import IsPlatformAdmin, PlatformJWTAuthentication, platform_token_for
from core.tenants.services import CollegeError, college_summary, create_college

PLATFORM_AUTH = [PlatformJWTAuthentication]
PLATFORM_ONLY = [IsPlatformAdmin]


def _colleges():
    return College.objects.exclude(schema_name=get_public_schema_name()).order_by("id")


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def platform_login(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    # PHASE 5 PART 4: too many wrong passwords -> wait (password not even checked)
    ip = login_guard.client_ip(request)
    wait = login_guard.seconds_blocked(username, ip)
    if wait:
        return Response({"detail": login_guard.blocked_message(wait), "retry_after": wait},
                        status=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)})

    admin = PlatformAdmin.objects.filter(username=username, is_active=True).first()
    if not admin or not admin.check_password(password):
        login_guard.record_failure(username, ip)
        return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
    login_guard.clear_failures(username, ip)
    admin.last_login = timezone.now()
    admin.save(update_fields=["last_login"])
    return Response({"access": platform_token_for(admin), "username": admin.username})


@api_view(["POST"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes(PLATFORM_ONLY)
def platform_logout(request):
    """PHASE 5 PART 4: this platform token stops working now."""
    revoke(request.auth)
    return Response({"detail": "Signed out."})


@api_view(["GET"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes(PLATFORM_ONLY)
def platform_me(request):
    return Response({"username": request.user.username, "email": request.user.email})


@api_view(["GET", "POST"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes(PLATFORM_ONLY)
def platform_colleges(request):
    if request.method == "GET":
        return Response([college_summary(c) for c in _colleges()])

    d = request.data
    try:
        college = create_college(
            code=d.get("code"),
            name=d.get("name"),
            domain=d.get("domain") or None,
            admin_username=(d.get("admin_username") or "").strip() or None,
            admin_password=d.get("admin_password") or None,
            admin_email=(d.get("admin_email") or "").strip(),
        )
    except CollegeError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(college_summary(college), status=status.HTTP_201_CREATED)


def _get_college(pk):
    return _colleges().filter(pk=pk).first()


@api_view(["GET", "PATCH"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes(PLATFORM_ONLY)
def platform_college_detail(request, pk):
    college = _get_college(pk)
    if college is None:
        return Response({"detail": "College not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        fields = []
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                return Response({"detail": "College name cannot be empty."}, status=400)
            college.name = name
            fields.append("name")
        if "is_active" in request.data:
            college.is_active = bool(request.data.get("is_active"))
            fields.append("is_active")
        if fields:
            college.save(update_fields=fields)
    return Response(college_summary(college))


@api_view(["POST"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes(PLATFORM_ONLY)
def platform_reset_admin_password(request, pk):
    """Set a new password for one of the college's ADMINS (never a student or teacher)."""
    college = _get_college(pk)
    if college is None:
        return Response({"detail": "College not found."}, status=status.HTTP_404_NOT_FOUND)

    username = (request.data.get("username") or "").strip()
    new_password = request.data.get("new_password") or ""
    try:
        validate_password(new_password)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)

    User = get_user_model()
    with schema_context(college.schema_name):
        user = User.objects.filter(username=username).first()
        if user is None or not (user.is_superuser or user.role == "admin"):
            return Response({"detail": "No admin with that username in this college."}, status=404)
        user.set_password(new_password)
        user.must_change_password = True       # they choose their own at next sign-in
        user.save(update_fields=["password", "must_change_password"])
    return Response({"detail": f"Password reset for {username}. They will be asked to change it at sign-in."})


class IsPlatformAdminOrReadOnly(IsPlatformAdmin):
    """Anyone may LOOK at a logo; only KB Technosoft may change it."""

    def has_permission(self, request, view):
        return request.method == "GET" or super().has_permission(request, view)


@api_view(["GET", "POST", "DELETE"])
@authentication_classes(PLATFORM_AUTH)
@permission_classes([IsPlatformAdminOrReadOnly])
def platform_college_logo(request, pk):
    """COLLEGE LOGO - shown on the college's login page."""
    college = _get_college(pk)
    if college is None:
        return Response({"detail": "College not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        from config.views import logo_response
        return logo_response(college)

    if request.method == "DELETE":
        CollegeLogo.objects.filter(college=college).delete()
        return Response(college_summary(college))

    try:
        png = clean_logo(request.FILES.get("logo"))
    except LogoError as exc:
        return Response({"detail": str(exc)}, status=400)
    CollegeLogo.objects.update_or_create(college=college, defaults={"image": png, "content_type": "image/png"})
    return Response(college_summary(college))

