from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from exams.services import get_academic_standing

from users.models import User, Department, PriorAcademics

from .eligibility import check_eligibility
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
from .permissions import (
    can_manage_placement,
    can_view_placement_staff,
    coordinator_department,
    is_placement_coordinator,
    is_placement_officer,
    is_placement_student,
    is_super_admin,
    scope_students_for,
)
from .serializers import (
    ApplicationSerializer,
    CompanySerializer,
    DepartmentLiteSerializer,
    DriveAttendanceSerializer,
    DriveSerializer,
    EligibilityRuleSerializer,
    JobRoleSerializer,
    MyAcademicsSerializer,
    OfferSerializer,
    PlacementCoordinatorSerializer,
    StaffApplicationSerializer,
    StudentAcademicsSerializer,
    StudentDriveSerializer,
    StudentJobRoleSerializer,
    StudentOfferSerializer,
    TeacherLiteSerializer,
)
from .services import create_drive_od, cancel_drive_od


# ===================== WHO AM I (placement context) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def placement_me(request):
    """
    What this user is allowed to do in placement, and which department they
    are scoped to.

    The frontend calls this once on load to decide which portal to show, so
    the sidebar and route guards read from the SAME rules the API enforces.
    """
    user = request.user
    department = coordinator_department(user)

    return Response({
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "sub_role": user.sub_role,
        "is_placement_officer": is_placement_officer(user),
        "is_placement_coordinator": is_placement_coordinator(user),
        "is_super_admin": is_super_admin(user),
        "can_manage_placement": can_manage_placement(user),
        "can_view_placement_staff": can_view_placement_staff(user),
        "department_id": department.id if department else None,
        "department_name": department.name if department else None,
        "department_code": department.code if department else None,
    })


