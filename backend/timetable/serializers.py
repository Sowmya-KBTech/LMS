from rest_framework import serializers

from .models import (
    TimeSlot,
    TimetableEntry,
    Semester,
    Holiday,
    Room,
    ActivityType,
    ClassActivity,
)


class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ["id", "period_no", "start_time", "end_time", "label", "is_break"]


class TimetableEntrySerializer(serializers.ModelSerializer):
    # An entry is either a CLASS (backed by a TeachingAssignment) or an
    # ACTIVITY (mentor, library, sports — no subject, no syllabus, often no
    # teacher). Every method below has to survive `assignment` being NULL.
    subject = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    course = serializers.SerializerMethodField()
    year_number = serializers.SerializerMethodField()
    semester = serializers.SerializerMethodField()
    class_label = serializers.SerializerMethodField()
    activity_name = serializers.SerializerMethodField()
    activity_colour = serializers.SerializerMethodField()

    period_no = serializers.IntegerField(source="time_slot.period_no", read_only=True)
    day_display = serializers.CharField(source="get_day_of_week_display", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "kind",
            "assignment", "class_activity",
            "day_of_week", "day_display",
            "time_slot", "period_no",
            "room", "room_name",
            "subject", "teacher_name", "course", "year_number",
            "semester", "class_label",
            "activity_name", "activity_colour",
        ]
        read_only_fields = [
            "day_display", "period_no", "room_name",
            "activity_name", "activity_colour",
        ]

    # ---------- activity fields ----------
    def get_activity_name(self, obj):
        if obj.class_activity:
            return obj.class_activity.activity.name
        return None

    def get_activity_colour(self, obj):
        if obj.class_activity:
            return obj.class_activity.activity.colour
        return None

    # ---------- class fields (None on activities) ----------
    def get_subject(self, obj):
        if obj.class_activity:
            return obj.class_activity.activity.name      # so the grid always has a label
        return obj.assignment.subject.name if obj.assignment else None

    def get_teacher_name(self, obj):
        t = None
        if obj.assignment:
            t = obj.assignment.teacher
        elif obj.class_activity:
            t = obj.class_activity.teacher               # may be None — that's fine
        if not t:
            return None
        return (t.get_full_name() or "").strip() or t.username

    def get_course(self, obj):
        if obj.assignment:
            return obj.assignment.course.name
        return None

    def get_year_number(self, obj):
        if obj.assignment:
            return obj.assignment.year.year_number
        if obj.class_activity:
            return obj.class_activity.year.year_number
        return None

    def get_semester(self, obj):
        if obj.assignment:
            return obj.assignment.subject.semester
        if obj.class_activity:
            return obj.class_activity.semester
        return None

    def get_class_label(self, obj):
        if obj.assignment:
            return f"{obj.assignment.course.name} - Year {obj.assignment.year.year_number}"
        return None


# =====================================================
#  SEMESTER / HOLIDAY
# =====================================================
class SemesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = ["id", "name", "start_date", "end_date", "is_active"]


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]


# =====================================================
#  ROOM
# =====================================================
class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "kind", "capacity", "is_active"]


# =====================================================
#  ACTIVITIES
# =====================================================
class ActivityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = [
            "id", "name",
            "preferred_position", "prefer_consecutive",
            "colour", "is_active",
        ]


class ClassActivitySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="activity.name", read_only=True)
    colour = serializers.CharField(source="activity.colour", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    placed = serializers.SerializerMethodField()

    class Meta:
        model = ClassActivity
        fields = [
            "id", "activity", "name", "colour",
            "year", "semester",
            "periods_per_week", "placed",
            "teacher", "teacher_name",
        ]

    def get_teacher_name(self, obj):
        if not obj.teacher:
            return None
        return (obj.teacher.get_full_name() or "").strip() or obj.teacher.username

    def get_placed(self, obj):
        return obj.entries.count()