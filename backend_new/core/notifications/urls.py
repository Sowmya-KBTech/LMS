# Notifications (core): the bell-icon list. Emails are sent by signals.py.
from rest_framework.routers import DefaultRouter
from django.urls import path, include

from .views import NotificationViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
