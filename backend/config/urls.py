from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [

    # ================= ADMIN =================
    path('admin/',admin.site.urls ),

    # ================= USERS APP =================
    path('api/users/',include('users.urls')),

    # ================= COURSES APP =================
    path('api/',include('courses.urls')),

    # ================= TIMETABLE APP =================
    path( 'api/',include('timetable.urls')),

    # ================= DRF LOGIN =================
    path('api-auth/',include('rest_framework.urls')),

    path('api/',include('attendance.urls')),

    path("api/", include("exams.urls")),
    path("api/", include("events.urls")),
    path("api/", include("teachingplan.urls")),

    # ================= MENTORING APP =================
    path("api/", include("mentoring.urls")),

    # ================= CLASS GROUPS APP =================
    path("api/", include("classgroups.urls")),
]

# ================= MEDIA FILES =================
if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )