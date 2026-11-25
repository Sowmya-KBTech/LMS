from rest_framework.permissions import SAFE_METHODS, BasePermission


def can_manage_academics(user):
    """
    Who may create / edit / delete academic setup (teaching assignments,
    courses, subjects): superuser, the main admin (no sub-role), super admin
    and academic admin. ONE rule - the REST API and the Excel import
    (core/dataio/importers/academics.py) both use it.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.role == "admin" and (user.sub_role or "") in ("", "super_admin", "academic_admin")


class CanManageAcademicsOrReadOnly(BasePermission):
    """Any logged-in user may READ; only can_manage_academics() may WRITE."""
    message = "Only the academic admin can change this."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return can_manage_academics(request.user)