from django.urls import path

from . import views

# mounted at /api/accreditation/ (config/module_registry.py)
urlpatterns = [
    path("reports/", views.report_list),
    path("reports/<slug:key>/", views.report_detail),
    path("reports/<slug:key>/excel/", views.report_excel),
]
