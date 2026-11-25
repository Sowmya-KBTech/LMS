# Academics (core): courses, years, subjects, teaching assignments,
# enrollments, dashboards, electives, parent accounts.
from rest_framework.routers import DefaultRouter
from django.urls import path, include

from .views import (
    teacher_dashboard,
    admin_dashboard,
    parent_dashboard,
    generate_enrollments,
    my_electives,
    elective_enroll,
    CourseViewSet,
    YearViewSet,
    SubjectViewSet,
    TeachingAssignmentViewSet,
    EnrollmentViewSet,
    manage_parents,
    update_parent_children,
)
from . import views_electives as ev
from . import course_registration as cr   # CBCS PART A
from . import views_regulations as rv     # WAVE 3 PART 1A (CBCS)

router = DefaultRouter()
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'years', YearViewSet, basename='year')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'teaching-assignments', TeachingAssignmentViewSet, basename='ta')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')

urlpatterns = [
    # ================= DASHBOARDS =================
    path('admin-dashboard/', admin_dashboard),
    path('teacher-dashboard/', teacher_dashboard),
    path('parent/dashboard/', parent_dashboard),

    # ================= ENROLLMENTS / ELECTIVES =================
    path('generate-enrollments/', generate_enrollments),
    path('my-electives/', my_electives),
    path('elective-enroll/', elective_enroll),

    # ================= ELECTIVES (meeting point 9) =================
    path('electives/setting/', ev.elective_setting),
    path('electives/groups/', ev.group_list),
    path('electives/groups/<int:pk>/', ev.group_detail),
    path('electives/groups/<int:pk>/available/', ev.group_available),
    path('electives/groups/<int:pk>/options/', ev.group_add_option),
    path('electives/groups/<int:pk>/students/', ev.group_students),
    path('electives/groups/<int:pk>/changes/', ev.group_changes),
    path('electives/options/<int:pk>/', ev.option_detail),
    path('electives/options/<int:pk>/assign-class/', ev.option_assign_class),
    path('electives/options/<int:pk>/prerequisites/', ev.option_prerequisite_choices),   # CBCS PART B
    path('electives/allocate/', ev.allocate),
    path('electives/remove/', ev.remove),
    path('electives/my/', ev.my_electives_v2),
    path('electives/my/choose/', ev.my_choose),
    path('electives/my/drop/', ev.my_drop),

    # ================= CBCS: REGULATIONS, CATEGORIES, CREDITS (WAVE 3 PART 1A) =================
    path('regulations/', rv.regulation_list),
    path('regulations/<int:pk>/', rv.regulation_detail),
    path('regulations/<int:pk>/default/', rv.regulation_make_default),
    path('regulations/<int:pk>/batches/', rv.regulation_add_batch),
    path('regulations/<int:pk>/batches/<int:year>/', rv.regulation_remove_batch),
    path('course-categories/', rv.category_list),
    path('course-categories/template/', rv.category_template),
    path('course-categories/<int:pk>/', rv.category_detail),
    path('curriculum/', rv.curriculum_view),
    path('curriculum/requirements/', rv.curriculum_requirements),

    # ================= CBCS PART A: COURSE REGISTRATION =================
    path('course-registration/me/', cr.my_registration),
    path('course-registration/me/submit/', cr.my_submit),
    path('course-registration/review/', cr.review_list),
    path('course-registration/review/approve-ok/', cr.review_approve_ok),
    path('course-registration/<int:pk>/approve/', cr.review_approve),
    path('course-registration/<int:pk>/return/', cr.review_return),
    path('course-registration/windows/', cr.window_list),
    path('course-registration/windows/<int:pk>/', cr.window_detail),
    path('course-registration/windows/<int:pk>/allocation/', cr.window_allocation),
    path('course-registration/windows/<int:pk>/fill-waitlist/', cr.window_fill_waitlist),
    path('course-registration/windows/<int:pk>/students/', cr.window_student_list),   # CBCS PART B

    # ================= PARENT ACCOUNTS =================
    path('manage/parents/', manage_parents),
    path('manage/parents/<int:profile_id>/children/', update_parent_children),

    path('', include(router.urls)),
]