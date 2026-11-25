from rest_framework import serializers
from modules.messaging.models import ParentMessage, ConversationMessage


# ===================== PARENT MESSAGE =====================
class ParentMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    receiver_name = serializers.CharField(source='receiver.username', read_only=True)

    class Meta:
        model = ParentMessage
        fields = ['id', 'sender', 'sender_name', 'receiver',
                  'receiver_name', 'text', 'is_read', 'created_at']
        read_only_fields = ['sender', 'created_at']


# ===================== CONVERSATION MESSAGE =====================
class ConversationMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    receiver_name = serializers.CharField(source='receiver.username', read_only=True)

    class Meta:
        model = ConversationMessage
        fields = ['id', 'sender', 'sender_name', 'receiver',
                  'receiver_name', 'text', 'is_read', 'created_at']
        read_only_fields = ['sender', 'created_at']
