from django.urls import path
from . import planner_views                       # WAVE 1: student planner
from .views import (
    AssignmentOptions,
    TimeSlotDetail,
    TimeSlotListCreate,
    TimetableDetail,
    TimetableListCreate,
    SemesterActive, SemesterAll, HolidayListCreate, HolidayDetail,
    TimetableSubmit, TimetableApprovalStatus,
    TimetableApprovalList, TimetableApprovalAction,
    RoomListCreate, RoomDetail,
    ActivityTypeListCreate, ActivityTypeDetail,
    ClassActivityList, ClassActivityDetail,
    TimetableAvailability, TimetableAutoFillStart,
    TimetableBusy, TimetableMove,
)

urlpatterns = [
    # WAVE 1: a student's (or parent's child's) planner -> /api/planner/
    path("planner/", planner_views.planner, name="student-planner"),

    # bell schedule
    path("timeslots/", TimeSlotListCreate.as_view(), name="timeslot-list-create"),
    path("timeslots/<int:pk>/", TimeSlotDetail.as_view(), name="timeslot-detail"),

    # ----- approval workflow (specific routes BEFORE the <int:pk> catch) -----
    path("timetable/submit/", TimetableSubmit.as_view(), name="timetable-submit"),
    path("timetable/approval-status/", TimetableApprovalStatus.as_view(), name="timetable-approval-status"),
    path("timetable/approvals/", TimetableApprovalList.as_view(), name="timetable-approvals"),
    path("timetable/approvals/<int:pk>/action/", TimetableApprovalAction.as_view(), name="timetable-approval-action"),

    # ----- builder helpers & AI (string routes, kept before <int:pk>) -----
    path("timetable/options/", AssignmentOptions.as_view(), name="timetable-options"),
    path("timetable/availability/", TimetableAvailability.as_view(), name="timetable-availability"),
    # Redis/Celery work, step 6.3: auto-fill runs in the Celery worker (the old
    # waiting "timetable/autofill/" was removed - lead's decision 20-11-2026)
    path("timetable/autofill/start/", TimetableAutoFillStart.as_view(), name="timetable-autofill-start"),
    path("timetable/busy/", TimetableBusy.as_view(), name="timetable-busy"),
    path("timetable/move/", TimetableMove.as_view(), name="timetable-move"),

    # timetable grid
    path("timetable/", TimetableListCreate.as_view(), name="timetable-list-create"),
    path("timetable/<int:pk>/", TimetableDetail.as_view(), name="timetable-detail"),

    # rooms (college-wide, admin-managed)
    path("rooms/", RoomListCreate.as_view(), name="room-list-create"),
    path("rooms/<int:pk>/", RoomDetail.as_view(), name="room-detail"),

    # activity types (college-wide catalogue)
    path("activity-types/", ActivityTypeListCreate.as_view(), name="activitytype-list-create"),
    path("activity-types/<int:pk>/", ActivityTypeDetail.as_view(), name="activitytype-detail"),

    # class activities ("this class has Library 1/week")
    path("class-activities/", ClassActivityList.as_view(), name="classactivity-list-create"),
    path("class-activities/<int:pk>/", ClassActivityDetail.as_view(), name="classactivity-detail"),

    # term + holidays
    path("semester/", SemesterActive.as_view(), name="semester-active"),
    path("semester/all/", SemesterAll.as_view(), name="semester-all"),   # parent "previous semesters"
    path("holidays/", HolidayListCreate.as_view(), name="holiday-list-create"),
    path("holidays/<int:pk>/", HolidayDetail.as_view(), name="holiday-detail"),
]