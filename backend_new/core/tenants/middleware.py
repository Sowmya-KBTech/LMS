"""
PLATFORM CONSOLE - a switched-off college is really switched off.

When KB Technosoft switches a college off (College.is_active = False), every
request to that college's address is refused, so its users cannot sign in or
use the app. Its data is kept untouched. /api/college/ still answers, so the
login page can explain what happened.

Placed after TenantMainMiddleware (which sets request.tenant) and after
CorsMiddleware (so the browser can read the message).
"""
from django.http import JsonResponse
from django_tenants.utils import get_public_schema_name

ALWAYS_ALLOWED = ("/api/college/",)


class InactiveCollegeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        college = getattr(request, "tenant", None)
        if (college is not None
                and college.schema_name != get_public_schema_name()
                and not college.is_active
                and not request.path.startswith(ALWAYS_ALLOWED)):
            return JsonResponse(
                {"detail": "This college's access is switched off. Please contact KB Technosoft."},
                status=403)
        return self.get_response(request)
