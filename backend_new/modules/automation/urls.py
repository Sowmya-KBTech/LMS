from django.urls import path

from .views import (
    automation_health, automation_preview, automation_runs, automation_settings, job_status,
)

# AUTOMATION SCREEN (Point 12, step 8)
urlpatterns = [
    path("automation/settings/", automation_settings),
    path("automation/runs/", automation_runs),
    path("automation/preview/", automation_preview),
    path("automation/health/", automation_health),          # STEP 8.4
    # STEP 6.2: background job status
    path("jobs/<uuid:job_id>/", job_status),
]