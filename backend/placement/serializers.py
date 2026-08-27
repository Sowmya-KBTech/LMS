from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from users.models import User, Department, PriorAcademics

from .models import (
    PlacementCoordinator,
    Company,
    Drive,
    JobRole,
    EligibilityRule,
    Application,
    DriveAttendance,
    Offer,
)


# ===================== PLACEMENT COORDINATOR =====================
class PlacementCoordinatorSerializer(serializers.ModelSerializer):

    teacher_name = serializers.CharField(
        source="teacher.username",
        read_only=True,
    )

    teacher_employee_id = serializers.CharField(
        source="teacher.employee_id",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
    )

    department_code = serializers.CharField(
        source="department.code",
        read_only=True,
    )

    assigned_by_name = serializers.CharField(
        source="assigned_by.username",
        read_only=True,
    )

    class Meta:
        model = PlacementCoordinator
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "teacher_employee_id",
            "department",
            "department_name",
            "department_code",
            "is_active",
            "assigned_at",
            "assigned_by",
            "assigned_by_name",
        ]
        # assigned_by is set server-side from request.user -- never accepted
        # from the client, same rule as class_section on teaching plans.
        read_only_fields = ["assigned_at", "assigned_by"]

    def validate(self, attrs):
        """
        Reject a second active coordinator for a department with a readable
        message, instead of letting the DB constraint raise a 500.
        """
        teacher = attrs.get("teacher") or getattr(self.instance, "teacher", None)
        department = attrs.get("department") or getattr(
            self.instance, "department", None
        )
        is_active = attrs.get(
            "is_active",
            getattr(self.instance, "is_active", True),
        )

        if teacher and teacher.role != "teacher":
            raise serializers.ValidationError(
                {"teacher": "Only a teacher can be a placement coordinator."}
            )

        if is_active and department:
            clash = PlacementCoordinator.objects.filter(
                department=department,
                is_active=True,
            )
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)

            existing = clash.first()
            if existing:
                raise serializers.ValidationError({
                    "department": (
                        f"{department.name} already has an active coordinator "
                        f"({existing.teacher.username}). Deactivate that "
                        f"assignment first."
                    )
                })

        return attrs


# ===================== TEACHER PICKER (for the assign dropdown) =====================
class TeacherLiteSerializer(serializers.ModelSerializer):

    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
    )

    class Meta:
        model = User
        fields = ["id", "username", "employee_id", "department", "department_name"]
        read_only_fields = fields


# ===================== DEPARTMENT PICKER =====================
class DepartmentLiteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Department
        fields = ["id", "name", "code"]
        read_only_fields = fields


