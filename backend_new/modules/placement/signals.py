"""
Keeps the saved placement eligibility (eligibility_store.py) in step with
everything check_eligibility() reads. Each handler only QUEUES the affected
students / roles; the refresh runs once after the transaction commits.

Publishing a drive is NOT here - drive_detail() calls publish_drive()
directly, because it also sends notices and reports how many went out.
"""
from django.apps import apps
from django.db.models.signals import m2m_changed, post_save, pre_save

from . import eligibility_store as store
from .models import EligibilityRule, JobRole, Offer, PlacementPolicy

STUDENT_FIELDS = ("year", "semester", "course_id", "department_id", "is_active", "batch_year")


def _role_saved(sender, instance, **kwargs):
    store.queue(roles=[instance.id])


def _rule_saved(sender, instance, **kwargs):
    store.queue(roles=[instance.job_role_id])


def _rule_departments_changed(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear"):
        store.queue(roles=[instance.job_role_id])


def _offer_saved(sender, instance, **kwargs):
    # accepted / declined changes the same-or-higher package rule
    from .models import Application
    sid = Application.objects.filter(pk=instance.application_id).values_list("student_id", flat=True).first()
    store.queue(students=[sid])


def _policy_saved(sender, instance, **kwargs):
    store.queue(everything=True)


def _prior_saved(sender, instance, **kwargs):
    store.queue(students=[instance.student_id])


def _result_saved(sender, instance, **kwargs):
    store.queue(students=[instance.student_id])


def _result_entry_saved(sender, instance, **kwargs):
    SemesterResult = apps.get_model("exams", "SemesterResult")
    sid = SemesterResult.objects.filter(pk=instance.result_id).values_list("student_id", flat=True).first()
    store.queue(students=[sid])


def _tracked(update_fields):
    """False when a save only touches untracked fields (e.g. last_login on every login)."""
    if update_fields is None:
        return True
    names = {f.replace("_id", "") for f in STUDENT_FIELDS}
    return any(f.replace("_id", "") in names for f in update_fields)


def _user_before_save(sender, instance, update_fields=None, **kwargs):
    if not _tracked(update_fields):
        instance._placement_old = None
        return
    if instance.pk and getattr(instance, "role", None) == "student":
        old = sender.objects.filter(pk=instance.pk).values(*STUDENT_FIELDS).first()
        instance._placement_old = old


def _user_saved(sender, instance, created, **kwargs):
    old = getattr(instance, "_placement_old", None)
    if created or old is None:
        return            # new students get their rows on first read
    if any(old[f] != getattr(instance, f) for f in STUDENT_FIELDS):
        store.queue(students=[instance.id])


def connect():
    from core.users.models import PriorAcademics, User

    post_save.connect(_role_saved, sender=JobRole, dispatch_uid="pl_elig_role")
    post_save.connect(_rule_saved, sender=EligibilityRule, dispatch_uid="pl_elig_rule")
    m2m_changed.connect(_rule_departments_changed, sender=EligibilityRule.allowed_departments.through,
                        dispatch_uid="pl_elig_rule_depts")
    post_save.connect(_offer_saved, sender=Offer, dispatch_uid="pl_elig_offer")
    post_save.connect(_policy_saved, sender=PlacementPolicy, dispatch_uid="pl_elig_policy")
    post_save.connect(_prior_saved, sender=PriorAcademics, dispatch_uid="pl_elig_prior")
    pre_save.connect(_user_before_save, sender=User, dispatch_uid="pl_elig_user_pre")
    post_save.connect(_user_saved, sender=User, dispatch_uid="pl_elig_user")

    # results live in the exams module, which a college may switch off
    if apps.is_installed("modules.exams"):
        post_save.connect(_result_saved, sender=apps.get_model("exams", "SemesterResult"),
                          dispatch_uid="pl_elig_result")
        post_save.connect(_result_entry_saved, sender=apps.get_model("exams", "ResultEntry"),
                          dispatch_uid="pl_elig_result_entry")
