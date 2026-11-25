# ===================== IMPORTS =====================
from django.contrib.auth import get_user_model

from rest_framework import viewsets
from rest_framework.decorators import (  action)
from rest_framework.permissions import ( IsAuthenticated)
from rest_framework.response import Response
from rest_framework.exceptions import MethodNotAllowed

from core.notifications.cache import get_unread, invalidate_unread, set_unread
from core.notifications.models import Notification

from core.notifications.serializers import NotificationSerializer

User = get_user_model()


# ===================== NOTIFICATION =====================
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    # PHASE 5: notifications are created by the system (notify()), never typed in
    # by a user - otherwise anyone could send anyone a fake "pay here" message.
    # People may read, mark read and delete THEIR OWN notifications only.
    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def get_queryset(self):
        queryset = Notification.objects.filter(
            recipient=self.request.user
        )

        unread = self.request.query_params.get("unread")
        if unread == "true":
            queryset = queryset.filter(is_read=False)

        return queryset.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        # Bell cache (Redis/Celery work): the frontend polls ?unread=true every
        # 10 s. Serve that exact request from the cache (core/notifications/cache.py).
        # Any other list request goes to the database as before.
        bell_poll = (request.query_params.get("unread") == "true"
                     and len(request.query_params) == 1)
        if not bell_poll:
            return super().list(request, *args, **kwargs)

        cached = get_unread(request.user.pk)
        if cached is not None:
            response = Response(cached)
            response["X-Cache"] = "HIT"
            return response

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            set_unread(request.user.pk, list(response.data))
        response["X-Cache"] = "MISS"
        return response

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"message": "Notification marked as read"})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        invalidate_unread([request.user])   # .update() skips signals
        return Response({"message": "All notifications marked as read"})
