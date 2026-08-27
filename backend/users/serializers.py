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

    # ---- profile ----
    # WRITE: the frontend sends a single "profile" object with the detail
    #        fields (address, dob, qualification, etc.).
    # READ:  "profile_data" returns that user's profile back.
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
            from courses.services import enroll_student
            enroll_student(user)

        return user
   # ================= UPDATE USER =================
    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password', None)

        # remember the class this student was in BEFORE the edit
        was_class = (instance.course_id, instance.year, instance.semester)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        # ---- re-enroll a student whose class changed ----
        # Enrollment rows are what give a subject group its audience. They are
        # created on student creation, CSV import, promotion and new subject
        # assignment — nothing created them when an existing student was edited
        # into another year or semester, so their subject groups came up empty.
        # Add-only, exactly like the promotion flow: old rows are kept.
        if instance.role == 'student':
            now_class = (instance.course_id, instance.year, instance.semester)
            if now_class != was_class:
                from courses.services import enroll_student
                enroll_student(instance)

        if profile_data is not None:
            self._save_profile(instance, profile_data)

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
        ]
        extra_kwargs = {
            'faculty': {'read_only': True},
            'proof': {'write_only': True, 'required': False},
        }

    def get_proof_url(self, obj):
        if not obj.proof:
            return None
        request = self.context.get('request')
        url = obj.proof.url
        return request.build_absolute_uri(url) if request else url