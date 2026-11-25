from rest_framework import serializers

from .models import (
    User,
    Department,
    FacultyParticipation,
    StudentProfile,
    FacultyProfile,
    ParentProfile,
)


# ================= DEPARTMENT =================
class DepartmentSerializer(serializers.ModelSerializer):

    hod_name = serializers.CharField(
        source='hod.username',
        read_only=True
    )

    class Meta:
        model = Department
        fields = ['id', 'name', 'hod', 'hod_name']


# ================= PROFILE SERIALIZERS =================

class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        exclude = ['id', 'user']


class FacultyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacultyProfile
        exclude = ['id', 'user']


class ParentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParentProfile
        exclude = ['id', 'user']


# ================= USER =================
class UserSerializer(serializers.ModelSerializer):

    # ---- read-only display helpers ----
    department_name = serializers.CharField(source='department.name', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)
    department_code = serializers.SerializerMethodField()
    role_label = serializers.CharField(source='get_role_display', read_only=True)
    sub_role_label = serializers.CharField(source='get_sub_role_display', read_only=True)

    profile = serializers.DictField(write_only=True, required=False)
    profile_data = serializers.SerializerMethodField()

    # which main role uses which profile table
    PROFILE_MODEL = {
        'student': StudentProfile,
        'teacher': FacultyProfile,
        'non_teaching': FacultyProfile,
    }

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'password',
            'email',
            'role',
            'role_label',
            'sub_role',
            'sub_role_label',
            'department',
            'department_name',
            'department_code',
            'course',
            'course_name',
            'roll_number',
            'employee_id',
            'year',
            'semester',
            'batch_year',
            'is_active',
            'profile',
            'profile_data',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'email': {'required': True},
            'roll_number': {'read_only': True},
            'employee_id': {'read_only': True},
        }

    # ================= DEPARTMENT CODE =================
    def get_department_code(self, obj):
        if obj.department:
            return obj.department.name[:3].upper()
        return ""


    # ================= PROFILE READ =================
    def get_profile_data(self, obj):
        if obj.role == 'student' and hasattr(obj, 'student_profile'):
            data = StudentProfileSerializer(obj.student_profile).data

            # guardian details live on the linked parent, not the student -
            # merge them back so the Edit form (Step 4) can pre-fill.
            # ParentProfile.children has related_name='parents', so the
            # reverse accessor from a student returns ParentProfile objects.
            parent_profile = obj.parents.first()
            if parent_profile:
                parent_user = parent_profile.user
                data['guardian_email'] = parent_user.email or parent_user.username
                data['guardian_name']  = parent_user.username
                data['guardian_phone'] = parent_profile.phone
                data['occupation']     = parent_profile.occupation
                data['relation']       = parent_profile.relation
            return data

        if obj.role in ('teacher', 'non_teaching') and hasattr(obj, 'faculty_profile'):
            return FacultyProfileSerializer(obj.faculty_profile).data
        if obj.role == 'parent' and hasattr(obj, 'parent_profile'):
            return ParentProfileSerializer(obj.parent_profile).data
        return None

    # ================= VALIDATE USERNAME =================
    def validate_username(self, value):
        if not value:
            raise serializers.ValidationError("Username is required")
        return value

    # ================= VALIDATE EMAIL =================
    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Email is required")

        user = self.instance
        qs = User.objects.filter(email=value)
        if user:
            qs = qs.exclude(id=user.id)
        if qs.exists():
            raise serializers.ValidationError("Email already exists")
        return value

    # ================= VALIDATE ROLE =================
    def validate_role(self, value):
        valid_roles = ['student', 'teacher', 'admin', 'non_teaching', 'parent']
        if value not in valid_roles:
            raise serializers.ValidationError("Invalid role")
        return value

    # ================= PROFILE SAVE HELPER =================
    def _save_profile(self, user, profile_data):
        model_cls = self.PROFILE_MODEL.get(user.role)
        if model_cls is None:
            # admins and parents don't use these detail tables here
            return
        if not profile_data:
            return

        # keep only real fields of the model, drop anything unexpected
        valid_fields = {f.name for f in model_cls._meta.get_fields()}
        clean = {
            k: v for k, v in profile_data.items()
            if k in valid_fields and k not in ('id', 'user')
        }

        obj, _ = model_cls.objects.get_or_create(user=user)
        for attr, value in clean.items():
            setattr(obj, attr, value)
        obj.save()

    # ================= CREATE USER =================
    def create(self, validated_data):
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password', None)

        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_password(User.objects.make_random_password())
        user.save()   # roll number / employee id auto-generate here

        self._save_profile(user, profile_data)

        # ---- auto-create / link a parent for students ----
        if user.role == 'student' and profile_data:
            guardian_email = profile_data.get('guardian_email', '')
            if guardian_email:
                from .views import create_or_link_parent
                create_or_link_parent(
                    student=user,
                    guardian_name=profile_data.get('father_name') or profile_data.get('mother_name') or '',
                    guardian_email=guardian_email,
                    guardian_phone=profile_data.get('guardian_phone', ''),
                    occupation=profile_data.get('occupation', ''),
                    relation=profile_data.get('relation', ''),
                )

        # ---- auto-enroll a new student into their course-semester subjects ----
        if user.role == 'student':
            from core.academics.services import enroll_student
            enroll_student(user)

        return user
      # ================= UPDATE USER =================
    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password', None)

        # Remember where this student was BEFORE the edit. create() enrolls a
        # new student into their course-semester subjects; update() did not,
        # so moving a student to another year left them in the class group
        # with no subjects at all - no assignments, materials or attendance.
        was_student = instance.role == 'student'
        old_placement = (instance.course_id, instance.year, instance.semester)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        if profile_data is not None:
            self._save_profile(instance, profile_data)

        # ---- re-enroll when a student's placement changes ----
        # Only on an actual move: enroll_student uses get_or_create, so calling
        # it every save would be harmless but pointless, and the delete below
        # is not something to run on an unrelated edit like a phone number.
        new_placement = (instance.course_id, instance.year, instance.semester)
        if instance.role == 'student' and new_placement != old_placement:
            from core.academics.models import Enrollment
            from core.academics.services import enroll_student

            # Drop subjects from the class they left. enroll_student only ever
            # ADDS, so without this a moved student keeps both years' subjects
            # and sees a timetable belonging to two classes at once.
            # Nothing has a foreign key to Enrollment, so removing a row takes
            # no attendance or submission history with it.
            if instance.course_id and instance.year and instance.semester:
                Enrollment.objects.filter(student=instance).exclude(
                    teaching_assignment__course_id=instance.course_id,
                    teaching_assignment__year__year_number=instance.year,
                    teaching_assignment__subject__semester=instance.semester,
                ).delete()

            enroll_student(instance)

        # A user who stops being a student keeps no enrollments.
        elif was_student and instance.role != 'student':
            from core.academics.models import Enrollment
            Enrollment.objects.filter(student=instance).delete()

        # ---- auto-link a parent ONLY if this student has none yet ----
        # Students who already have a linked parent are left untouched
        # (no duplicates, existing link not disturbed).
        if instance.role == 'student' and profile_data:
            if not instance.parents.exists():
                guardian_email = profile_data.get('guardian_email', '')
                if guardian_email:
                    from .views import create_or_link_parent
                    create_or_link_parent(
                        student=instance,
                        guardian_name=profile_data.get('father_name') or profile_data.get('mother_name') or '',
                        guardian_email=guardian_email,
                        guardian_phone=profile_data.get('guardian_phone', ''),
                        occupation=profile_data.get('occupation', ''),
                        relation=profile_data.get('relation', ''),
                    )

        return instance
    
