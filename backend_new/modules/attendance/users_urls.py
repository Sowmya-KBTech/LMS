# Attendance URLs that live under /api/users/ (kept there so the frontend
# does not change). config/urls.py loads this file BEFORE users.urls,
# because users.urls ends with a catch-all <pk>/ route.
from django.urls import path

from .od_views import (
    od_create, od_my_requests, od_cancel,
    tutor_od_pending, tutor_od_action,
    hod_od_pending, hod_od_action,
)
from .staff_leave_views import (
    staff_leave_create, staff_leave_my, staff_leave_detail, staff_leave_cancel,
    staff_leave_preview, staff_leave_proof, staff_leave_covering,
    hod_staff_leave_pending, hod_staff_leave_history,
    hod_staff_leave_on_leave_today, hod_staff_leave_action,
    principal_staff_leave_pending, principal_staff_leave_history,   # WAVE 2 Part 1b
    principal_staff_leave_action,
)
from .hod_views import hod_attendance
from . import student_leave_views as sl     # WAVE 1: student leave

urlpatterns = [
    path('hod-attendance/', hod_attendance),

    # ================= ON DUTY =================
    path('od/', od_my_requests),
    path('od/create/', od_create),
    path('od/<int:pk>/cancel/', od_cancel),
    path('tutor/od/', tutor_od_pending),
    path('tutor/od/<int:pk>/action/', tutor_od_action),
    path('hod/od/', hod_od_pending),
    path('hod/od/<int:pk>/action/', hod_od_action),

    # ================= STUDENT LEAVE (WAVE 1) =================
    path('leave/', sl.leave_my_requests),
    path('leave/create/', sl.leave_create),
    path('leave/<int:pk>/cancel/', sl.leave_cancel),
    path('tutor/leave/', sl.tutor_leave_pending),
    path('tutor/leave/<int:pk>/action/', sl.tutor_leave_action),
    path('hod/leave/', sl.hod_leave_pending),
    path('hod/leave/<int:pk>/action/', sl.hod_leave_action),

    # ================= STAFF LEAVE =================
    path('staff-leave/',                     staff_leave_my),
    path('staff-leave/create/',              staff_leave_create),
    path('staff-leave/preview/',             staff_leave_preview),
    path('staff-leave/covering/',            staff_leave_covering),
    path('staff-leave/<int:pk>/',            staff_leave_detail),
    path('staff-leave/<int:pk>/cancel/',     staff_leave_cancel),
    path('staff-leave/<int:pk>/proof/',      staff_leave_proof),
    path('hod/staff-leave/',                 hod_staff_leave_pending),
    path('hod/staff-leave/history/',         hod_staff_leave_history),
    path('hod/staff-leave/on-leave-today/',  hod_staff_leave_on_leave_today),
    path('hod/staff-leave/<int:pk>/action/', hod_staff_leave_action),
    # WAVE 2 Part 1b: the Principal decides an HOD's own leave
    path('principal/staff-leave/',                 principal_staff_leave_pending),
    path('principal/staff-leave/history/',         principal_staff_leave_history),
    path('principal/staff-leave/<int:pk>/action/', principal_staff_leave_action),
]
