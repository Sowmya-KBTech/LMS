from django.urls import path

from . import views

urlpatterns = [

    # ================= CONTEXT =================
    path("me/", views.placement_me, name="placement-me"),

    # ================= COORDINATORS =================
    path("coordinators/", views.coordinator_list, name="placement-coordinator-list"),
    path("coordinators/<int:pk>/", views.coordinator_detail, name="placement-coordinator-detail"),

    # ================= PICKERS =================
    path("assignable-teachers/", views.assignable_teachers, name="placement-assignable-teachers"),
    path("departments/", views.placement_departments, name="placement-departments"),

    # ================= ACADEMICS (PHASE 1) =================
    path("my-academics/", views.my_academics, name="placement-my-academics"),
    path("verify-academics/", views.academics_verification_list, name="placement-verify-academics-list"),
    path("verify-academics/<int:student_id>/", views.verify_academics, name="placement-verify-academics"),

    # ================= COMPANIES (PHASE 2) =================
    # "categories" stays above "<int:pk>" so the literal path matches first.
    path("companies/categories/", views.company_categories, name="placement-company-categories"),
    path("companies/", views.company_list, name="placement-company-list"),
    path("companies/<int:pk>/", views.company_detail, name="placement-company-detail"),

    # ================= DRIVES (PHASE 3) =================
    # No round routes here. DriveRound and RoundResult were removed: companies
    # run their own tests on their own platforms, so this college never sees
    # stage-by-stage outcomes. It records who ATTENDED and who got PLACED.
    path("my-drives/", views.my_drives, name="placement-my-drives"),
    path("drives/", views.drive_list, name="placement-drive-list"),
    path("drives/<int:pk>/", views.drive_detail, name="placement-drive-detail"),
    path("drives/<int:pk>/roles/", views.drive_job_roles, name="placement-drive-job-roles"),

    # ================= JOB ROLES (PHASE 3b) =================
    # Eligibility and the match count hang off the ROLE, not the drive -- one
    # visit can open several positions with different cutoffs.
    path("roles/<int:role_id>/", views.job_role_detail, name="placement-job-role-detail"),
    path("roles/<int:role_id>/eligibility/", views.role_eligibility, name="placement-role-eligibility"),
    path("roles/<int:role_id>/matches/", views.role_matches, name="placement-role-matches"),

    # ================= APPLICATIONS (PHASE 4) =================
    path("my-applications/", views.my_applications, name="placement-my-applications"),
    path("roles/<int:role_id>/apply/", views.apply_to_role, name="placement-apply"),
    path("roles/<int:role_id>/applications/", views.role_applications, name="placement-role-applications"),

    # ================= ATTENDANCE (PHASE 5) =================
    # Per ROLE -- the sheet a coordinator works from on the day. Marking a
    # student present creates an approved OD and writes duty_leave attendance,
    # through placement/services.py -> attendance/services.py.
    path("roles/<int:role_id>/attendance/", views.drive_attendance, name="placement-drive-attendance"),

    # ================= OFFERS (PHASE 6) =================
    # The officer RECORDS an offer; the STUDENT accepts or declines it through
    # decide-offer below. Two endpoints because they are two different
    # decisions made by two different people.
    path("roles/<int:role_id>/offers/", views.role_offers, name="placement-role-offers"),
    path("offers/<int:offer_id>/", views.offer_detail, name="placement-offer-detail"),

    # The student's own offers. No id in the path -- always request.user.
    path("my-offers/", views.my_offers, name="placement-my-offers"),
    path("offers/<int:offer_id>/decide/", views.decide_offer, name="placement-decide-offer"),
     path("report/", views.placement_report, name="placement-report"),
      path("dashboard/", views.placement_dashboard, name="placement-dashboard"),
]