# ================= FACULTY PARTICIPATION (IQAC) =================
class FacultyParticipationSerializer(serializers.ModelSerializer):

    # read-only display helpers
    faculty_name = serializers.CharField(source='faculty.username', read_only=True)
    employee_id = serializers.CharField(source='faculty.employee_id', read_only=True)
    department_name = serializers.CharField(source='faculty.department.name', read_only=True)
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    role_label = serializers.CharField(source='get_activity_role_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)     # HRIS PART B
    verified_by_name = serializers.SerializerMethodField()                                 # HRIS PART B
    proof_url = serializers.SerializerMethodField()

    class Meta:
        model = FacultyParticipation
        fields = [
            'id',
            'faculty',
            'faculty_name',
            'employee_id',
            'department_name',
            'category',
            'category_label',
            'title',
            'organizer',
            'activity_role',
            'role_label',
            'date',
            'academic_year',
            'proof',
            'proof_url',
            'remarks',
            'created_at',
            # HRIS PART B
            'details',
            'indexing',
            'amount_lakhs',
            'status',
            'status_label',
            'review_note',
            'verified_by_name',
            'verified_at',
        ]
        read_only_fields = ['status', 'review_note', 'verified_at']
        extra_kwargs = {
            'faculty': {'read_only': True},
            'proof': {'write_only': True, 'required': False},
        }

    def get_verified_by_name(self, obj):
        u = obj.verified_by
        return ((u.get_full_name() or '').strip() or u.username) if u else ''

    def validate_amount_lakhs(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Enter the amount in lakhs (0 or more).')
        return value

    def get_proof_url(self, obj):
        if not obj.proof:
            return None
        request = self.context.get('request')
        url = obj.proof.url
        return request.build_absolute_uri(url) if request else url