"""
PHASE 5 (security) - who may do what, in ONE place.

The menu hiding a button is not protection: anyone signed in can call an API
directly. These helpers are the server-side rules the APIs use.

    is_college_admin(user)   any admin of this college (role "admin") or superuser
    is_top_admin(user)       the main admin / super admin - the only ones who may
                             create admins or change anyone's role
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

TOP_ADMIN_SUB_ROLES = ("", "super_admin")


def is_college_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser) or getattr(user, "role", None) == "admin"


def is_top_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.role == "admin" and (user.sub_role or "") in TOP_ADMIN_SUB_ROLES


class IsCollegeAdminOrReadOnly(BasePermission):
    """Anyone signed in may READ; only a college admin may WRITE."""
    message = "Only the college admin can change this."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return is_college_admin(request.user)
