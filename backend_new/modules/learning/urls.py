# Learning module: lectures, assignments, submissions, quizzes,
# study materials, discussions, feedback, progress.
from rest_framework.routers import DefaultRouter
from django.urls import path, include

from . import online_tests      # WAVE 3 PART 3: online tests (the quiz, upgraded)
from .views import (
    LectureViewSet,
    AssignmentViewSet,
    SubmissionViewSet,
    QuizViewSet,
    QuestionViewSet,
    QuizAttemptViewSet,
    StudyMaterialViewSet,
    MaterialFolderViewSet,
    DiscussionMessageViewSet,
    FeedbackViewSet,
    my_progress,
    class_progress,
)

router = DefaultRouter()
router.register(r'lectures', LectureViewSet, basename='lecture')
router.register(r'assignments', AssignmentViewSet, basename='assignment')
router.register(r'submissions', SubmissionViewSet, basename='submission')
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'quiz-attempts', QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'study-materials', StudyMaterialViewSet, basename='study-material')
router.register(r'discussions', DiscussionMessageViewSet, basename='discussion')
router.register(r'feedback', FeedbackViewSet, basename='feedback')
router.register(r'material-folders', MaterialFolderViewSet, basename='material-folders')

urlpatterns = [
    # ================= WAVE 3 PART 3: ONLINE TESTS =================
    path('online-tests/bank/', online_tests.bank),
    path('online-tests/bank/meta/', online_tests.bank_meta),
    path('online-tests/bank/generate/', online_tests.bank_generate),
    path('online-tests/bank/<int:pk>/', online_tests.bank_detail),
    path('online-tests/tests/', online_tests.tests),
    path('online-tests/tests/check/', online_tests.test_check),
    path('online-tests/tests/<int:pk>/', online_tests.test_detail),
    path('online-tests/tests/<int:pk>/publish/', online_tests.test_publish),
    path('online-tests/tests/<int:pk>/unpublish/', online_tests.test_unpublish),
    path('online-tests/tests/<int:pk>/attempts/', online_tests.test_attempts),
    # WAVE 3 PART 3b: marking + results
    path('online-tests/tests/<int:pk>/attempts/<int:aid>/', online_tests.teacher_attempt),
    path('online-tests/tests/<int:pk>/marking/', online_tests.marking_overview),
    path('online-tests/tests/<int:pk>/marking/<int:qid>/', online_tests.marking_question),
    path('online-tests/tests/<int:pk>/results/', online_tests.test_results),
    path('online-tests/tests/<int:pk>/release/', online_tests.test_release),
    path('online-tests/tests/<int:pk>/withdraw/', online_tests.test_withdraw),
    path('online-tests/tests/<int:pk>/preview/', online_tests.test_preview),
    path('online-tests/tests/<int:pk>/start/', online_tests.test_start),
    path('online-tests/attempts/<int:pk>/', online_tests.attempt_detail),
    path('online-tests/attempts/<int:pk>/save/', online_tests.attempt_save),
    path('online-tests/attempts/<int:pk>/submit/', online_tests.attempt_submit),
    path('online-tests/attempts/<int:pk>/review/', online_tests.attempt_review),
    path('my-progress/', my_progress),
    path('class-progress/', class_progress),
    path('', include(router.urls)),
]
