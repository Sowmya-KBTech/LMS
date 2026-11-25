from rest_framework import serializers
from modules.learning.models import (
    Lecture,
    Assignment,
    Submission,
    Quiz,
    Question,
    QuizAttempt,
    StudyMaterial,
    MaterialFolder,
    DiscussionMessage,
    Feedback,
)


        
# ===================== LECTURE =====================
class LectureSerializer(serializers.ModelSerializer):

    teacher_name = serializers.CharField(
        source='teaching_assignment.teacher.username',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='teaching_assignment.subject.name',
        read_only=True
    )

    course_name = serializers.CharField(
        source='teaching_assignment.course.name',
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
        model = Lecture

        fields = '__all__'

        read_only_fields = [
            'created_by',
            'created_at'
        ]


# ===================== ASSIGNMENT =====================
class AssignmentSerializer(serializers.ModelSerializer):

    teacher_name = serializers.CharField(
        source='teaching_assignment.teacher.username',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='teaching_assignment.subject.name',
        read_only=True
    )

    course_name = serializers.CharField(
        source='teaching_assignment.course.name',
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
        model = Assignment

        fields = '__all__'

        read_only_fields = [
            'created_by',
            'created_at'
        ]


# ===================== SUBMISSION =====================
class SubmissionSerializer(serializers.ModelSerializer):

    # ================= STUDENT =================
    student_name = serializers.CharField(
        source='student.username',
        read_only=True
    )

    student_roll_no = serializers.CharField(
        source='student.roll_number',
        read_only=True
    )

    # ================= ASSIGNMENT =================
    assignment_title = serializers.CharField(
        source='assignment.title',
        read_only=True
    )

    # ================= SUBJECT =================
    subject_name = serializers.CharField(
        source='assignment.teaching_assignment.subject.name',
        read_only=True
    )

    # ================= COURSE =================
    course_name = serializers.CharField(
        source='assignment.teaching_assignment.course.name',
        read_only=True
    )

    # ================= YEAR =================
    year_number = serializers.IntegerField(
        source='assignment.teaching_assignment.year.year_number',
        read_only=True
    )

    # ================= SEMESTER =================
    semester = serializers.IntegerField(
        source='assignment.teaching_assignment.subject.semester',
        read_only=True
    )

    # ================= TOTAL MARKS =================
    total_marks = serializers.IntegerField(
        source='assignment.total_marks',
        read_only=True
    )

    class Meta:

        model = Submission

        fields = '__all__'

        read_only_fields = [

            # AUTO
            'student',
            'submitted_at',
            'graded_at',

            # DISPLAY
            'student_name',
            'student_roll_no',
            'assignment_title',
            'subject_name',
            'course_name',
            'year_number',
            'semester',
            'total_marks',
        ]


# ===================== QUESTION (student-safe: NO correct answer) =====================
class QuestionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question
        fields = [
            'id',
            'quiz',
            'text',
            'option1',
            'option2',
            'option3',
            'option4',
            'marks',
        ]


        # correct_answer is deliberately excluded so students can't see it


# ===================== QUESTION (teacher/admin: full, includes answer) =====================
class QuestionAdminSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question
        fields = '__all__'


# ===================== QUIZ =====================
class QuizSerializer(serializers.ModelSerializer):

    questions = QuestionSerializer(
        many=True,
        read_only=True
    )

    teacher_name = serializers.CharField(
        source='teaching_assignment.teacher.username',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='teaching_assignment.subject.name',
        read_only=True
    )

    course_name = serializers.CharField(
        source='teaching_assignment.course.name',
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
        model = Quiz

        fields = '__all__'

        read_only_fields = [
            'created_by',
            'created_at',
            'total_marks'
        ]


# ===================== QUIZ ATTEMPT =====================
class QuizAttemptSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source='student.username',
        read_only=True
    )

    quiz_title = serializers.CharField(
        source='quiz.title',
        read_only=True
    )

    class Meta:
        model = QuizAttempt

        fields = '__all__'

        read_only_fields = [
            'student',
            'score',
            'submitted_at'
        ]


# ===================== STUDY MATERIAL =====================
class StudyMaterialSerializer(
    serializers.ModelSerializer
):

    uploaded_by_name = serializers.CharField(
        source='uploaded_by.username',
        read_only=True
    )

    teacher_name = serializers.CharField(
        source='teaching_assignment.teacher.username',
        read_only=True
    )

    subject_name = serializers.CharField(
        source='teaching_assignment.subject.name',
        read_only=True
    )

    course_name = serializers.CharField(
        source='teaching_assignment.course.name',
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

        model = StudyMaterial

        fields = '__all__'

        read_only_fields = [
            'uploaded_by',
            'created_at'
        ]


# ===================== DISCUSSION MESSAGE =====================
class DiscussionMessageSerializer(serializers.ModelSerializer):

    user_name = serializers.CharField(
        source='user.username',
        read_only=True
    )

    class Meta:

        model = DiscussionMessage

        fields = [
            'id',
            'teaching_assignment',
            'user',
            'user_name',
            'message',
            'created_at'
        ]

        read_only_fields = [
            'user',
            'user_name',
            'created_at'
        ]


class FeedbackSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source="student.username",
        read_only=True
    )

    teacher_name = serializers.CharField(
        source="teacher.username",
        read_only=True
    )

    subject = serializers.CharField(
        source="teaching_assignment.subject.name",
        read_only=True
    )

    class Meta:
        model = Feedback

        fields = [
            "id",
            "teaching_assignment",
            "student",
            "teacher",
            "student_name",
            "teacher_name",
            "subject",
            "message",
            "rating",
            "direction",
            "is_anonymous",
            "created_at",
        ]

        read_only_fields = [
            "teacher",
            "student",
            "direction",
            "created_at",
        ]


# ===================== MATERIAL FOLDER =====================
class MaterialFolderSerializer(serializers.ModelSerializer):
 
    created_by_name = serializers.CharField(
        source="created_by.username",
        read_only=True
    )
 
    # how many files are inside this folder (for the folder card)
    file_count = serializers.IntegerField(
        source="materials.count",
        read_only=True
    )
 
    class Meta:
        model = MaterialFolder
        fields = [
            "id",
            "name",
            "teaching_assignment",
            "created_by",
            "created_by_name",
            "file_count",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]
