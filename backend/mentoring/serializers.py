# backend/mentoring/serializers.py
from rest_framework import serializers

from users.models import User
from .models import MentorAllocation, MentorChangeRequest, MentoringSetting


def person_name(u):
    if not u:
        return ""
    full = f"{u.first_name} {u.last_name}".strip()
    return full or u.username


# ================= SMALL NESTED SHAPES =================
class StudentBriefSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    course_name = serializers.CharField(source="course.name", default="", read_only=True)

    class Meta:
        model = User
        fields = ["id", "name", "roll_number", "year", "semester", "course_name", "email"]

    def get_name(self, obj):
        return person_name(obj)


class MentorBriefSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    designation = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "employee_id", "designation", "email"]

    def get_name(self, obj):
        return person_name(obj)

    def get_designation(self, obj):
        return obj.get_sub_role_display() if obj.sub_role else ""


# ================= ALLOCATION =================
class AllocationSerializer(serializers.ModelSerializer):
    """Read shape used by every HOD table."""

    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source="student.roll_number", read_only=True)
    student_year = serializers.IntegerField(source="student.year", read_only=True)
    student_semester = serializers.IntegerField(source="student.semester", read_only=True)
    course_name = serializers.CharField(source="student.course.name", default="", read_only=True)

    mentor_name = serializers.SerializerMethodField()
    mentor_employee_id = serializers.CharField(source="mentor.employee_id", read_only=True)

    proposed_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    previous_mentor_name = serializers.SerializerMethodField()
    suggested_mentor_name = serializers.SerializerMethodField()

    recommended_by = serializers.SerializerMethodField()

    class Meta:
        model = MentorAllocation
        fields = [
            "id",
            "student", "student_name", "student_roll", "student_year",
            "student_semester", "course_name",
            "mentor", "mentor_name", "mentor_employee_id",
            "department", "academic_year",
            "grade_band", "cgpa_at_allocation",
            "status", "source", "recommended_by",
            "proposed_by", "proposed_by_name",
            "approved_by", "approved_by_name",
            "previous_mentor", "previous_mentor_name",
            "suggested_mentor", "suggested_mentor_name",
            "reason", "note",
            "start_date", "end_date", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_student_name(self, o):
        return person_name(o.student)

    def get_mentor_name(self, o):
        return person_name(o.mentor)

    def get_proposed_by_name(self, o):
        return person_name(o.proposed_by)

    def get_approved_by_name(self, o):
        return person_name(o.approved_by)

    def get_previous_mentor_name(self, o):
        return person_name(o.previous_mentor)

    def get_suggested_mentor_name(self, o):
        return person_name(o.suggested_mentor)

    def get_recommended_by(self, o):
        """What the 'Recommended By' column shows."""
        if o.source == "advisor" and o.proposed_by:
            return person_name(o.proposed_by)
        if o.source == "auto":
            return "Auto-distributed"
        return "HOD"


class AssignSerializer(serializers.Serializer):
    """POST body for assign / reassign / bulk assign."""
    student_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )
    mentor_id = serializers.IntegerField()
    academic_year = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    # capacity and balance are warnings; the caller confirms to proceed
    override = serializers.BooleanField(required=False, default=False)


class ProposeSerializer(serializers.Serializer):
    """POST body a class advisor uses to propose a group list."""
    allocations = serializers.ListField(
        child=serializers.DictField(), allow_empty=False
    )  # [{"student_id": 1, "mentor_id": 9}, ...]
    academic_year = serializers.CharField(required=False, allow_blank=True)


class DecideProposalSerializer(serializers.Serializer):
    allocation_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(required=False, allow_blank=True)


class RemoveSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


# ================= SETTINGS =================
class MentoringSettingSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = MentoringSetting
        fields = [
            "id", "department", "department_name",
            "max_students_per_mentor",
            "allocate_from_year",
            "band_a_min", "band_b_min",
            "require_all_bands", "route_via_advisor",
            "first_year_rule", "updated_at",
        ]
        read_only_fields = ["id", "department", "department_name", "updated_at"]



