"""
WAVE 2 - PRINCIPAL: who the Principal is right now, and assigning one.

Rules
  - At most one current Principal (database constraint).
  - Only the main admin assigns or ends a term.
  - The Principal must be an active teacher. Their own role, department and
    HOD duties do not change; the Principal powers come only from the current
    PrincipalTerm row.
  - Assigning a new Principal ends the current term the same day (history kept).
"""
from django.db import transaction
from django.utils import timezone

from core.users.models import PrincipalTerm, User


class PrincipalError(Exception):
    """A rule was broken. The message is shown to the user as it is."""


def current_term():
    return PrincipalTerm.objects.filter(is_current=True).select_related("teacher").first()


def current_principal():
    term = current_term()
    return term.teacher if term else None


def is_principal(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return PrincipalTerm.objects.filter(is_current=True, teacher_id=user.id).exists()


def _end(term, by):
    term.is_current = False
    term.end_date = timezone.localdate()
    term.ended_by = by
    term.save(update_fields=["is_current", "end_date", "ended_by"])


@transaction.atomic
def assign(teacher_id, by):
    teacher = User.objects.filter(pk=teacher_id, role="teacher", is_active=True).first() \
        if str(teacher_id).isdigit() else None
    if teacher is None:
        raise PrincipalError("Choose an active teaching staff member.")
    term = PrincipalTerm.objects.select_for_update().filter(is_current=True).first()
    if term and term.teacher_id == teacher.id:
        raise PrincipalError(f"{teacher.get_full_name() or teacher.username} is already the Principal.")
    if term:
        _end(term, by)
    return PrincipalTerm.objects.create(teacher=teacher, start_date=timezone.localdate(),
                                        is_current=True, assigned_by=by)


@transaction.atomic
def end_current(by):
    term = PrincipalTerm.objects.select_for_update().filter(is_current=True).first()
    if term is None:
        raise PrincipalError("No Principal is set.")
    _end(term, by)
    return term
