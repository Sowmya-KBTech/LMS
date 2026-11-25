# backend/classgroups/serializers.py
from rest_framework import serializers

from django.utils import timezone

from .models import ClassGroup, ClassMessage, ClassPollVote


def person_name(u):
    # one rule for names: User.display_name
    return u.display_name if u else ""


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
    poll = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()

    class Meta:
        model = ClassMessage
        fields = [
            "id", "group", "message_type", "title", "text",
            "sender", "sender_name", "sender_role", "from_me",
            "attachment_url", "attachment_name", "attachment_size",
            "attachment_size_label",
            "is_pinned", "can_delete", "can_pin", "created_at",
            "poll", "event",
        ]
        read_only_fields = fields

    # ---------- poll ----------
    def get_poll(self, o):
        """
        Counts and percentages for everyone; the student's own choice echoed
        back to them. NEVER any names — the owner reads those from
        .../responses/, which students cannot call.
        """
        if o.message_type != ClassMessage.POLL:
            return None
        poll = getattr(o, "poll", None)
        if not poll:
            return None

        me = self._user()
        is_owner = o.group.owner() == me

        votes = list(poll.votes.all())
        total = len(votes)
        mine = next((v for v in votes if v.student_id == me.id), None)

        options = []
        for opt in poll.options.all():
            n = sum(1 for v in votes if v.option_id == opt.id)
            options.append({
                "id": opt.id,
                "text": opt.text,
                "votes": n,
                "percent": round(n * 100 / total) if total else 0,
                "is_mine": bool(mine and mine.option_id == opt.id),
            })

        return {
            "id": poll.id,
            "closes_at": poll.closes_at,
            "is_open": poll.is_open,
            "total_votes": total,
            "options": options,
            "my_vote": mine.option_id if mine else None,
            "my_vote_text": mine.option.text if mine else "",
            "can_vote": poll.is_open and not mine and not is_owner,
            "can_close": is_owner and poll.is_open,
            "can_view_responses": is_owner,
        }

    # ---------- event ----------
    def get_event(self, o):
        if o.message_type != ClassMessage.EVENT:
            return None
        ev = getattr(o, "event", None)
        if not ev:
            return None
        return {
            "id": ev.id,
            "starts_at": ev.starts_at,
            "ends_at": ev.ends_at,
            "location": ev.location,
            "is_past": ev.starts_at < timezone.now(),
        }

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