# ================= CHANGE REQUEST =================
class ChangeRequestSerializer(serializers.ModelSerializer):
    """Row shape for the HOD queue."""

    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source="student.roll_number", read_only=True)
    student_year = serializers.IntegerField(source="student.year", read_only=True)
    course_name = serializers.CharField(source="student.course.name", default="", read_only=True)

    current_mentor_name = serializers.SerializerMethodField()
    new_mentor_name = serializers.SerializerMethodField()
    advisor_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()
    raised_by_name = serializers.SerializerMethodField()

    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.SerializerMethodField()

    class Meta:
        model = MentorChangeRequest
        fields = [
            "id",
            "student", "student_name", "student_roll", "student_year", "course_name",
            "current_mentor", "current_mentor_name",
            "academic_year",
            "raised_by", "raised_by_name", "raised_role", "source_label",
            "reason", "reason_label", "detail", "is_confidential",
            "status", "status_label",
            "advisor", "advisor_name", "advisor_note", "advisor_acted_at",
            "decided_by", "decided_by_name", "decision_note", "decided_at",
            "new_mentor", "new_mentor_name",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_student_name(self, o):
        return person_name(o.student)

    def get_current_mentor_name(self, o):
        return person_name(o.current_mentor)

    def get_new_mentor_name(self, o):
        return person_name(o.new_mentor)

    def get_advisor_name(self, o):
        return person_name(o.advisor)

    def get_decided_by_name(self, o):
        return person_name(o.decided_by)

    def get_raised_by_name(self, o):
        return person_name(o.raised_by)

    def get_source_label(self, o):
        """What the HOD list shows as the origin tag."""
        if o.raised_role == "mentor":
            return "From a mentor"
        if o.is_confidential:
            return "Confidential"
        if o.advisor_acted_at:
            return "Forwarded by advisor"
        return "From a student"


class DecideChangeRequestSerializer(serializers.Serializer):
    """POST body for the HOD decision."""
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    new_mentor_id = serializers.IntegerField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    # capacity is a warning, same as hod_assign
    override = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if data["decision"] == "approve" and not data.get("new_mentor_id"):
            raise serializers.ValidationError(
                {"new_mentor_id": "Pick the mentor the student moves to."}
            )
        if data["decision"] == "reject" and not (data.get("note") or "").strip():
            raise serializers.ValidationError(
                {"note": "A rejection needs a reason — the student is shown it."}
            )
        return data


class CreateChangeRequestSerializer(serializers.Serializer):
    """POST body a student uses to raise a request."""
    reason = serializers.ChoiceField(choices=[c[0] for c in MentorChangeRequest.REASON_CHOICES])
    detail = serializers.CharField(required=False, allow_blank=True)

    def validate_reason(self, value):
        if value in MentorChangeRequest.STAFF_ONLY_REASONS:
            raise serializers.ValidationError("That reason is for mentors only.")
        return value

    def validate(self, data):
        if data["reason"] == "other" and not (data.get("detail") or "").strip():
            raise serializers.ValidationError(
                {"detail": "Tell them a little more when you choose Other."}
            )
        return data


class AdvisorActSerializer(serializers.Serializer):
    """POST body a class advisor uses to forward or resolve."""
    action = serializers.ChoiceField(choices=["forward", "resolve"])
    note = serializers.CharField()

    def validate_note(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "A note is required — the student is shown it either way."
            )
        return value.strip()




class MentorRaiseSerializer(serializers.Serializer):
    """POST body a mentor uses to ask for one of their mentees to be moved."""
    student_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=[c[0] for c in MentorChangeRequest.REASON_CHOICES])
    detail = serializers.CharField(required=False, allow_blank=True)

    def validate_reason(self, value):
        # a mentor has no business claiming a student is uncomfortable with them
        if value in MentorChangeRequest.CONFIDENTIAL_REASONS:
            raise serializers.ValidationError(
                "That reason is for a student to give, not a mentor."
            )
        return value

    def validate(self, data):
        if data["reason"] == "other" and not (data.get("detail") or "").strip():
            raise serializers.ValidationError(
                {"detail": "Say a little more when you choose Other."}
            )
        return data