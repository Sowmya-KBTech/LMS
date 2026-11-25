"""
SAAS PHASE 1 - URLs for the PLATFORM address (localhost, later
admin.kbtechcampus.in). College addresses use config/urls.py.

Only a status page for now; the platform console comes in Phase 6.
College data is never reachable from here: the public schema has none.
"""
from django.urls import path

from config.views import college_info, platform_status
from core.tenants import platform_views as pv

urlpatterns = [
    path("api/platform/status/", platform_status, name="platform-status"),
    # SAAS PHASE 2: lets the login page say "this is the platform address"
    path("api/college/", college_info, name="college-info"),

    # PLATFORM CONSOLE (KB Technosoft only)
    path("api/platform/login/", pv.platform_login, name="platform-login"),
    path("api/platform/logout/", pv.platform_logout, name="platform-logout"),   # PHASE 5 PART 4
    path("api/platform/me/", pv.platform_me, name="platform-me"),
    path("api/platform/colleges/", pv.platform_colleges, name="platform-colleges"),
    path("api/platform/colleges/<int:pk>/", pv.platform_college_detail, name="platform-college"),
    path("api/platform/colleges/<int:pk>/reset-admin-password/", pv.platform_reset_admin_password,
         name="platform-reset-admin-password"),
    # COLLEGE LOGO: GET is public (an <img> in the console); POST / DELETE need a platform login
    path("api/platform/colleges/<int:pk>/logo/", pv.platform_college_logo, name="platform-college-logo"),
]
