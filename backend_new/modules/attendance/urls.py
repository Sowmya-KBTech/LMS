from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AttendanceViewSet
from .correction_views import correction_day, attendance_corrections, late_entry   # #43 Change 2, #46


router = DefaultRouter()

router.register(
    r'attendance',
    AttendanceViewSet,
    basename='attendance'
)

urlpatterns = router.urls + [
    # ATTENDANCE CORRECTION (#43 Change 2): class tutor corrects past attendance
    path('attendance-corrections/day/', correction_day),
    path('attendance-corrections/', attendance_corrections),
    # #46 Part 3: class tutor enters a period that was never marked
    path('attendance-corrections/late-entry/', late_entry),
]