from django.urls import path

from . import report_views          # WAVE 1: progress reports and rank lists
from . import credits_views         # WAVE 3 PART 1B: results under the regulation (CBCS)
from . import session_views         # WAVE 3 PART 2: exam sessions, registration, clash check
from . import seating               # WAVE 3 PART 2b: halls, seating, invigilation
from . import co_marks              # CO-PO PART B: IA question paper, marks by question, CO attainment
from rest_framework.routers import DefaultRouter
from .views import (
    InternalAssessmentViewSet,
    IAMarkViewSet,
    SemesterResultViewSet,
    ExamScheduleViewSet,
    students_by_class,
    my_hall_ticket,
    hall_ticket_roster,
    generate_attendance_fines,
    set_revaluation_window,
    revaluation_window_status,
    revaluation_latest,
    my_revaluations,
    apply_revaluation,
    confirm_revaluation_payment,
    revaluation_review_list,
    process_revaluation,
    cancel_revaluation,
    generate_exam_fees,
    eligibility_rules,
    eligibility_override,
    eligibility_override_revoke,
    eligibility_override_log,
)

router = DefaultRouter()
router.register( "internal-assessments", InternalAssessmentViewSet, basename="internal-assessment")
router.register("ia-marks",IAMarkViewSet,basename="ia-mark",)
router.register("semester-results",SemesterResultViewSet,basename="semester-result",)
router.register("exam-schedules",ExamScheduleViewSet,basename="exam-schedule",)

urlpatterns = router.urls + [
    # CO-PO PART B
    path("ia-papers/", co_marks.ia_paper),
    path("ia-question-marks/", co_marks.ia_question_marks),
    path("co-attainment/<int:ta_id>/", co_marks.co_attainment),
    path("co-attainment/<int:ta_id>/plan/", co_marks.co_action_plan),
    # CO-PO PART C
    path("co-attainment/<int:ta_id>/survey/", co_marks.co_exit_survey),
    path("po-attainment/", co_marks.po_attainment_view),
    path("po-attainment/export/", co_marks.po_attainment_export),
    # ================= WAVE 1: PROGRESS REPORTS + RANK LISTS =================
    path("reports/classes/", report_views.report_classes),
    path("reports/rank-list/", report_views.rank_list),
    path("reports/progress/me/", report_views.my_progress_report),
    path("reports/progress/<int:student_id>/", report_views.progress_report),

    # ================= WAVE 3 PART 1B: CBCS RESULTS =================
    path("results/credits/me/", credits_views.my_credits),
    path("results/credits/<int:student_id>/", credits_views.student_credits),
    path("results/entry-rules/", credits_views.entry_rules),
    path("results/arrear-roster/", credits_views.arrear_roster),

    # ================= WAVE 3 PART 2: EXAM SESSIONS =================
    path("exam-sessions/", session_views.sessions),
    path("exam-sessions/<int:pk>/", session_views.session_detail),
    path("exam-sessions/<int:pk>/make-current/", session_views.make_current),
    path("exam-sessions/<int:pk>/progress/", session_views.session_progress),
    path("exam-sessions/<int:pk>/registrations/", session_views.session_registrations),
    path("exam-sessions/<int:pk>/timetable-check/", session_views.timetable_check),
    path("exam-sessions/<int:pk>/publish-timetable/", session_views.publish_timetable),
    path("exam-sessions/<int:pk>/unpublish-timetable/", session_views.unpublish_timetable),
    path("exam-sessions/<int:pk>/release-hall-tickets/", session_views.release_hall_tickets),
    path("exam-sessions/<int:pk>/withdraw-hall-tickets/", session_views.withdraw_hall_tickets),
    path("exam-registration/me/", session_views.my_registration),
    # ================= WAVE 3 PART 2b: HALLS, SEATING, INVIGILATION =================
    path("exam-halls/", seating.halls),
    path("exam-halls/from-rooms/", seating.halls_from_rooms),
    path("exam-halls/<int:pk>/", seating.hall_detail),
    path("exam-sessions/<int:pk>/rules/", seating.rules),
    path("exam-sessions/<int:pk>/sittings/", seating.session_sittings),
    path("exam-sessions/<int:pk>/seating/", seating.seating),
    path("exam-sessions/<int:pk>/seating/allot/", seating.seating_allot),
    path("exam-sessions/<int:pk>/duties/", seating.duties),
    path("exam-sessions/<int:pk>/duties/assign/", seating.duties_assign),
    path("exam-duties/me/", seating.my_duties),
    path("exam-duties/<int:pk>/", seating.duty_detail),

    path("exam-students/", students_by_class),
    path("hall-ticket/", my_hall_ticket),
    path("hall-ticket/roster/", hall_ticket_roster),
    path("hall-ticket/generate-fines/", generate_attendance_fines),
    path("revaluation-window/", set_revaluation_window),
    path("revaluation-window/status/", revaluation_window_status),
    path("revaluations/", my_revaluations),
    path("revaluations/latest/", revaluation_latest),
    path("revaluations/apply/", apply_revaluation),
    path("revaluations/<int:pk>/confirm-payment/", confirm_revaluation_payment),
    path("revaluations/review/", revaluation_review_list),
    path("revaluations/<int:pk>/process/", process_revaluation),
    path("revaluations/<int:pk>/cancel/", cancel_revaluation),
    path("hall-ticket/generate-exam-fees/", generate_exam_fees),
    path("hall-ticket/eligibility-rules/", eligibility_rules),
    path("hall-ticket/override/", eligibility_override),
    path("hall-ticket/override/<int:pk>/revoke/", eligibility_override_revoke),
    path("hall-ticket/overrides/", eligibility_override_log),
]