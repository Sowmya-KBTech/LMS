# backend/classgroups/serializers.py
from rest_framework import serializers

from .models import ClassGroup, ClassMessage


def person_name(u):
    if not u:
        return ""
    return f"{u.first_name} {u.last_name}".strip() or u.username


def size_label(n):
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


class ClassMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.CharField(source="sender.role", read_only=True)
    from_me = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()
    attachment_size_label = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_pin = serializers.SerializerMethodField()

    class Meta:
        model = ClassMessage
        fields = [
            "id", "group", "message_type", "title", "text",
            "sender", "sender_name", "sender_role", "from_me",
            "attachment_url", "attachment_name", "attachment_size",
            "attachment_size_label",
            "is_pinned", "can_delete", "can_pin", "created_at",
        ]
        read_only_fields = fields

    def _user(self):
        return self.context["request"].user

    def get_sender_name(self, o):
        return person_name(o.sender)

    def get_from_me(self, o):
        return o.sender_id == self._user().id

    def get_attachment_url(self, o):
        if not o.attachment:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(o.attachment.url) if req else o.attachment.url

    def get_attachment_size_label(self, o):
        return size_label(o.attachment_size) if o.attachment else ""

    def get_can_delete(self, o):
        u = self._user()
        return o.sender_id == u.id or o.group.owner() == u

    def get_can_pin(self, o):
        return o.message_type == ClassMessage.ANNOUNCEMENT and o.group.owner() == self._user()


class GroupSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassGroup
        fields = ["announcement_only", "students_can_message", "students_can_upload"]