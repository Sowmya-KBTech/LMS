# backend/config/views.py
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from config.module_registry import MODULES


@api_view(["GET"])
@permission_classes([AllowAny])
def enabled_modules(request):
    """
    GET /api/modules/
    Tells the frontend which modules this college has,
    so it can hide menus / hubs for modules that are off.
    """
    return Response({
        "enabled": settings.ENABLED_MODULES,
        "modules": [
            {
                "name": name,
                "label": info["label"],
                "core": info["core"],
                "enabled": name in settings.ENABLED_MODULES,
            }
            for name, info in MODULES.items()
        ],
    })


@api_view(["GET"])
@authentication_classes([])      # works before sign-in, on any address
@permission_classes([AllowAny])
def college_info(request):
    """
    SAAS PHASE 2 - GET /api/college/
    Tells the frontend which college this address belongs to, so the login
    page can show its name. On the platform address it says so, and the login
    page asks the user to open their college's address instead.
    """
    from django_tenants.utils import get_public_schema_name

    college = request.tenant
    if college.schema_name == get_public_schema_name():
        return Response({"platform": True, "name": college.name})
    # "active": False when KB Technosoft has switched the college off
    # "logo_version": None = no logo; otherwise load GET /api/college/logo/?v=<it>
    return Response({"platform": False, "name": college.name, "code": college.schema_name,
                     "active": college.is_active, "logo_version": _logo_version(college)})


def _logo_version(college):
    from core.tenants.services import _logo_version as version
    return version(college)


def logo_response(college):
    """The college's logo image (or 404). Public: it is shown before sign-in."""
    from django.http import HttpResponse, JsonResponse
    from core.tenants.models import CollegeLogo
    logo = CollegeLogo.objects.filter(college=college).first()
    if logo is None:
        return JsonResponse({"detail": "No logo."}, status=404)
    response = HttpResponse(bytes(logo.image), content_type=logo.content_type)
    response["Cache-Control"] = "public, max-age=86400"       # ?v= changes when it changes
    response["X-Content-Type-Options"] = "nosniff"
    return response


def college_logo(request):
    """GET /api/college/logo/ on a college's address - its logo for the login page."""
    from django.http import JsonResponse
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    return logo_response(request.tenant)


@api_view(["GET"])
@authentication_classes([])      # the public schema has no users table to check a token against
@permission_classes([AllowAny])
def platform_status(request):
    """
    SAAS PHASE 1 - GET /api/platform/status/ on the platform address.
    Confirms the platform is up. Shows no college names or data.
    """
    return Response({"platform": "KB Tech Campus", "status": "ok"})
