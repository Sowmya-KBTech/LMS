# backend/mentoring/team_serializers.py
"""Shapes for team-based allocation. Kept apart from serializers.py."""

from rest_framework import serializers

from .models import MentorRule


class MentorRuleSerializer(serializers.ModelSerializer):
    """The department's team rules for one academic year."""

    department_name = serializers.CharField(source="department.name", read_only=True)
    grade_mix_label = serializers.CharField(
        source="get_grade_mix_display", read_only=True
    )
    fallback_label = serializers.CharField(
        source="get_fallback_display", read_only=True
    )

    class Meta:
        model = MentorRule
        fields = [
            "id", "department", "department_name", "academic_year",
            "team_size", "grade_mix", "grade_mix_label",
            "fallback", "fallback_label",
            "skip_last_year_mentors", "skip_class_advisors",
            "tiebreak_fewest_mentees",
            "updated_at",
        ]
        read_only_fields = [
            "id", "department", "department_name", "academic_year", "updated_at"
        ]

    def validate_team_size(self, value):
        if value < 2 or value > 10:
            raise serializers.ValidationError(
                "A team holds between 2 and 10 students."
            )
        return value


class JoinTeamSerializer(serializers.Serializer):
    """Omit team_id to start a new team instead of joining one."""

    team_id = serializers.IntegerField(required=False, allow_null=True)


class PlaceStudentSerializer(serializers.Serializer):
    """Omit team_id to mark the student as deliberately left unplaced."""

    student_id = serializers.IntegerField()
    team_id = serializers.IntegerField(required=False, allow_null=True)


class SetTeamMentorSerializer(serializers.Serializer):
    team_id = serializers.IntegerField()
    mentor_id = serializers.IntegerField(allow_null=True, required=False)