# ===================== COORDINATOR LIST / CREATE =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def coordinator_list(request):
    """
    GET  -> list coordinator assignments
    POST -> assign a teacher as coordinator for a department
    """
    user = request.user

    if request.method == "GET":

        if not can_view_placement_staff(user):
            return Response(
                {"detail": "Not allowed."},
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = (
            PlacementCoordinator.objects
            .select_related("teacher", "department", "assigned_by")
        )

        active = request.query_params.get("active")
        if active == "true":
            queryset = queryset.filter(is_active=True)
        elif active == "false":
            queryset = queryset.filter(is_active=False)

        return Response(PlacementCoordinatorSerializer(queryset, many=True).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can assign coordinators."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = PlacementCoordinatorSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # assigned_by comes from the request, never from the payload
    serializer.save(assigned_by=user)

    return Response(serializer.data, status=status.HTTP_201_CREATED)


# ===================== COORDINATOR DETAIL =====================
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def coordinator_detail(request, pk):
    """
    PATCH  -> update an assignment (usually is_active = false to end it)
    DELETE -> deactivate, NOT remove

    Soft delete: once drives and applications reference a coordinator's
    actions, removing the row would orphan that history.
    """
    user = request.user

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can change coordinators."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        assignment = PlacementCoordinator.objects.get(pk=pk)
    except PlacementCoordinator.DoesNotExist:
        return Response(
            {"detail": "Assignment not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        return Response({"detail": "Coordinator assignment deactivated."})

    serializer = PlacementCoordinatorSerializer(
        assignment, data=request.data, partial=True,
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response(serializer.data)


# ===================== TEACHER PICKER =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assignable_teachers(request):
    """Teachers who can be made coordinators, for the assign dropdown."""
    user = request.user

    if not can_manage_placement(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    queryset = (
        User.objects
        .filter(role="teacher")
        .select_related("department")
        .order_by("username")
    )

    department_id = request.query_params.get("department")
    if department_id:
        queryset = queryset.filter(department_id=department_id)

    return Response(TeacherLiteSerializer(queryset, many=True).data)


# ===================== PLACEMENT DEPARTMENTS =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def placement_departments(request):
    """
    Departments that actually admit students.

    Service departments (Mathematics, Physics, Tamil...) own subjects but have
    no students of their own, so they must never appear as a placement branch.
    Tested by whether any student belongs to them -- no extra flag to maintain.
    """
    if not can_view_placement_staff(request.user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    queryset = (
        Department.objects
        .filter(user__role="student")
        .distinct()
        .order_by("name")
    )

    return Response(DepartmentLiteSerializer(queryset, many=True).data)

# ===================== MY ACADEMICS (STUDENT) =====================
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def my_academics(request):
    """
    GET -> the student's own 10th / 12th / diploma record
    PUT -> create or update it

    The record is looked up from request.user, never from an id in the
    payload. Accepting a student id here would let any student read or
    overwrite another student's marks by changing one number.

    Editing an already-verified record CLEARS the verification. A student who
    could edit after approval could pass verification with real marks and then
    change them -- the coordinator's tick has to mean "these exact values were
    checked", not "this student was checked once".
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students have a placement profile."},
            status=status.HTTP_403_FORBIDDEN,
        )

    record = PriorAcademics.objects.filter(student=user).first()

    if request.method == "GET":
        if not record:
            # No row yet. Return an empty shape rather than a 404 so the form
            # can render blank fields instead of handling an error path.
            return Response({
                "exists": False,
                "verified": False,
                "is_lateral_entry": False,
            })

        data = MyAcademicsSerializer(record).data
        data["exists"] = True
        return Response(data)

    # ---------------- WRITE ----------------
    was_verified = bool(record and record.verified)

    serializer = MyAcademicsSerializer(record, data=request.data, partial=bool(record))
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    saved = serializer.save(student=user)

    # any edit after verification sends it back for re-checking
    if was_verified:
        saved.verified = False
        saved.verified_by = None
        saved.verified_at = None
        saved.save(update_fields=["verified", "verified_by", "verified_at"])

    data = MyAcademicsSerializer(saved).data
    data["exists"] = True
    data["verification_reset"] = was_verified

    return Response(data, status=status.HTTP_200_OK)


# ===================== VERIFICATION LIST (COORDINATOR) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def academics_verification_list(request):
    """
    Students the caller may verify, with whatever each has entered.

    Scoped through scope_students_for() -- the same function every other
    coordinator screen uses -- so a coordinator sees only their own
    department and the officer sees everyone.

    Students with NO record are included, marked has_record=False. Leaving
    them out would hide exactly the students who need chasing.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    students = scope_students_for(
        user,
        User.objects.filter(role="student"),
    ).select_related("department").order_by("roll_number")

    records = {
        r.student_id: r
        for r in PriorAcademics.objects.filter(student__in=students)
        .select_related("student", "student__department", "verified_by")
    }

    wanted = request.query_params.get("status")

    rows = []
    counts = {"verified": 0, "pending": 0, "missing": 0}

    for student in students:
        record = records.get(student.id)

        if record is None:
            state = "missing"
        elif record.verified:
            state = "verified"
        else:
            state = "pending"

        counts[state] += 1

        if wanted and wanted != state:
            continue

        if record is None:
            rows.append({
                "id": None,
                "student": student.id,
                "student_name": student.username,
                "roll_number": student.roll_number,
                "department_name": (
                    student.department.name if student.department else None
                ),
                "has_record": False,
                "state": "missing",
                "verified": False,
            })
        else:
            row = StudentAcademicsSerializer(record).data
            row["has_record"] = True
            row["state"] = state
            rows.append(row)

    return Response({
        "counts": counts,
        "total": students.count(),
        "results": rows,
    })


# ===================== VERIFY ONE STUDENT (COORDINATOR) =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_academics(request, student_id):
    """
    Mark one student's record verified, or send it back.

    Body: {"verified": true} or {"verified": false}

    The student is re-checked through scope_students_for() rather than
    trusted from the URL -- otherwise a coordinator could verify any student
    in the college by typing a different id.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    allowed = scope_students_for(user, User.objects.filter(role="student"))

    student = allowed.filter(pk=student_id).first()
    if not student:
        # same message whether the student does not exist or is out of scope,
        # so this cannot be used to discover who is in another department
        return Response(
            {"detail": "Student not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    record = PriorAcademics.objects.filter(student=student).first()
    if not record:
        return Response(
            {"detail": "This student has not entered their academic details yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    verified = request.data.get("verified", True)

    if verified:
        if record.tenth_percent is None or record.qualifying_percent is None:
            return Response(
                {"detail": "Record is incomplete -- ask the student to finish it first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record.verified = True
        record.verified_by = user
        record.verified_at = timezone.now()
    else:
        record.verified = False
        record.verified_by = None
        record.verified_at = None

    record.save(update_fields=["verified", "verified_by", "verified_at"])

    return Response(StudentAcademicsSerializer(record).data)


# ===================== COMPANY LIST / CREATE =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def company_list(request):
    """
    GET  -> list companies
    POST -> add a company

    Coordinators can READ the list but only the officer can add or change one.
    Companies are college-wide, so there is no department scoping here.
    """
    user = request.user

    if request.method == "GET":

        if not can_view_placement_staff(user):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        queryset = Company.objects.select_related("created_by")

        active = request.query_params.get("active")
        if active == "true":
            queryset = queryset.filter(is_active=True)
        elif active == "false":
            queryset = queryset.filter(is_active=False)

        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)

        search = request.query_params.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())

        return Response(CompanySerializer(queryset, many=True).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can add companies."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = CompanySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save(created_by=user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# ===================== COMPANY DETAIL =====================
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def company_detail(request, pk):
    """
    GET    -> one company
    PATCH  -> edit it
    DELETE -> deactivate, NOT remove

    Soft delete: once drives, applications and offers reference a company,
    removing the row would orphan a student's placement record -- the one
    piece of data they will still care about years later.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    company = Company.objects.filter(pk=pk).select_related("created_by").first()
    if not company:
        return Response({"detail": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(CompanySerializer(company).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can change companies."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        company.is_active = False
        company.save(update_fields=["is_active"])
        return Response({"detail": f"{company.name} marked inactive."})

    serializer = CompanySerializer(company, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response(serializer.data)


# ===================== COMPANY CATEGORIES =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def company_categories(request):
    """
    The category options, read from the model.

    Sent to the frontend rather than hardcoded in the dropdown, so adding a
    category means editing CATEGORY_CHOICES in one place instead of the model
    AND every form that offers it.
    """
    if not can_view_placement_staff(request.user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    return Response([
        {"value": value, "label": label}
        for value, label in Company.CATEGORY_CHOICES
    ])

# ===================== DRIVE LIST / CREATE =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def drive_list(request):
    """
    GET  -> drives with their roles, for staff
    POST -> create a drive (the visit only -- roles are added after)

    Drives are college-wide, so there is no department scoping on the drive
    itself -- who may APPLY is decided per student per ROLE by the
    eligibility rule.
    """
    user = request.user

    if request.method == "GET":

        if not can_view_placement_staff(user):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        queryset = (
            Drive.objects
            .select_related("company", "created_by")
            .prefetch_related("job_roles__eligibility__allowed_departments")
        )

        drive_status = request.query_params.get("status")
        if drive_status:
            queryset = queryset.filter(status=drive_status)

        company = request.query_params.get("company")
        if company:
            queryset = queryset.filter(company_id=company)

        # is_open is a PROPERTY, not a column, so it cannot be filtered in SQL.
        # Filtering in Python is fine -- a college runs tens of drives a year.
        drives = list(queryset)

        if request.query_params.get("open") == "true":
            drives = [d for d in drives if d.is_open]

        return Response(DriveSerializer(drives, many=True).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can create drives."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = DriveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    drive = serializer.save(created_by=user)
    return Response(DriveSerializer(drive).data, status=status.HTTP_201_CREATED)


# ===================== DRIVE DETAIL =====================
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def drive_detail(request, pk):
    """
    GET    -> one drive with its roles
    PATCH  -> edit it
    DELETE -> cancel, NOT remove

    Cancelling keeps applications and offers pointing at a real drive. A
    student who attended should still be able to see that they did.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    drive = (
        Drive.objects
        .select_related("company", "created_by")
        .prefetch_related("job_roles__eligibility__allowed_departments")
        .filter(pk=pk)
        .first()
    )
    if not drive:
        return Response({"detail": "Drive not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(DriveSerializer(drive).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can change drives."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        drive.status = "cancelled"
        drive.save(update_fields=["status"])
        return Response({"detail": f"{drive} cancelled."})

    serializer = DriveSerializer(drive, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response(DriveSerializer(drive).data)


# ===================== JOB ROLES =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def drive_job_roles(request, pk):
    """
    GET  -> the roles on offer in a drive
    POST -> add a role

    Every new role gets an eligibility row immediately, with everything null
    (= no limit). Without it the officer has to remember a second step, and a
    role with no rule row becomes a special case every screen must handle.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    drive = Drive.objects.filter(pk=pk).first()
    if not drive:
        return Response({"detail": "Drive not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        roles = drive.job_roles.select_related("drive__company").prefetch_related(
            "eligibility__allowed_departments"
        )
        return Response(JobRoleSerializer(roles, many=True).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can add roles."},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = dict(request.data)
    data["drive"] = drive.id

    serializer = JobRoleSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    role = serializer.save()
    EligibilityRule.objects.get_or_create(job_role=role)

    return Response(JobRoleSerializer(role).data, status=status.HTTP_201_CREATED)


# ===================== JOB ROLE DETAIL =====================
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def job_role_detail(request, role_id):
    """
    GET    -> one role with its eligibility
    PATCH  -> edit it
    DELETE -> deactivate, NOT remove

    Soft delete: applications point at a role, and removing it would orphan
    them.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = (
        JobRole.objects
        .select_related("drive__company")
        .prefetch_related("eligibility__allowed_departments")
        .filter(pk=role_id)
        .first()
    )
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(JobRoleSerializer(role).data)

    if not can_manage_placement(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "DELETE":
        role.is_active = False
        role.save(update_fields=["is_active"])
        return Response({"detail": f"{role.title} deactivated."})

    serializer = JobRoleSerializer(role, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response(JobRoleSerializer(role).data)


# ===================== ELIGIBILITY RULE =====================
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def role_eligibility(request, role_id):
    """
    GET   -> the rule for one ROLE
    PATCH -> edit the cutoffs

    allowed_departments is a M2M and must be sent as a list of ids. Sending []
    means every branch -- the "no limit" case, not an error.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = JobRole.objects.filter(pk=role_id).first()
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    rule, _ = EligibilityRule.objects.get_or_create(job_role=role)

    if request.method == "GET":
        return Response(EligibilityRuleSerializer(rule).data)

    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can change eligibility."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = EligibilityRuleSerializer(rule, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response(EligibilityRuleSerializer(rule).data)


# ===================== WHO MATCHES (LIVE COUNT) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def role_matches(request, role_id):
    """
    How many students meet this ROLE's rules right now, and why the rest fail.

    Computed live on every call -- never stored. A stored count would be wrong
    the moment a result is published, a mark is verified, or a cutoff changes.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = (
        JobRole.objects
        .select_related("drive")
        .prefetch_related("eligibility__allowed_departments")
        .filter(pk=role_id)
        .first()
    )
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    students = scope_students_for(
        user,
        User.objects.filter(role="student"),
    ).select_related("department", "prior_academics", "course")

    want_detail = request.query_params.get("detail") == "true"

    eligible = 0
    rows = []
    # Why students fail, aggregated. An officer setting a cutoff wants to know
    # "40 fail on CGPA, 12 have not verified" -- a bare count of 3 eligible
    # tells them nothing about which rule to relax.
    reasons = {}

    for student in students:
        result = check_eligibility(student, role)

        if result["eligible"]:
            eligible += 1
        else:
            for blocker in result["blockers"]:
                reasons[blocker] = reasons.get(blocker, 0) + 1

        if want_detail:
            rows.append({
                "student": student.id,
                "student_name": student.username,
                "roll_number": student.roll_number,
                "department_name": (
                    student.department.name if student.department else None
                ),
                "eligible": result["eligible"],
                "blockers": result["blockers"],
            })

    total = students.count()

    payload = {
        "job_role": role.id,
        "role_title": role.title,
        "total_students": total,
        "eligible": eligible,
        "not_eligible": total - eligible,
        "reasons": [
            {"reason": r, "count": c}
            for r, c in sorted(reasons.items(), key=lambda x: -x[1])
        ],
    }

    if want_detail:
        payload["results"] = rows

    return Response(payload)

# ===================== MY DRIVES (STUDENT) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_drives(request):
    """
    Drives a student can see, each ROLE carrying their own eligibility result.

    Eligibility is per role, so a student may qualify for one position in a
    drive and not another. The drive is listed once with its roles beneath.

    Ineligible roles are still shown, with reasons. Hiding them would leave a
    student wondering why a friend can apply and they cannot.

    Academic standing is fetched ONCE and reused across every role rather than
    recomputing CGPA per role.
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students have a drive list."},
            status=status.HTTP_403_FORBIDDEN,
        )

    drives = (
        Drive.objects
        .filter(status__in=["published", "closed"])
        .select_related("company")
        .prefetch_related("job_roles__eligibility__allowed_departments")
        .order_by("-created_at")
    )

    standing = get_academic_standing(user)

    # This student's existing decisions, fetched once and attached per role.
    # Without it the page cannot tell "not applied" from "already applied",
    # and would offer Apply on a role they already applied for.
    decisions = {
        a.job_role_id: a
        for a in Application.objects.filter(student=user)
    }

    rows = []
    eligible_roles = 0

    for drive in drives:
        drive_row = StudentDriveSerializer(drive).data

        roles = []
        for role in drive.job_roles.all():
            if not role.is_active:
                continue

            result = check_eligibility(user, role, standing=standing)

            role_row = StudentJobRoleSerializer(role).data
            role_row["eligible"] = result["eligible"]
            role_row["blockers"] = result["blockers"]
            role_row["checks"] = result["checks"]
            role_row["is_open"] = role.is_open

            decision = decisions.get(role.id)
            role_row["application"] = (
                {
                    "id": decision.id,
                    "status": decision.status,
                    "opt_out_reason": decision.opt_out_reason,
                    "applied_at": decision.applied_at,
                }
                if decision
                else None
            )

            roles.append(role_row)

            if result["eligible"]:
                eligible_roles += 1

        # A drive with no roles yet is not worth showing -- there is nothing
        # to apply for.
        if not roles:
            continue

        drive_row["job_roles"] = roles
        drive_row["any_eligible"] = any(r["eligible"] for r in roles)
        rows.append(drive_row)

    return Response({
        "standing": standing,
        "eligible_count": eligible_roles,
        "results": rows,
    })


# ===================== APPLY / OPT OUT (STUDENT) =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_to_role(request, role_id):
    """
    A student's decision about one role.

    Body:
        {"status": "applied"}
        {"status": "opted_out", "opt_out_reason": "..."}
        {"status": "withdrawn"}

    ELIGIBILITY IS RE-CHECKED HERE, not trusted from the page. The Apply
    button appearing is not permission: the page may have loaded an hour ago,
    and a result published since could have changed the answer.

    The deadline is enforced here too. Hiding the button in the UI is not
    enforcement -- anyone can post to this endpoint directly.
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students can apply."},
            status=status.HTTP_403_FORBIDDEN,
        )

    role = (
        JobRole.objects
        .select_related("drive__company")
        .prefetch_related("eligibility__allowed_departments")
        .filter(pk=role_id)
        .first()
    )
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get("status", "applied")

    if new_status not in ("applied", "opted_out", "withdrawn"):
        return Response({"detail": "Unknown status."}, status=status.HTTP_400_BAD_REQUEST)

    existing = Application.objects.filter(student=user, job_role=role).first()

    # ---------------- APPLYING ----------------
    if new_status == "applied":

        if not role.is_open:
            return Response(
                {"detail": "Applications for this role are closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = check_eligibility(user, role)
        if not result["eligible"]:
            return Response(
                {
                    "detail": "You are not eligible for this role.",
                    "blockers": result["blockers"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if existing:
            existing.status = "applied"
            existing.opt_out_reason = ""
            # snapshot refreshed: this is a NEW decision, so it records what
            # was true today, not when they first opted out
            existing.eligibility_snapshot = result
            existing.save()
            return Response(ApplicationSerializer(existing).data)

        application = Application.objects.create(
            student=user,
            job_role=role,
            status="applied",
            eligibility_snapshot=result,
        )
        return Response(
            ApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------------- WITHDRAWING ----------------
    if new_status == "withdrawn":

        if not existing:
            return Response(
                {"detail": "You have not applied for this role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Allowed only while the role is still open. After the deadline the
        # company has the applicant list, and a student vanishing from it is a
        # conversation, not a button.
        if not role.is_open:
            return Response(
                {"detail": "The deadline has passed -- speak to your coordinator."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing.status = "withdrawn"
        existing.save(update_fields=["status", "updated_at"])
        return Response(ApplicationSerializer(existing).data)

    # ---------------- OPTING OUT ----------------
    # No eligibility check: a student may decline a role they could not have
    # had anyway, and refusing to record that would leave them in the
    # "no response" list forever.
    reason = (request.data.get("opt_out_reason") or "").strip()

    if not reason:
        return Response(
            {"opt_out_reason": ["Please say why you are not interested."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if existing:
        existing.status = "opted_out"
        existing.opt_out_reason = reason
        existing.save(update_fields=["status", "opt_out_reason", "updated_at"])
        return Response(ApplicationSerializer(existing).data)

    application = Application.objects.create(
        student=user,
        job_role=role,
        status="opted_out",
        opt_out_reason=reason,
    )
    return Response(
        ApplicationSerializer(application).data,
        status=status.HTTP_201_CREATED,
    )


# ===================== MY APPLICATIONS (STUDENT) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_applications(request):
    """
    Everything this student has decided on.

    Read from request.user, never an id in the path, so one student cannot
    read another's applications.
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students have applications."},
            status=status.HTTP_403_FORBIDDEN,
        )

    applications = (
        Application.objects
        .filter(student=user)
        .select_related("job_role__drive__company")
    )

    return Response({
        "applied": ApplicationSerializer(
            applications.filter(status="applied"), many=True
        ).data,
        "opted_out": ApplicationSerializer(
            applications.filter(status="opted_out"), many=True
        ).data,
        "withdrawn": ApplicationSerializer(
            applications.filter(status="withdrawn"), many=True
        ).data,
    })


# ===================== APPLICATIONS FOR A ROLE (STAFF) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def role_applications(request, role_id):
    """
    Who applied, who declined, and who has not answered -- for one role.

    THE THIRD GROUP IS COMPUTED, NOT STORED. "No response" is every eligible
    student without an application row. Storing a row per non-response would
    mean creating thousands of rows nobody asked for, each needing an update
    whenever eligibility changed.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = (
        JobRole.objects
        .select_related("drive__company")
        .prefetch_related("eligibility__allowed_departments")
        .filter(pk=role_id)
        .first()
    )
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    students = scope_students_for(
        user,
        User.objects.filter(role="student"),
    ).select_related("department", "prior_academics", "course")

    applications = (
        Application.objects
        .filter(job_role=role, student__in=students)
        .select_related("student__department", "job_role__drive__company")
    )

    decided = {a.student_id: a for a in applications}

    no_response = []
    for student in students:
        if student.id in decided:
            continue
        if check_eligibility(student, role)["eligible"]:
            no_response.append({
                "student": student.id,
                "student_name": student.username,
                "roll_number": student.roll_number,
                "department_name": (
                    student.department.name if student.department else None
                ),
            })

    applied = applications.filter(status="applied")
    opted_out = applications.filter(status="opted_out")
    withdrawn = applications.filter(status="withdrawn")

    return Response({
        "job_role": role.id,
        "role_title": role.title,
        "company_name": role.drive.company.name,
        "counts": {
            "applied": applied.count(),
            "opted_out": opted_out.count(),
            "withdrawn": withdrawn.count(),
            "no_response": len(no_response),
        },
        "applied": StaffApplicationSerializer(applied, many=True).data,
        "opted_out": StaffApplicationSerializer(opted_out, many=True).data,
        "withdrawn": StaffApplicationSerializer(withdrawn, many=True).data,
        "no_response": no_response,
    })


# ===================== DRIVE ATTENDANCE =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def drive_attendance(request, role_id):
    """
    GET  -> everyone who applied for this role, with their attendance
    POST -> mark one student present or absent

    Marking PRESENT creates an approved OD and writes duty_leave attendance,
    through placement/services.py -> attendance/services.py. The placement
    cell sent the student, so there is nothing for a tutor or HOD to approve.

    Only students who APPLIED appear. Someone who opted out or withdrew is not
    expected on the day.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = JobRole.objects.select_related("drive__company").filter(pk=role_id).first()
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    students = scope_students_for(user, User.objects.filter(role="student"))

    applications = (
        Application.objects
        .filter(job_role=role, status="applied", student__in=students)
        .select_related("student__department", "drive_attendance")
        .order_by("student__roll_number")
    )

    if request.method == "GET":

        rows = []
        present = absent = unmarked = 0

        for app in applications:
            record = getattr(app, "drive_attendance", None)

            if record is None:
                unmarked += 1
                rows.append({
                    "id": None,
                    "application": app.id,
                    "student_name": app.student.username,
                    "roll_number": app.student.roll_number,
                    "department_name": (
                        app.student.department.name if app.student.department else None
                    ),
                    "status": None,
                    "status_display": "Not marked",
                    "remarks": "",
                    "od_created": False,
                })
            else:
                if record.status == "present":
                    present += 1
                else:
                    absent += 1
                rows.append(DriveAttendanceSerializer(record).data)

        return Response({
            "job_role": role.id,
            "role_title": role.title,
            "company_name": role.drive.company.name,
            "drive_date": role.drive.drive_date,
            # Without a date no OD can be created, and the screen should say
            # so before the coordinator marks thirty students.
            "can_create_od": bool(role.drive.drive_date),
            "counts": {
                "applied": applications.count(),
                "present": present,
                "absent": absent,
                "unmarked": unmarked,
            },
            "results": rows,
        })

    # ---------------- MARK ----------------
    application_id = request.data.get("application")
    new_status = request.data.get("status", "present")
    remarks = request.data.get("remarks", "")

    if new_status not in ("present", "absent"):
        return Response(
            {"detail": "status must be present or absent."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # re-checked against the caller's scope rather than trusted from the body,
    # so a coordinator cannot mark a student in another department
    application = applications.filter(pk=application_id).first()
    if not application:
        return Response(
            {"detail": "Application not found, or not one you can mark."},
            status=status.HTTP_404_NOT_FOUND,
        )

    record, _ = DriveAttendance.objects.get_or_create(
        application=application,
        defaults={"status": new_status},
    )

    was_present = record.status == "present" and record.od_request_id

    record.status = new_status
    record.remarks = remarks
    record.marked_by = user
    record.marked_at = timezone.now()

    note = ""

    if new_status == "present":
        od, note = create_drive_od(application, marked_by=user)
        record.od_request = od
    elif was_present:
        _od, note = cancel_drive_od(application)
        # the OD row is kept, cancelled, so the history stays readable
    record.save()

    data = DriveAttendanceSerializer(record).data
    data["note"] = note
    return Response(data)


# ===================== OFFERS (STAFF) =====================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def role_offers(request, role_id):
    """
    GET  -> offers made for this role, and who attended but has none
    POST -> record an offer

    The officer RECORDS an offer; the STUDENT accepts or declines it. This
    endpoint never sets status past 'offered' -- that decision is theirs and
    goes through their own endpoint.

    package_lpa defaults to the role's advertised package but is STORED on the
    offer. The role's figure can be edited later, and an offer must record
    what was actually offered.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    role = JobRole.objects.select_related("drive__company").filter(pk=role_id).first()
    if not role:
        return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

    students = scope_students_for(user, User.objects.filter(role="student"))

    applications = (
        Application.objects
        .filter(job_role=role, status="applied", student__in=students)
        .select_related("student__department", "offer")
        .order_by("student__roll_number")
    )

    if request.method == "GET":

        rows = []
        no_offer = []
        counts = {"offered": 0, "accepted": 0, "declined": 0}

        for app in applications:
            offer = getattr(app, "offer", None)

            if offer is None:
                no_offer.append({
                    "application": app.id,
                    "student_name": app.student.username,
                    "roll_number": app.student.roll_number,
                    "department_name": (
                        app.student.department.name if app.student.department else None
                    ),
                })
            else:
                counts[offer.status] = counts.get(offer.status, 0) + 1
                rows.append(OfferSerializer(offer).data)

        return Response({
            "job_role": role.id,
            "role_title": role.title,
            "company_name": role.drive.company.name,
            "role_package": role.package_lpa,
            "counts": {
                **counts,
                "no_offer": len(no_offer),
                "applied": applications.count(),
            },
            "results": rows,
            "no_offer": no_offer,
        })

    # ---------------- RECORD ----------------
    if not can_manage_placement(user):
        return Response(
            {"detail": "Only the placement officer can record offers."},
            status=status.HTTP_403_FORBIDDEN,
        )

    application_id = request.data.get("application")

    application = applications.filter(pk=application_id).first()
    if not application:
        return Response(
            {"detail": "Application not found, or not one you can record against."},
            status=status.HTTP_404_NOT_FOUND,
        )

    package = request.data.get("package_lpa")
    if package in ("", None):
        package = role.package_lpa

    offer, created = Offer.objects.get_or_create(
        application=application,
        defaults={
            "package_lpa": package,
            "joining_date": request.data.get("joining_date") or None,
            "remarks": request.data.get("remarks", ""),
            "recorded_by": user,
        },
    )

    if not created:
        offer.package_lpa = package
        offer.joining_date = request.data.get("joining_date") or offer.joining_date
        offer.remarks = request.data.get("remarks", offer.remarks)
        offer.recorded_by = user

    # A file only arrives on multipart requests, so it is set separately --
    # a plain JSON edit of the package must not wipe an uploaded letter.
    if "offer_letter" in request.FILES:
        offer.offer_letter = request.FILES["offer_letter"]

    offer.save()

    return Response(
        OfferSerializer(offer).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ===================== OFFER DETAIL (STAFF) =====================
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def offer_detail(request, offer_id):
    """
    PATCH  -> correct an offer's package, joining date, letter or remarks
    DELETE -> remove it

    Delete is REAL here, unlike everywhere else in this module: an offer
    recorded against the wrong student is a mistake, not history, and leaving
    it as a cancelled row would still count them as placed in the reports.
    """
    user = request.user

    if not can_manage_placement(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    offer = (
        Offer.objects
        .select_related("application__student", "application__job_role__drive__company")
        .filter(pk=offer_id)
        .first()
    )
    if not offer:
        return Response({"detail": "Offer not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        offer.delete()
        return Response({"detail": "Offer removed."})

    serializer = OfferSerializer(offer, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save(recorded_by=user)

    if "offer_letter" in request.FILES:
        offer.offer_letter = request.FILES["offer_letter"]
        offer.save(update_fields=["offer_letter"])

    return Response(OfferSerializer(offer).data)


# ===================== MY OFFERS (STUDENT) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_offers(request):
    """
    A student's own offers.

    A student may hold several at once and choose between them, so they are
    returned as ONE list rather than split by status -- the decision is a
    comparison, and separating them into tabs would hide the comparison.
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students have offers."},
            status=status.HTTP_403_FORBIDDEN,
        )

    offers = (
        Offer.objects
        .filter(application__student=user)
        .select_related("application__job_role__drive__company")
    )

    return Response({
        "count": offers.count(),
        "accepted": offers.filter(status="accepted").count(),
        "results": StudentOfferSerializer(offers, many=True).data,
    })


# ===================== ACCEPT / DECLINE (STUDENT) =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decide_offer(request, offer_id):
    """
    A student accepts or declines one of their own offers.

    Body: {"status": "accepted"} or {"status": "declined"}

    NOTHING is auto-declined. A student may accept two offers while deciding,
    and the system records what they did rather than enforcing a choice the
    college has not asked for. Reports count STUDENTS with an accepted offer,
    not offer rows, so a second acceptance cannot inflate the placed figure.

    Whether an accepted offer stops them applying elsewhere is decided by
    EligibilityRule.placed_package_cap at apply time -- not here.
    """
    user = request.user

    if not is_placement_student(user):
        return Response(
            {"detail": "Only students can answer an offer."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # filtered by student, so one student cannot answer another's offer
    offer = (
        Offer.objects
        .filter(pk=offer_id, application__student=user)
        .select_related("application__job_role__drive__company")
        .first()
    )
    if not offer:
        return Response({"detail": "Offer not found."}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get("status")

    if new_status not in ("accepted", "declined"):
        return Response(
            {"detail": "status must be accepted or declined."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    offer.status = new_status
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])

    return Response(StudentOfferSerializer(offer).data)

# ===================== PLACEMENT REPORT =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def placement_report(request):
    """
    Placement figures for ONE graduating batch.

    ?year=2030   the passing year to report on
    ?year        omitted -> the most recent batch

    THE NUMBER THAT MATTERS: "placed" counts STUDENTS WITH AT LEAST ONE
    ACCEPTED OFFER -- never offer rows. Forty students holding sixty offers
    between them is FORTY placed. Counting rows would publish sixty, and this
    is the figure that goes into a NAAC submission.

    Passing year is DERIVED (batch_year + course duration), not stored, so it
    cannot be filtered in SQL -- each student is checked in Python. Slower,
    but there is one definition of passing year rather than a stored column
    that drifts from the calculation.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    from exams.services import get_passing_year

    students = (
        scope_students_for(user, User.objects.filter(role="student"))
        .select_related("department", "course")
    )

    # ---------------- WHICH YEARS EXIST ----------------
    by_year = {}
    for student in students:
        year = get_passing_year(student)
        if year:
            by_year.setdefault(year, []).append(student)

    available_years = sorted(by_year.keys())

    if not available_years:
        return Response({
            "years": [],
            "year": None,
            "detail": (
                "No student has a passing year yet — batch year or course "
                "duration is missing."
            ),
        })

    # ---------------- PICK THE YEAR ----------------
    wanted = request.query_params.get("year")
    if wanted:
        try:
            year = int(wanted)
        except ValueError:
            year = available_years[-1]
    else:
        # The most recent batch, not the earliest. Opening on a graduated year
        # shows an empty report and makes the page look broken when the
        # current batch has all the data.
        year = available_years[-1]

    batch = by_year.get(year, [])
    batch_ids = [s.id for s in batch]

    # ---------------- ACCEPTED OFFERS ----------------
    accepted = (
        Offer.objects
        .filter(application__student_id__in=batch_ids, status="accepted")
        .select_related(
            "application__student__department",
            "application__job_role__drive__company",
        )
    )

    # student id -> their best accepted package. A student with two accepted
    # offers counts ONCE, and the package reported is the higher one.
    best_package = {}
    for offer in accepted:
        sid = offer.application.student_id
        pkg = offer.package_lpa
        if pkg is None:
            continue
        if sid not in best_package or pkg > best_package[sid]:
            best_package[sid] = pkg

    placed_ids = set(accepted.values_list("application__student_id", flat=True))

    total = len(batch)
    placed = len(placed_ids)

    packages = list(best_package.values())

    # ---------------- BY DEPARTMENT ----------------
    departments = {}
    for student in batch:
        name = student.department.name if student.department else "No department"
        row = departments.setdefault(name, {"students": 0, "placed": 0})
        row["students"] += 1
        if student.id in placed_ids:
            row["placed"] += 1

    department_rows = [
        {
            "department": name,
            "students": row["students"],
            "placed": row["placed"],
            "percent": round(row["placed"] / row["students"] * 100, 1)
            if row["students"]
            else 0,
        }
        for name, row in sorted(departments.items())
    ]

    # ---------------- BY COMPANY CATEGORY ----------------
    # Counts OFFERS here, not students, and the key says so. A student with a
    # product and a service offer is one placed student but two rows in this
    # split -- mixing the two meanings is how these reports go wrong.
    categories = {}
    for offer in accepted:
        company = offer.application.job_role.drive.company
        label = company.get_category_display()
        categories[label] = categories.get(label, 0) + 1

    # ---------------- BY COMPANY ----------------
    companies = {}
    for offer in accepted:
        name = offer.application.job_role.drive.company.name
        companies[name] = companies.get(name, 0) + 1

    company_rows = [
        {"company": name, "offers": count}
        for name, count in sorted(companies.items(), key=lambda x: -x[1])
    ]

    # ---------------- ACTIVITY ----------------
    applied_ids = set(
        Application.objects
        .filter(student_id__in=batch_ids, status="applied")
        .values_list("student_id", flat=True)
    )

    return Response({
        "years": available_years,
        "year": year,

        "summary": {
            "students": total,
            "applied": len(applied_ids),
            "placed": placed,
            "not_placed": total - placed,
            "percent": round(placed / total * 100, 1) if total else 0,
            # Offers can exceed placed students -- that is the point of
            # reporting both.
            "accepted_offers": accepted.count(),
        },

        "package": {
            "highest": max(packages) if packages else None,
            "lowest": min(packages) if packages else None,
            "average": round(sum(packages) / len(packages), 2) if packages else None,
            "counted": len(packages),
        },

        "departments": department_rows,
        "categories": [
            {"category": k, "offers": v}
            for k, v in sorted(categories.items(), key=lambda x: -x[1])
        ],
        "companies": company_rows,
    })

# ===================== DASHBOARD =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def placement_dashboard(request):
    """
    What the placement officer lands on: what is open, and what needs
    attention.

    The "attention" items are the point of this endpoint. Each is a silent
    problem -- nothing errors, nothing looks broken, the drive simply does
    nothing:

      * a PUBLISHED drive with no roles -- students see a card with nothing
        to apply for
      * a role nobody is eligible for -- the cutoffs are too tight, and the
        officer finds out when the applicant list stays empty
      * a role closing within 3 days with no applicants
      * students whose marks are unverified, who cannot apply for anything

    None of these are visible from any other screen, which is why they are
    computed here rather than assembled from existing endpoints.
    """
    user = request.user

    if not can_view_placement_staff(user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    from datetime import timedelta

    students = scope_students_for(user, User.objects.filter(role="student"))
    student_ids = list(students.values_list("id", flat=True))

    now = timezone.now()
    soon = now + timedelta(days=3)

    # ---------------- DRIVES ----------------
    drives = (
        Drive.objects
        .select_related("company")
        .prefetch_related("job_roles__eligibility__allowed_departments")
    )

    open_drives = []
    attention = []

    for drive in drives:

        if drive.status == "cancelled":
            continue

        roles = [r for r in drive.job_roles.all() if r.is_active]

        # published with nothing to apply for
        if drive.status == "published" and not roles:
            attention.append({
                "kind": "no_roles",
                "drive": drive.id,
                "message": (
                    f"{drive.company.name} is published but has no roles — "
                    f"students see it with nothing to apply for."
                ),
            })

        if not drive.is_open:
            continue

        for role in roles:

            applied = Application.objects.filter(
                job_role=role, status="applied", student_id__in=student_ids
            ).count()

            # A role nobody qualifies for is the expensive mistake: the drive
            # runs, the applicant list stays empty, and nobody finds out until
            # the day. Computed live -- the same check the student sees.
            eligible = sum(
                1 for s in students if check_eligibility(s, role)["eligible"]
            )

            open_drives.append({
                "drive": drive.id,
                "company_name": drive.company.name,
                "drive_title": drive.title,
                "role": role.id,
                "role_title": role.title,
                "package_lpa": role.package_lpa,
                "application_deadline": drive.application_deadline,
                "drive_date": drive.drive_date,
                "eligible": eligible,
                "applied": applied,
            })

            if eligible == 0:
                attention.append({
                    "kind": "nobody_eligible",
                    "drive": drive.id,
                    "role": role.id,
                    "message": (
                        f"Nobody is eligible for {role.title} at "
                        f"{drive.company.name} — the cutoffs may be too tight."
                    ),
                })

            elif (
                applied == 0
                and drive.application_deadline
                and drive.application_deadline <= soon
            ):
                attention.append({
                    "kind": "closing_empty",
                    "drive": drive.id,
                    "role": role.id,
                    "message": (
                        f"{role.title} at {drive.company.name} closes soon "
                        f"and nobody has applied."
                    ),
                })

    # ---------------- VERIFICATION ----------------
    # A student with unverified marks is ineligible for everything, and
    # nothing else on any screen says so out loud.
    verified = set(
        PriorAcademics.objects
        .filter(student_id__in=student_ids, verified=True)
        .values_list("student_id", flat=True)
    )
    unverified = len(student_ids) - len(verified)

    if unverified:
        attention.append({
            "kind": "unverified",
            "message": (
                f"{unverified} student{'' if unverified == 1 else 's'} "
                f"{'has' if unverified == 1 else 'have'} unverified academic "
                f"details and cannot apply for anything."
            ),
        })

    # ---------------- RECENT OFFERS ----------------
    recent_offers = (
        Offer.objects
        .filter(application__student_id__in=student_ids)
        .select_related(
            "application__student",
            "application__job_role__drive__company",
        )
        .order_by("-created_at")[:8]
    )

    offers = [
        {
            "id": o.id,
            "student_name": o.application.student.username,
            "roll_number": o.application.student.roll_number,
            "company_name": o.application.job_role.drive.company.name,
            "role_title": o.application.job_role.title,
            "package_lpa": o.package_lpa,
            "status": o.status,
            "status_display": o.get_status_display(),
        }
        for o in recent_offers
    ]

    waiting = sum(1 for o in offers if o["status"] == "offered")

    return Response({
        "counts": {
            "students": len(student_ids),
            "unverified": unverified,
            "open_roles": len(open_drives),
            "companies": Company.objects.filter(is_active=True).count(),
            "drives": drives.exclude(status="cancelled").count(),
            "offers_waiting": waiting,
        },
        "open_drives": sorted(
            open_drives,
            key=lambda d: (d["application_deadline"] is None, d["application_deadline"]),
        ),
        "attention": attention,
        "recent_offers": offers,
    })