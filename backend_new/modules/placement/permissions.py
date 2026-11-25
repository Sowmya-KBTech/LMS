"""
Who is allowed to do what in the placement module.

Single source of truth. Placement has roughly 40 endpoints and every one of
them asks the same two questions: is this person allowed here, and if they are
a coordinator, which department may they see? Writing that condition out in
each view means editing 40 places when the rule changes -- and missing one
leaves a hole nobody notices until the wrong data is on screen.

Plain functions, not DRF permission classes, to stay close to the inline style
already used across this codebase (`if user.role == "admin":`).

NOTE ON SCOPING: coordinator_department() reads the assignment table on the
server. A department must NEVER be accepted from the browser -- that would let
anyone view another department's students by editing a request.
"""

from .models import PlacementCoordinator


# ===================== PLACEMENT OFFICER =====================
def is_placement_officer(user):
    """
    The college-level placement admin.

    role='admin' + sub_role='placement_officer'. Not a top-level role, so all
    existing "is this an admin?" checks continue to pass for them.
    """
    if not user or not user.is_authenticated:
        return False
    return user.role == "admin" and user.sub_role == "placement_officer"


# ===================== SUPER ADMIN =====================
def is_super_admin(user):
    """Super admin sees everything placement can show."""
    if not user or not user.is_authenticated:
        return False
    return user.role == "admin" and (
        user.sub_role == "super_admin" or user.is_superuser
    )


# ===================== PLACEMENT COORDINATOR =====================
def is_placement_coordinator(user):
    """
    A teacher with an ACTIVE coordinator assignment.

    Inactive assignments do not count -- that is how an assignment is ended.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role != "teacher":
        return False
    return PlacementCoordinator.objects.filter(
        teacher=user,
        is_active=True,
    ).exists()


def coordinator_department(user):
    """
    The Department this coordinator may see, or None.

    Every coordinator-facing queryset must filter by this. Returns None for
    anyone who is not an active coordinator, so a caller that forgets to check
    gets an empty result rather than everything.
    """
    if not user or not user.is_authenticated or user.role != "teacher":
        return None

    assignment = (
        PlacementCoordinator.objects
        .filter(teacher=user, is_active=True)
        .select_related('department')
        .first()
    )
    return assignment.department if assignment else None


# ===================== COMBINED CHECKS =====================
def can_manage_placement(user):
    """
    May create companies, drives and eligibility rules.
    Officer and super admin only -- coordinators do not create drives.
    """
    return is_placement_officer(user) or is_super_admin(user)


def can_view_placement_staff(user):
    """
    May open a staff-side placement screen at all.
    Officers see the whole college; coordinators see one department.
    """
    return (
        is_placement_officer(user)
        or is_super_admin(user)
        or is_placement_coordinator(user)
    )


def is_placement_student(user):
    """A student, for the student-facing placement screens."""
    if not user or not user.is_authenticated:
        return False
    return user.role == "student"


# ===================== QUERYSET SCOPING =====================
def scope_students_for(user, queryset):
    """
    Narrow a queryset of student Users to what `user` is allowed to see.

    Officer / super admin -> everything.
    Coordinator           -> their department only.
    Anyone else           -> nothing.

    Views call this instead of writing their own filter, so the department
    rule cannot drift between screens.
    """
    if is_placement_officer(user) or is_super_admin(user):
        return queryset

    department = coordinator_department(user)
    if department:
        return queryset.filter(department=department)

    return queryset.none()