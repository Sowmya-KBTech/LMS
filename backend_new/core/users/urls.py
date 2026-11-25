from rest_framework.routers import DefaultRouter

from django.urls import path

from . import hris, hris_b   # HRIS PART A / B

from .views import (
    UserViewSet,
    DepartmentViewSet,
    login_view,
    admin_dashboard,
    change_password,
    logout_view,          # PHASE 5 PART 4
    student_template,
    student_import,
    promote_students,
    my_department,
    hod_class_performance,
    hod_tutor_overview,
    hod_tutor_grid,
    hod_assign_tutor,
    hod_remove_tutor,
    my_class,
    tutor_student_report,
    participation_create,
    participation_my,
    participation_delete,
    iqac_participation_list,
    iqac_participation_summary,
    iqac_academic_quality,
    hod_allocation_subjects,
    hod_allocate,
)

# WAVE 2: PRINCIPAL
from .principal_views import (
    principal_assign, principal_candidates, principal_dashboard, principal_end, principal_info,
)

# #50 ACTING HOD
from .acting_hod_views import (
    acting_hod_list,
    acting_hod_candidates,
    acting_hod_extend,
    acting_hod_end,
    acting_hod_approve,
    acting_hod_reject,
    acting_hod_me,
)

router = DefaultRouter()

router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'', UserViewSet, basename='user')

# OD, staff leave, HOD attendance/results and the marksheet moved to the
# attendance and exams modules (attendance/users_urls.py, exams/users_urls.py).
# Their URLs are unchanged.

urlpatterns = [

    path('login/', login_view),
    path('admin-dashboard/', admin_dashboard),
    path('change-password/', change_password),
    path('logout/', logout_view),                    # PHASE 5 PART 4
    path('student-template/', student_template),
    path('student-import/', student_import),
    path('promote-students/', promote_students),
    path('my-department/', my_department),
    path('hod-class-performance/', hod_class_performance),

    # ================= HOD TUTOR =================
    path('hod-tutor-overview/', hod_tutor_overview),
    path('hod-tutor-grid/<int:course_id>/', hod_tutor_grid),
    path('hod-assign-tutor/', hod_assign_tutor),
    path('hod-remove-tutor/<int:tutor_id>/', hod_remove_tutor),

    # ================= HOD FACULTY ALLOCATION =================
    path('hod/allocation/', hod_allocation_subjects),
    path('hod/allocate/', hod_allocate),

    # ================= CLASS ADVISOR =================
    path('my-class/', my_class),
    path('my-class/student/<int:student_id>/report/', tutor_student_report),

    # ================= FACULTY PARTICIPATION (IQAC) =================
    path('participation/', participation_my),
    path('participation/add/', participation_create),
    path('participation/<int:pk>/delete/', participation_delete),
    path('iqac/participation/', iqac_participation_list),
    path('iqac/participation/summary/', iqac_participation_summary),

    # ================= IQAC ACADEMIC QUALITY =================
    path('iqac/academic-quality/', iqac_academic_quality),

    # ================= ACTING HOD (#50) =================
    # WAVE 2: PRINCIPAL
    path('principal/', principal_info),
    path('principal/candidates/', principal_candidates),
    path('principal/assign/', principal_assign),
    path('principal/end/', principal_end),
    path('principal/dashboard/', principal_dashboard),

    # HRIS PART B: achievements verification and the yearly appraisal
    path('achievements/review/', hris_b.achievements_review),
    path('achievements/<int:pk>/review/', hris_b.achievement_review),
    path('achievements/<int:pk>/', hris_b.achievement_edit),
    path('appraisal/cycles/', hris_b.cycles),
    path('appraisal/cycles/<int:pk>/', hris_b.cycle_edit),
    path('appraisal/mine/', hris_b.mine),
    path('appraisal/list/', hris_b.appraisal_list),
    path('appraisal/export/', hris_b.appraisal_export),
    path('appraisal/<int:pk>/', hris_b.one),
    path('appraisal/<int:pk>/self/', hris_b.self_step),
    path('appraisal/<int:pk>/hod/', hris_b.hod_step),
    path('appraisal/<int:pk>/principal/', hris_b.principal_step),
    path('appraisal/<int:pk>/reply/', hris_b.reply_step),

    # HRIS PART A
    path('hris/staff/', hris.staff_directory),
    path('hris/staff/<int:pk>/', hris.staff_record),
    path('hris/staff/<int:pk>/service/', hris.service_add),
    path('hris/staff/<int:pk>/documents/', hris.document_add),
    path('hris/staff/<int:pk>/leave-adjust/', hris.leave_adjust),
    path('hris/service/<int:pk>/', hris.service_delete),
    path('hris/documents/<int:pk>/', hris.document_delete),
    path('hris/leave-rules/', hris.leave_rules),
    path('hris/leave-balance/', hris.leave_balance),
    path('hris/reports/<slug:key>/', hris.staff_report),

    path('acting-hod/', acting_hod_list),
    path('acting-hod/me/', acting_hod_me),
    path('acting-hod/candidates/', acting_hod_candidates),
    path('acting-hod/<int:pk>/extend/', acting_hod_extend),
    path('acting-hod/<int:pk>/end/', acting_hod_end),
    path('acting-hod/<int:pk>/approve/', acting_hod_approve),
    path('acting-hod/<int:pk>/reject/', acting_hod_reject),
]

# Router goes last: it registers r'' (the UserViewSet), whose
# <pk>/ pattern would otherwise catch the explicit paths above.
urlpatterns += router.urls