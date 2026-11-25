from rest_framework import serializers
from core.academics.models import (
    Course,
    Year,
    Subject,
    TeachingAssignment,
    Enrollment,
)


# ===================== COURSE =====================
class CourseSerializer(serializers.ModelSerializer):

    class Meta:
        model = Course
        fields = [
            'id',
            'name'
        ]


# ===================== SUBJECT =====================
class SubjectSerializer(serializers.ModelSerializer):

    year_number = serializers.IntegerField(
        source='year.year_number',
        read_only=True
    )

    course_name = serializers.CharField(
        source='year.course.name',
        read_only=True
    )

    department_name = serializers.CharField(
        source='department.name',
        read_only=True
    )

    # WAVE 3 PART 1A (CBCS): half credits, sent as a number (not "4.0")
    credits = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=0, max_value=30,
        coerce_to_string=False, required=False
    )
    category_code = serializers.CharField(source='category.code', read_only=True, default='')
    regulation_name = serializers.CharField(source='regulation.name', read_only=True, default='')

    class Meta:
        model = Subject

        fields = ['id', 'name', 'code', 'credits', 'weekly_hours','is_elective','year', 'semester', 'year_number', 'course_name', 'department', 'department_name',
                  # WAVE 3 PART 1A (CBCS)
                  'regulation', 'regulation_name', 'category', 'category_code', 'kind',
                  'lecture_hours', 'tutorial_hours', 'practical_hours']

    def validate_credits(self, value):
        if value is not None and (value * 2) != (value * 2).to_integral_value():
            raise serializers.ValidationError("Credits must be whole or half (like 3 or 1.5).")
        return value

    def validate(self, attrs):
        for key in ('lecture_hours', 'tutorial_hours', 'practical_hours'):
            if attrs.get(key) is not None and attrs[key] > 40:
                raise serializers.ValidationError({key: "At most 40 hours a week."})
        return attrs


# ===================== YEAR =====================
class YearSerializer(serializers.ModelSerializer):

    course_name = serializers.CharField(
        source='course.name',
        read_only=True
    )

    subjects = SubjectSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Year

        fields = [
            'id',
            'course',
            'course_name',
            'year_number',
            'subjects'
        ]


# ===================== TEACHING ASSIGNMENT =====================
class TeachingAssignmentSerializer(serializers.ModelSerializer):

    teacher_name = serializers.CharField(
        source='teacher.username',
        read_only=True
    )

    course_name = serializers.CharField(
        source='course.name',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='subject.name',
        read_only=True
    )

    year_number = serializers.IntegerField(
        source='year.year_number',
        read_only=True
    )

    semester = serializers.IntegerField(
        source='subject.semester',
        read_only=True
    )

    subject_id = serializers.IntegerField(
        source='subject.id',
        read_only=True
    )

    class Meta:
        model = TeachingAssignment

        fields = [
            'id',
            'teacher',
            'teacher_name',
            'course',
            'course_name',
            'year',
            'year_number',
            'semester',
            'subject',
            'subject_id',
            'subject_name',
        ]


# ===================== ENROLLMENT =====================
class EnrollmentSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source='student.display_name',
        read_only=True
    )

    student_roll_no = serializers.CharField(
        source='student.roll_number',
        read_only=True
    )

    teacher_name = serializers.CharField(
        source='teaching_assignment.teacher.username',
        read_only=True
    )

    course_id = serializers.IntegerField(
        source='teaching_assignment.course.id',
        read_only=True
    )

    course_name = serializers.CharField(
        source='teaching_assignment.course.name',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='teaching_assignment.subject.name',
        read_only=True
    )

    year_number = serializers.IntegerField(
        source='teaching_assignment.year.year_number',
        read_only=True
    )

    semester = serializers.IntegerField(
        source='teaching_assignment.subject.semester',
        read_only=True
    )

    class Meta:

        model = Enrollment

        fields = [

            'id',

            # STUDENT
            'student',
            'student_name',
            'student_roll_no',

            # SUBJECT ENROLLMENT
            'teaching_assignment',

            # DETAILS
            'teacher_name',
            'course_id',
            'course_name',
            'subject_name',
            'year_number',
            'semester',

            # DATE
            'enrolled_at',
        ]
