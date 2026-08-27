from rest_framework import serializers
from .models import *


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

    class Meta:
        model = Subject

        fields = ['id', 'name', 'code', 'credits', 'weekly_hours','is_elective','year', 'semester', 'year_number', 'course_name', 'department', 'department_name']
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
# ===================== ENROLLMENT =====================
class EnrollmentSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source='student.username',
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


# ===================== NOTIFICATION =====================
class NotificationSerializer(serializers.ModelSerializer):

    recipient_name = serializers.CharField(
        source='recipient.username',
        read_only=True
    )

    class Meta:

        model = Notification

        fields = '__all__'

        read_only_fields = [
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


# ===================== FEE =====================
class FeeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source='student.username', read_only=True)
    department = serializers.SerializerMethodField()
    pending_amount = serializers.SerializerMethodField()

    def get_department(self, obj):
        course = getattr(obj.student, 'course', None)
        return course.name if course else None

    def get_pending_amount(self, obj):
        return float(obj.amount) - float(obj.paid_amount)

    class Meta:
        model = Fee
        fields = ['id', 'student', 'student_name', 'department', 'term',
                  'amount', 'paid_amount', 'pending_amount',
                  'due_date', 'paid_date', 'status', 'created_at']
        read_only_fields = ['created_at']

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
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = ConversationMessage
        fields = ['id', 'sender', 'sender_name', 'receiver',
                  'receiver_name', 'text', 'is_read', 'created_at',
                  'attachment_url', 'attachment_name', 'attachment_size']
        read_only_fields = ['sender', 'created_at',
                            'attachment_name', 'attachment_size']

    def get_attachment_url(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get('request')
        url = obj.attachment.url
        return request.build_absolute_uri(url) if request else url      

