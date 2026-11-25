from rest_framework import serializers
from .models import CalendarEvent,Announcement

# ===================== CALENDAR EVENT =====================
class CalendarEventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = CalendarEvent
        fields = [
            'id', 'title', 'event_type', 'audience', 'year_number',
            'start_date', 'end_date', 'description',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

class AnnouncementSerializer(serializers.ModelSerializer):
    posted_by_name = serializers.CharField(source='posted_by.username', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'message', 'audience',
            'posted_by', 'posted_by_name', 'created_at',
        ]
        read_only_fields = ['posted_by', 'created_at']