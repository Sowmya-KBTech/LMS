from rest_framework import serializers
from .models import InternalAssessment, IAMark
from .models import SemesterResult, ResultEntry,ExamSchedule
from .models import RevaluationRequest

# ===================== IA MARK (TEACHER / ADMIN) =====================
class IAMarkSerializer(serializers.ModelSerializer):
   
    student_name = serializers.CharField(
        source="student.display_name",
        read_only=True
    )

    roll_number = serializers.CharField(
        source="student.roll_number",
        read_only=True
    )

    class Meta:
        model = IAMark
        fields = [ "id", "student", "student_name", "roll_number", "marks_obtained", "is_absent", "updated_at", ]

    # FIX #14: a single-mark edit (PATCH /ia-marks/<id>/) must obey the same
    # 0..max_marks rule as the bulk grid and the CSV import.
    def validate(self, attrs):
        attrs = super().validate(attrs)
        absent = attrs.get("is_absent", getattr(self.instance, "is_absent", False))
        marks = attrs.get("marks_obtained", getattr(self.instance, "marks_obtained", None))
        if absent or marks is None:
            return attrs
        assessment = getattr(self.instance, "assessment", None)
        max_marks = assessment.max_marks if assessment else 100
        if marks < 0 or marks > max_marks:
            raise serializers.ValidationError(
                {"marks_obtained": f"Marks must be between 0 and {max_marks}."}
            )
        return attrs


# ===================== IA SLOT (TEACHER / ADMIN) =====================
class InternalAssessmentSerializer(serializers.ModelSerializer):

    marks = IAMarkSerializer( many=True, read_only=True)

    subject_name = serializers.CharField( source="teaching_assignment.subject.name", read_only=True)

    class Meta:
        model = InternalAssessment
        fields = [ "id", "teaching_assignment", "subject_name", "number", "max_marks", "is_locked", "created_at", "marks",  ]


# ===================== IA MARK (STUDENT — READ ONLY) =====================
class IAMarkStudentSerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source="assessment.teaching_assignment.subject.name",
        read_only=True
    )

    ia_number = serializers.IntegerField(
        source="assessment.number",
        read_only=True
    )

    max_marks = serializers.IntegerField(
        source="assessment.max_marks",
        read_only=True
    )

    class Meta:
        model = IAMark
        fields = [
            "id",
            "subject_name",
            "ia_number",
            "max_marks",
            "marks_obtained",
            "is_absent",
        ]
        read_only_fields = fields




# ===================== RESULT ENTRY (ADMIN) =====================
class ResultEntrySerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True
    )

    class Meta:
        model = ResultEntry
        fields = [
            "id",
            "subject",
            "subject_name",
            "max_marks",
            "marks_obtained",
            "grade",
            "is_pass",
            # WAVE 3 PART 1B (CBCS)
            "internal_marks", "end_marks", "grade_points", "outcome", "attempt", "exam_session",
        ]
        read_only_fields = ["grade", "is_pass", "grade_points", "outcome", "attempt"]


# ===================== SEMESTER RESULT (ADMIN) =====================
class SemesterResultSerializer(serializers.ModelSerializer):

    entries = ResultEntrySerializer(
        many=True,
        read_only=True
    )

    student_name = serializers.CharField(
        source="student.display_name",
        read_only=True
    )

    roll_number = serializers.CharField(
        source="student.roll_number",
        read_only=True
    )

    class Meta:
        model = SemesterResult
        fields = [
            "id",
            "student",
            "student_name",
            "roll_number",
            "semester",
            "is_published",
            "created_at",
            "entries",
        ]


# ===================== RESULT ENTRY (STUDENT — READ ONLY) =====================
class ResultEntryStudentSerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True
    )

    class Meta:
        model = ResultEntry
        fields = [
            "id",
            "subject_name",
            "max_marks",
            "marks_obtained",
            "grade",
            "is_pass",
            # WAVE 3 PART 1B (CBCS)
            "internal_marks", "end_marks", "grade_points", "outcome", "attempt", "exam_session",
        ]
        read_only_fields = fields


# ===================== SEMESTER RESULT (STUDENT — READ ONLY) =====================
class SemesterResultStudentSerializer(serializers.ModelSerializer):
    
    entries = ResultEntryStudentSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = SemesterResult
        fields = [
            "id",
            "semester",
            "is_published",
            "entries",
        ]
        read_only_fields = fields

from .models import ExamSchedule


class ExamScheduleSerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True
    )

    subject_code = serializers.CharField(
        source="subject.code",
        read_only=True
    )

    class Meta:
        model = ExamSchedule
        fields = [
            "id",
            "subject",
            "subject_name",
            "subject_code",
            "semester",
            "exam_date",
            "session",
            "exam_session",     # WAVE 3 PART 2 (empty = the current session)
        ]
        validators = []         # the one-slot-per-subject rule is checked in the view

# ===================== REVALUATION REQUEST =====================
from .models import RevaluationWindow


class RevaluationRequestSerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source="result_entry.subject.name",
        read_only=True
    )

    subject_code = serializers.CharField(
        source="result_entry.subject.code",
        read_only=True
    )

    semester = serializers.IntegerField(
        source="result_entry.result.semester",
        read_only=True
    )

    current_marks = serializers.FloatField(
        source="result_entry.marks_obtained",
        read_only=True
    )

    student_name = serializers.CharField(
        source="student.display_name",
        read_only=True
    )

    student_roll_no = serializers.CharField(
        source="student.roll_number",
        read_only=True
    )

    fee_amount = serializers.SerializerMethodField()
    fee_paid = serializers.SerializerMethodField()

    class Meta:
        model = RevaluationRequest
        fields = ["id",  "student",
            "student_name",
            "student_roll_no",
            "result_entry",
            "subject_name",
            "subject_code",
            "semester",
            "current_marks",
            "status",
            "original_marks",
            "revised_marks",
            "fee",
            "fee_amount",
            "fee_paid",
            "created_at",
        ]
        read_only_fields = ["status", "original_marks", "revised_marks", "fee", "student"]

    def get_fee_amount(self, obj):
        return float(obj.fee.amount) if obj.fee else None

    def get_fee_paid(self, obj):
        return obj.fee.status == "paid" if obj.fee else False


# ===================== REVALUATION WINDOW =====================
class RevaluationWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevaluationWindow
        fields = ["id", "semester", "is_open", "fee_amount", "opened_at", "closed_at"]