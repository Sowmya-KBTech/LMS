from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from config.module_registry import MODULES
from config.views import college_info, college_logo, enabled_modules
from core.tenants.media import college_media   # PHASE 4: files per college

urlpatterns = [

    # ================= ADMIN =================
    path(settings.ADMIN_URL, admin.site.urls),        # PHASE 5 PART 5: address set in .env

    # ================= DRF LOGIN =================
    path('api-auth/', include('rest_framework.urls')),

    # ================= MODULE LIST (for the frontend) =================
    path('api/modules/', enabled_modules, name='enabled-modules'),

    # ================= WHICH COLLEGE IS THIS ADDRESS (SAAS PHASE 2) =================
    path('api/college/', college_info, name='college-info'),
    path('api/college/logo/', college_logo, name='college-logo'),   # shown on the login page
]

# ================= MODULE URLS =================
# Only modules switched on in ENABLED_MODULES are loaded; a module that is
# off simply has no URLs (404). "early_urls" go first because users.urls
# ends with a catch-all <pk>/ route under /api/users/.
for name in settings.ENABLED_MODULES:
    for prefix, urls_module in MODULES[name].get("early_urls", []):
        urlpatterns.append(path(prefix, include(urls_module)))

for name in settings.ENABLED_MODULES:
    for prefix, urls_module in MODULES[name]["urls"]:
        urlpatterns.append(path(prefix, include(urls_module)))

# ================= MEDIA FILES (PHASE 4) =================
# Every uploaded file is served through college_media, in development AND on
# the server: only this college's folder, only to someone signed in here.
# (The old static() served every college's files to anyone, and only in DEBUG.)
urlpatterns += [
    re_path(r"^media/(?P<path>.+)$", college_media, name="college-media"),
]
