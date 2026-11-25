# Exam URLs that live under /api/users/ (kept there so the frontend
# does not change). config/urls.py loads this file BEFORE users.urls,
# because users.urls ends with a catch-all <pk>/ route.
from django.urls import path

from .hod_views import hod_results, my_class_marksheet

urlpatterns = [
    path('hod-results/', hod_results),
    path('my-class/marksheet/', my_class_marksheet),
]
