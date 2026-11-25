# ===================== IMPORTS =====================
from core.academics.permissions import CanManageAcademicsOrReadOnly
from django.db import models
from django.contrib.auth import get_user_model

from rest_framework import viewsets
from rest_framework.decorators import (  api_view, permission_classes)
from rest_framework.permissions import ( IsAuthenticated)
from rest_framework.response import Response
from rest_framework import status

from core.academics.models import Course, Year, Subject, TeachingAssignment, Enrollment
from core.notifications.models import Notification
from config.module_registry import optional_model

from core.academics.serializers import (
    CourseSerializer,
    YearSerializer,
    SubjectSerializer,
    TeachingAssignmentSerializer,
    EnrollmentSerializer,
)

User = get_user_model()

# Optional modules used by the dashboards (read-only). When a module is
# switched off, these become stand-ins that always return no rows, so the
# dashboard shows 0 instead of crashing.
Attendance = optional_model("attendance", "attendance", "Attendance")
Lecture = optional_model("learning", "learning", "Lecture")
Assignment = optional_model("learning", "learning", "Assignment")
Submission = optional_model("learning", "learning", "Submission")
Quiz = optional_model("learning", "learning", "Quiz")
StudyMaterial = optional_model("learning", "learning", "StudyMaterial")
Fee = optional_model("fees", "fees", "Fee")


# ===================== ADMIN DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard(request):
    if request.user.role != "admin":
        return Response({"error": "Unauthorized"}, status=403)

    return Response({
        "total_users": User.objects.count(),
        "total_students": User.objects.filter(role="student").count(),
        "total_teachers": User.objects.filter(role="teacher").count(),
        "total_parents": User.objects.filter(role="parent").count(),
        "total_courses": Course.objects.count(),
        "total_enrollments": Enrollment.objects.count(),
    })


# ===================== TEACHER DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_dashboard(request):
    if request.user.role != "teacher":
        return Response({"error": "Unauthorized"}, status=403)

    tas = TeachingAssignment.objects.filter(teacher=request.user)

    # FIX #22: count each student once, not once per subject they take with me
    total_students = Enrollment.objects.filter(
        teaching_assignment__teacher=request.user
    ).values("student").distinct().count()

    return Response({
        "subjects": tas.count(),
        "students": total_students,
        "assignments": Assignment.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "lectures": Lecture.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "quizzes": Quiz.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
        "materials": StudyMaterial.objects.filter(
            teaching_assignment__teacher=request.user
        ).count(),
    })


# ===================== COURSE =====================
class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by("name")
    serializer_class = CourseSerializer
    # PHASE 5: everyone may read; only the academic admin may create / edit / delete
    permission_classes = [CanManageAcademicsOrReadOnly]


# ===================== YEAR =====================
class YearViewSet(viewsets.ModelViewSet):
    serializer_class = YearSerializer
    # PHASE 5: everyone may read; only the academic admin may create / edit / delete
    permission_classes = [CanManageAcademicsOrReadOnly]

    def get_queryset(self):
        queryset = Year.objects.all()

        course = self.request.query_params.get("course")
        if course:
            queryset = queryset.filter(course_id=course)

        return queryset.select_related("course").order_by("year_number")


# ===================== SUBJECT =====================
class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    # PHASE 5: everyone may read; only the academic admin may create / edit / delete
    permission_classes = [CanManageAcademicsOrReadOnly]

    def get_queryset(self):
        queryset = Subject.objects.all()

        year = self.request.query_params.get("year")
        semester = self.request.query_params.get("semester")

        if year:
            queryset = queryset.filter(year_id=year)
        if semester:
            queryset = queryset.filter(semester=semester)

        return queryset.select_related(
            "year", "year__course"
        ).order_by("name")


# ===================== TEACHING ASSIGNMENT =====================
class TeachingAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = TeachingAssignmentSerializer
    # SECURITY FIX: anyone logged in could create / edit / delete who teaches
    # what. Reading stays open (subject pages need it); writing is for the
    # academic admin only - the same rule as the Excel import.
    permission_classes = [CanManageAcademicsOrReadOnly]

    def get_queryset(self):
        queryset = TeachingAssignment.objects.all()

        course = self.request.query_params.get("course")
        year = self.request.query_params.get("year")
        teacher = self.request.query_params.get("teacher")
        my = self.request.query_params.get("my")

        if course:
            queryset = queryset.filter(course_id=course)
        if year:
            queryset = queryset.filter(year_id=year)
        if teacher:
            queryset = queryset.filter(teacher_id=teacher)

        # only the logged-in teacher's own assignments
        if my == "true" and self.request.user.role == "teacher":
            queryset = queryset.filter(teacher=self.request.user)

        return queryset.select_related(
            "course", "year", "subject", "teacher"
        ).order_by("year__year_number")

    def perform_create(self, serializer):
        serializer.save()


        

