# ===================== IMPORTS =====================
from django.contrib.auth import get_user_model

from rest_framework.permissions import ( BasePermission, SAFE_METHODS)

from core.academics.models import Enrollment


User = get_user_model()


def get_parent_children(user):
    from core.users.models import ParentProfile

    try:
        profile = ParentProfile.objects.prefetch_related(
            "children"
        ).get(user=user)

        return profile.children.all()

    except ParentProfile.DoesNotExist:
        return User.objects.none()


# ===================== PERMISSION =====================
class IsAdminOrTeacherOrReadOnly(BasePermission):

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated

        return (
            request.user.is_authenticated
            and request.user.role in ['teacher', 'admin']
        )


# ===================== HELPER =====================
def get_enrolled_ta_ids(user):
    """Return the teaching_assignment IDs the student is enrolled in."""
    return Enrollment.objects.filter(
        student=user
    ).values_list("teaching_assignment_id", flat=True)
