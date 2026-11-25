# backend/teaching_plans/urls.py
from rest_framework.routers import DefaultRouter
from .views import CourseOutcomeViewSet, TeachingPlanViewSet

router = DefaultRouter()
router.register(r"teaching-plans", TeachingPlanViewSet, basename="teaching-plans")
router.register(r"course-outcomes", CourseOutcomeViewSet, basename="course-outcomes")  # COURSE PLAN (Part B)

from django.urls import path
from . import outcomes   # CO-PO PART A

urlpatterns = router.urls + [
    # ===== CO-PO PART A =====
    path("outcomes/programme/", outcomes.programme_outcomes),
    path("outcomes/programme/standard/", outcomes.programme_outcomes_standard),
    path("outcomes/programme/<int:pk>/", outcomes.programme_outcome_detail),
    path("outcomes/subjects/", outcomes.mapping_subjects),
    path("outcomes/mapping/<int:subject_id>/", outcomes.mapping_detail),
    path("outcomes/rules/", outcomes.attainment_rules),
]