# ===================== PRIOR ACADEMICS (STUDENT — OWN RECORD) =====================
class MyAcademicsSerializer(serializers.ModelSerializer):
    """
    The student's own 10th / 12th / diploma record.

    `verified`, `verified_by` and `verified_at` are READ ONLY here. If a
    student could set verified=True on their own record, the coordinator's
    verification step would be decoration -- anyone could type 95% and tick
    their own box.
    """

    qualifying_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )

    verified_by_name = serializers.CharField(
        source="verified_by.username",
        read_only=True,
    )

    class Meta:
        model = PriorAcademics
        fields = [
            "id",
            # 10th
            "tenth_percent",
            "tenth_board",
            "tenth_year",
            # lateral entry
            "is_lateral_entry",
            # 12th
            "twelfth_percent",
            "twelfth_board",
            "twelfth_year",
            # diploma
            "diploma_percent",
            "diploma_branch",
            "diploma_year",
            # derived
            "qualifying_percent",
            # verification (read only for the student)
            "verified",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "updated_at",
        ]
        read_only_fields = [
            "verified",
            "verified_by",
            "verified_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """
        Run the model's own rule rather than repeating it here.

        PriorAcademics.clean() decides which qualification is required based
        on is_lateral_entry. Re-implementing that check in the serializer
        would give two versions of the same rule, and they would drift.
        """
        instance = self.instance or PriorAcademics()

        for field, value in attrs.items():
            setattr(instance, field, value)

        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)

        return attrs

    def validate_tenth_percent(self, value):
        if value is None:
            raise serializers.ValidationError("10th percentage is required.")
        return value


# ===================== PRIOR ACADEMICS (COORDINATOR — VERIFY) =====================
class StudentAcademicsSerializer(serializers.ModelSerializer):
    """
    One student's record as the coordinator sees it on the verification list.

    Read only. Verification is done through a dedicated endpoint rather than
    a PATCH on this serializer, so `verified` can never be set by accident
    alongside an unrelated field update.
    """

    student_name = serializers.CharField(
        source="student.username",
        read_only=True,
    )

    roll_number = serializers.CharField(
        source="student.roll_number",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="student.department.name",
        read_only=True,
    )

    qualifying_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )

    verified_by_name = serializers.CharField(
        source="verified_by.username",
        read_only=True,
    )

    class Meta:
        model = PriorAcademics
        fields = [
            "id",
            "student",
            "student_name",
            "roll_number",
            "department_name",
            "tenth_percent",
            "tenth_board",
            "tenth_year",
            "is_lateral_entry",
            "twelfth_percent",
            "twelfth_board",
            "twelfth_year",
            "diploma_percent",
            "diploma_branch",
            "diploma_year",
            "qualifying_percent",
            "verified",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "updated_at",
        ]
        read_only_fields = fields


# ===================== COMPANY =====================
class CompanySerializer(serializers.ModelSerializer):

    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )

    created_by_name = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "category",
            "category_display",
            "website",
            "about",
            "contact_person",
            "contact_email",
            "contact_phone",
            "is_active",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        # created_by is taken from request.user in the view -- never accepted
        # from the payload, same rule as assigned_by on coordinators.
        read_only_fields = ["created_by", "created_at"]

    def validate_name(self, value):
        """
        Names are compared case-insensitively so "Zoho" and "zoho" cannot both
        be created. The DB unique constraint is case-SENSITIVE on PostgreSQL,
        so without this check both would save and the drive list would show
        what looks like two companies.
        """
        name = (value or "").strip()

        if not name:
            raise serializers.ValidationError("Company name is required.")

        clash = Company.objects.filter(name__iexact=name)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)

        existing = clash.first()
        if existing:
            raise serializers.ValidationError(
                f"{existing.name} is already on the list."
            )

        return name


# ===================== ELIGIBILITY RULE =====================
class EligibilityRuleSerializer(serializers.ModelSerializer):

    allowed_department_names = serializers.SerializerMethodField()

    class Meta:
        model = EligibilityRule
        fields = [
            "id",
            "job_role",
            "min_cgpa",
            "max_arrears",
            "min_tenth_percent",
            "min_twelfth_percent",
            "allowed_departments",
            "allowed_department_names",
            "passing_year",
            "allow_lateral_entry",
            # A student holding an ACCEPTED offer at or above this package
            # cannot apply. Null means no cap.
            "placed_package_cap",
            "notes",
        ]
        read_only_fields = ["job_role"]

    def get_allowed_department_names(self, obj):
        # reads the model's own helper, so "empty means all branches" is
        # defined once and the API, the form and the service all agree
        return obj.allowed_department_names()


# ===================== JOB ROLE =====================
class JobRoleSerializer(serializers.ModelSerializer):

    eligibility = EligibilityRuleSerializer(read_only=True)

    # is_open is a model PROPERTY: the role is active AND its drive is open.
    # Exposed read-only so no screen re-derives "can I apply now" for itself.
    is_open = serializers.BooleanField(read_only=True)

    company_name = serializers.CharField(
        source="drive.company.name",
        read_only=True,
    )

    class Meta:
        model = JobRole
        fields = [
            "id",
            "drive",
            "company_name",
            "title",
            "package_lpa",
            "job_location",
            "bond_details",
            "description",
            "openings",
            "is_active",
            "is_open",
            "eligibility",
            "created_at",
        ]
        read_only_fields = ["created_at"]


# ===================== DRIVE =====================
class DriveSerializer(serializers.ModelSerializer):

    company_name = serializers.CharField(
        source="company.name",
        read_only=True,
    )

    company_category = serializers.CharField(
        source="company.get_category_display",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    is_open = serializers.BooleanField(read_only=True)

    # The positions on offer. A drive with one role is just a list of one --
    # no special case anywhere.
    job_roles = JobRoleSerializer(many=True, read_only=True)

    created_by_name = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = Drive
        fields = [
            "id",
            "company",
            "company_name",
            "company_category",
            "title",
            "description",
            "application_deadline",
            "drive_date",
            "status",
            "status_display",
            "is_open",
            "job_roles",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

    def validate_company(self, value):
        """
        An inactive company has stopped recruiting -- creating a new drive for
        one is almost always a mistake made by picking the wrong row from a
        long dropdown.
        """
        if not value.is_active:
            raise serializers.ValidationError(
                f"{value.name} is marked inactive. Reactivate it first."
            )
        return value

    def validate(self, attrs):
        """
        The deadline must fall on or before the drive date. A deadline AFTER
        the drive would let a student apply to something already held, and the
        error would only surface as an empty applicant list on the day.
        """
        deadline = attrs.get(
            "application_deadline",
            getattr(self.instance, "application_deadline", None),
        )
        drive_date = attrs.get(
            "drive_date",
            getattr(self.instance, "drive_date", None),
        )

        if deadline and drive_date and deadline.date() > drive_date:
            raise serializers.ValidationError({
                "application_deadline": (
                    "Applications must close on or before the drive date."
                )
            })

        return attrs


# ===================== JOB ROLE (STUDENT VIEW) =====================
class StudentJobRoleSerializer(serializers.ModelSerializer):
    """
    A role as a student sees it.

    NARROWER than JobRoleSerializer on purpose: no eligibility rule. Students
    receive their own computed RESULT (eligible + reasons), never the raw
    cutoffs -- otherwise the whole batch could read every company's bar.
    """

    class Meta:
        model = JobRole
        fields = [
            "id",
            "title",
            "package_lpa",
            "job_location",
            "bond_details",
            "description",
            "openings",
        ]
        read_only_fields = fields


# ===================== DRIVE (STUDENT VIEW) =====================
class StudentDriveSerializer(serializers.ModelSerializer):
    """
    A drive as a student sees it.

    No created_by, no status, no eligibility rules. Reusing DriveSerializer
    here would leak who set the drive up and let a student read cutoffs for
    roles they cannot see.
    """

    company_name = serializers.CharField(source="company.name", read_only=True)
    company_category = serializers.CharField(
        source="company.get_category_display",
        read_only=True,
    )
    company_website = serializers.CharField(source="company.website", read_only=True)

    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Drive
        fields = [
            "id",
            "company_name",
            "company_category",
            "company_website",
            "title",
            "description",
            "application_deadline",
            "drive_date",
            "is_open",
        ]
        read_only_fields = fields


# ===================== APPLICATION (STUDENT) =====================
class ApplicationSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    role_title = serializers.CharField(
        source="job_role.title",
        read_only=True,
    )

    company_name = serializers.CharField(
        source="job_role.drive.company.name",
        read_only=True,
    )

    package_lpa = serializers.DecimalField(
        source="job_role.package_lpa",
        max_digits=6,
        decimal_places=2,
        read_only=True,
    )

    drive_id = serializers.IntegerField(
        source="job_role.drive.id",
        read_only=True,
    )

    class Meta:
        model = Application
        fields = [
            "id",
            "student",
            "job_role",
            "role_title",
            "company_name",
            "package_lpa",
            "drive_id",
            "status",
            "status_display",
            "opt_out_reason",
            "applied_at",
            "updated_at",
        ]
        # student is taken from request.user, never the payload -- otherwise
        # one student could apply on another's behalf.
        # eligibility_snapshot is written server-side at apply time.
        read_only_fields = ["student", "applied_at", "updated_at"]

    def validate(self, attrs):
        """
        A reason is REQUIRED when opting out.

        Without it the "Skipped" tab lists names and nothing else, and
        chasing students who quietly ignored a drive is most of what a
        placement cell does.
        """
        status_value = attrs.get(
            "status",
            getattr(self.instance, "status", "applied"),
        )
        reason = attrs.get(
            "opt_out_reason",
            getattr(self.instance, "opt_out_reason", ""),
        )

        if status_value == "opted_out" and not (reason or "").strip():
            raise serializers.ValidationError({
                "opt_out_reason": "Please say why you are not interested."
            })

        return attrs


# ===================== APPLICATION (STAFF) =====================
class StaffApplicationSerializer(serializers.ModelSerializer):
    """
    An application as the officer or coordinator sees it.

    Carries the student's identity, which the student-facing serializer does
    not need, and the eligibility snapshot taken when they applied.
    """

    student_name = serializers.CharField(
        source="student.username",
        read_only=True,
    )

    roll_number = serializers.CharField(
        source="student.roll_number",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="student.department.name",
        read_only=True,
    )

    role_title = serializers.CharField(
        source="job_role.title",
        read_only=True,
    )

    company_name = serializers.CharField(
        source="job_role.drive.company.name",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Application
        fields = [
            "id",
            "student",
            "student_name",
            "roll_number",
            "department_name",
            "job_role",
            "role_title",
            "company_name",
            "status",
            "status_display",
            "opt_out_reason",
            # What was true when they applied -- NOT what is true now. A
            # revaluation weeks later can change live eligibility, and this is
            # the record of why they were accepted at the time.
            "eligibility_snapshot",
            "applied_at",
            "updated_at",
        ]
        read_only_fields = fields


# ===================== DRIVE ATTENDANCE =====================
class DriveAttendanceSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source="application.student.username",
        read_only=True,
    )

    roll_number = serializers.CharField(
        source="application.student.roll_number",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="application.student.department.name",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    marked_by_name = serializers.CharField(
        source="marked_by.username",
        read_only=True,
    )

    # Whether an OD exists, not the OD itself. The coordinator needs to know
    # the student's classes were covered; the OD's own fields are the
    # attendance module's business.
    od_created = serializers.SerializerMethodField()

    class Meta:
        model = DriveAttendance
        fields = [
            "id",
            "application",
            "student_name",
            "roll_number",
            "department_name",
            "status",
            "status_display",
            "remarks",
            "od_created",
            "marked_by",
            "marked_by_name",
            "marked_at",
        ]
        read_only_fields = ["marked_by", "marked_at"]

    def get_od_created(self, obj):
        return obj.od_request_id is not None


# ===================== OFFER (STAFF) =====================
class OfferSerializer(serializers.ModelSerializer):

    student_name = serializers.CharField(
        source="application.student.username",
        read_only=True,
    )

    roll_number = serializers.CharField(
        source="application.student.roll_number",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="application.student.department.name",
        read_only=True,
    )

    company_name = serializers.CharField(
        source="application.job_role.drive.company.name",
        read_only=True,
    )

    role_title = serializers.CharField(
        source="application.job_role.title",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    recorded_by_name = serializers.CharField(
        source="recorded_by.username",
        read_only=True,
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "application",
            "student_name",
            "roll_number",
            "department_name",
            "company_name",
            "role_title",
            "package_lpa",
            "offer_letter",
            "joining_date",
            "status",
            "status_display",
            "remarks",
            "offered_on",
            "decided_at",
            "recorded_by",
            "recorded_by_name",
        ]
        # decided_at is stamped server-side when the STUDENT answers, never
        # sent by the officer recording the offer.
        read_only_fields = ["recorded_by", "decided_at"]


# ===================== OFFER (STUDENT) =====================
class StudentOfferSerializer(serializers.ModelSerializer):
    """
    A student's own offers.

    Accepting or declining goes through a dedicated endpoint, not a PATCH on
    this serializer -- so `status` stays read-only here and cannot be changed
    alongside an unrelated field.
    """

    company_name = serializers.CharField(
        source="application.job_role.drive.company.name",
        read_only=True,
    )

    role_title = serializers.CharField(
        source="application.job_role.title",
        read_only=True,
    )

    job_location = serializers.CharField(
        source="application.job_role.job_location",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "company_name",
            "role_title",
            "job_location",
            "package_lpa",
            "offer_letter",
            "joining_date",
            "status",
            "status_display",
            "remarks",
            "offered_on",
            "decided_at",
        ]
        read_only_fields = fields