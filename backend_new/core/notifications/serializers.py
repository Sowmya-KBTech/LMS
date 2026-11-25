from rest_framework import serializers
from core.notifications.models import Notification


# ===================== NOTIFICATION =====================
class NotificationSerializer(serializers.ModelSerializer):

    recipient_name = serializers.CharField(
        source='recipient.username',
        read_only=True
    )

    class Meta:

        model = Notification

        fields = '__all__'

        read_only_fields = [
            'created_at'
        ]