# ===================== ENROLLMENT =====================
class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    # PHASE 5: lists stay scoped by role (get_queryset); only the academic admin may
    # create / edit / delete enrollments (students pick electives through elective-enroll)
    permission_classes = [CanManageAcademicsOrReadOnly]

    def get_queryset(self):
        user = self.request.user

        queryset = Enrollment.objects.select_related(
            'student',
            'teaching_assignment',
            'teaching_assignment__teacher',
            'teaching_assignment__course',
            'teaching_assignment__year',
            'teaching_assignment__subject',
        )

        # role-based visibility (narrow, don't return yet)
        if user.role in ("admin", "academic_admin"):
            pass
        elif user.role == "teacher":
            queryset = queryset.filter(teaching_assignment__teacher=user)
        elif user.role == "student":
            queryset = queryset.filter(student=user)
        else:
            return Enrollment.objects.none()

        # filter by the selected class (THE FIX)
        ta = self.request.query_params.get("teaching_assignment")
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)

        return queryset

    def perform_create(self, serializer):
        serializer.save()


    

    # ================= GENERATE ENROLLMENTS =================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_enrollments(request):

    if request.user.role not in ("admin", "academic_admin"):
        return Response(
            {
                "error": "Only admin or academic admin can generate enrollments"
            },
            status=403
        )

    from core.academics.services import enroll_student

    created_count = 0

    for student in User.objects.filter(role='student'):
        created_count += enroll_student(student)

    return Response(
        {
            "message": "Enrollments generated successfully",
            "created": created_count
        },
        status=status.HTTP_200_OK
    )


# ===================== ELECTIVE SELF-ENROLLMENT =====================
# A student sees the electives offered for their own course + year + semester,
# and enrols / un-enrols themselves. Core subjects are auto-enrolled elsewhere;
# ONLY subjects with is_elective=True are self-serve, and a student can only
# ever touch electives in their OWN class.

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_electives(request):
    """
    GET /my-electives/
    The electives offered to THIS student (their course/year/semester), each
    flagged with whether they're already enrolled.
    """
    user = request.user
    if getattr(user, "role", None) != "student":
        return Response({"detail": "Only students have electives."}, status=403)

    if not user.course or not user.year or not user.semester:
        return Response([])

    # every elective teaching-assignment for this student's exact class
    assignments = (
        TeachingAssignment.objects
        .filter(
            course=user.course,
            year__year_number=user.year,
            subject__semester=user.semester,
            subject__is_elective=True,
        )
        .select_related("subject", "teacher")
        .order_by("subject__name")
    )

    # which of them this student is already in
    mine = set(
        Enrollment.objects
        .filter(student=user, teaching_assignment__in=assignments)
        .values_list("teaching_assignment_id", flat=True)
    )

    data = [
        {
            "teaching_assignment": a.id,
            "subject": a.subject.name,
            "code": a.subject.code or "",
            "credits": a.subject.credits,
            "teacher_name": (a.teacher.get_full_name() or "").strip() or a.teacher.username,
            "enrolled": a.id in mine,
        }
        for a in assignments
    ]
    return Response(data)


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def elective_enroll(request):
    """
    POST   /elective-enroll/   body { "teaching_assignment": <id> }  -> enrol
    DELETE /elective-enroll/   body { "teaching_assignment": <id> }  -> un-enrol

    Guardrails: the target must be an ELECTIVE in the student's OWN
    course/year/semester. A student can't self-enrol into a core subject,
    another class, or someone else's elective.
    """
    user = request.user
    if getattr(user, "role", None) != "student":
        return Response({"detail": "Only students can choose electives."}, status=403)

    ta_id = request.data.get("teaching_assignment")
    if not ta_id:
        return Response({"detail": "teaching_assignment is required."}, status=400)

    # the TA must be an elective in EXACTLY this student's class
    ta = (
        TeachingAssignment.objects
        .filter(
            id=ta_id,
            course=user.course,
            year__year_number=user.year,
            subject__semester=user.semester,
            subject__is_elective=True,
        )
        .first()
    )
    if not ta:
        return Response(
            {"detail": "That elective is not available for your class."},
            status=404,
        )

    # ELECTIVES (meeting point 9): this older endpoint follows the same rules
    # as the new ones, so it can't be used to skip a seat limit, a last date,
    # a "pick 1" group or the "HOD allocates" setting.
    from core.academics import electives as rules
    from core.academics.models_electives import ElectiveOption, ElectiveSetting
    option = ElectiveOption.objects.filter(teaching_assignment=ta).first()
    if option is not None:
        try:
            if request.method == "POST":
                rules.choose(user, option, by=user)
            else:
                rules.drop(user, option, by=user)
        except rules.ElectiveError as exc:
            return Response({"detail": str(exc)}, status=400)
        enrolled = request.method == "POST"
        return Response({"detail": "Enrolled." if enrolled else "Removed.",
                         "teaching_assignment": ta.id, "enrolled": enrolled})
    if not ElectiveSetting.current().students_choose:
        return Response({"detail": "In this college your HOD allocates electives."}, status=403)

    if request.method == "POST":
        _, created = Enrollment.objects.get_or_create(
            student=user,
            teaching_assignment=ta,
        )
        return Response(
            {"detail": "Enrolled.", "teaching_assignment": ta.id, "enrolled": True},
            status=201 if created else 200,
        )

    # DELETE -> drop it
    Enrollment.objects.filter(student=user, teaching_assignment=ta).delete()
    return Response(
        {"detail": "Removed.", "teaching_assignment": ta.id, "enrolled": False}
    )


# ===================== PARENT DASHBOARD =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parent_dashboard(request):
    user = request.user
    if user.role != 'parent':
        return Response({'detail': 'Not a parent.'}, status=403)
    from core.users.models import ParentProfile
    try:
        profile = ParentProfile.objects.prefetch_related(
            'children').get(user=user)
    except ParentProfile.DoesNotExist:
        return Response({'detail': 'No profile.'}, status=404)
    children = profile.children.all()
    fees = Fee.objects.filter(student__in=children)
    pending_fees = sum(
        (f.amount - f.paid_amount) for f in fees if f.status != 'paid')
    enrolled_ta_ids = Enrollment.objects.filter(
        student__in=children
    ).values_list('teaching_assignment_id', flat=True)
    submitted_ids = Submission.objects.filter(
        student__in=children
    ).values_list('assignment_id', flat=True)
    pending_assignments = Assignment.objects.filter(
        teaching_assignment_id__in=enrolled_ta_ids
    ).exclude(id__in=submitted_ids).count()
    att_data = {}
    for child in children:
        recs = Attendance.objects.filter(student=child)
        total = recs.count()
        present = recs.filter(status='present').count()
        att_data[child.username] = {
            'total': total, 'present': present,
            'percentage': round(present/total*100,1) if total else 0
        }
    avg = round(sum(v['percentage'] for v in att_data.values())
                / len(att_data), 1) if att_data else 0
    notifs = Notification.objects.filter(
        recipient=user).order_by('-created_at')[:10]
    return Response({
        'children_enrolled': children.count(),
        'pending_fees': float(pending_fees),
        'avg_attendance': avg,
        'pending_assignments': pending_assignments,
        'attendance_per_child': att_data,
        'children': [{'id': c.id, 'username': c.username} for c in children],
        'recent_notifications': [
            {'id':n.id,'title':n.title,'message':n.message,
             'is_read':n.is_read,'created_at':n.created_at}
            for n in notifs],
    })


# ===================== MANAGE PARENTS (ADMIN) =====================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def manage_parents(request):
    if request.user.role != 'admin':
        return Response({'detail': 'Only admin can manage parents.'}, status=403)

    from core.users.models import ParentProfile

    if request.method == 'GET':
        parents = []
        for p in ParentProfile.objects.select_related('user').prefetch_related('children'):
            parents.append({
                'profile_id': p.id,
                'username': p.user.username,
                'children': [{'id': c.id, 'username': c.username} for c in p.children.all()],
            })
        students = list(
            User.objects.filter(role='student')
            .order_by('course__name', 'username')
            .values('id', 'username', course_name=models.F('course__name'))
        )
        return Response({'parents': parents, 'students': students})

    username = (request.data.get('username') or '').strip()
    password = request.data.get('password') or ''
    child_ids = request.data.get('children', [])

    if not username or not password:
        return Response({'detail': 'Username and password are required.'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'detail': 'That username already exists.'}, status=400)

    parent = User(username=username, role='parent')
    parent.set_password(password)
    parent.save()

    profile = ParentProfile.objects.create(user=parent)
    if child_ids:
        profile.children.set(User.objects.filter(id__in=child_ids, role='student'))

    return Response({'message': 'Parent created successfully.', 'profile_id': profile.id}, status=201)


# ===================== UPDATE A PARENT (ADMIN) =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_parent_children(request, profile_id):
    if request.user.role != 'admin':
        return Response({'detail': 'Only admin can manage parents.'}, status=403)

    from core.users.models import ParentProfile
    try:
        profile = ParentProfile.objects.select_related('user').get(id=profile_id)
    except ParentProfile.DoesNotExist:
        return Response({'detail': 'Parent profile not found.'}, status=404)

    parent = profile.user

    # ----- update username (if provided and changed) -----
    username = (request.data.get('username') or '').strip()
    if username and username != parent.username:
        if User.objects.filter(username=username).exclude(id=parent.id).exists():
            return Response({'detail': 'That username already exists.'}, status=400)
        parent.username = username

    # ----- update password (only if a new one is sent) -----
    password = request.data.get('password') or ''
    if password:
        parent.set_password(password)

    parent.save()

    # ----- update children (if the list is sent) -----
    if 'children' in request.data:
        child_ids = request.data.get('children', [])
        profile.children.set(User.objects.filter(id__in=child_ids, role='student'))

    return Response({'message': 'Parent updated.'})