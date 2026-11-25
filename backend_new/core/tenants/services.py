"""
PLATFORM CONSOLE - creating and describing colleges, in ONE place.

Used by the `create_college` command AND the platform console's
"Add college" form, so both always follow exactly the same rules.
"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College, Domain

CODE_RULE = re.compile(r"^[a-z][a-z0-9]{1,29}$")
RESERVED = {"public", "admin", "www", "api", "platform", "static", "media", "test"}


class CollegeError(Exception):
    """A reason a college cannot be created, worded for the person who asked."""


def default_domain(code):
    """abc -> abc.localhost on a laptop; abc.kbtechcampus.in when COLLEGE_DOMAIN_SUFFIX says so."""
    suffix = getattr(settings, "COLLEGE_DOMAIN_SUFFIX", "localhost")
    return f"{code}.{suffix}"


def check_new_college(code, name, domain=None, admin_username=None, admin_password=None):
    """Every check BEFORE anything is created. Returns (code, name, domain)."""
    code = (code or "").strip().lower()
    name = (name or "").strip()
    if not name:
        raise CollegeError("College name is required.")
    if not CODE_RULE.match(code) or code in RESERVED or code == get_public_schema_name():
        raise CollegeError(
            "Code must be 2-30 lowercase letters/digits starting with a letter, "
            f"and not one of: {', '.join(sorted(RESERVED))}.")
    if College.objects.filter(schema_name=code).exists():
        raise CollegeError(f"A college with code '{code}' already exists.")

    domain = (domain or default_domain(code)).strip().lower()
    if Domain.objects.filter(domain=domain).exists():
        raise CollegeError(f"The address {domain} is already in use.")

    if admin_username and not admin_password:
        raise CollegeError("A password is required for the first college admin.")
    if admin_password:
        try:
            validate_password(admin_password)
        except ValidationError as exc:
            raise CollegeError(" ".join(exc.messages))
    return code, name, domain


def create_college(code, name, domain=None, admin_username=None, admin_password=None, admin_email=""):
    """
    Build a college: its row (Tenant ID), its schema with every table, its
    address, and optionally its first admin. Raises CollegeError with a
    readable reason if anything is wrong - and then creates nothing.
    """
    code, name, domain = check_new_college(code, name, domain, admin_username, admin_password)

    # colleges live in the public schema; the schema + tables are built in save()
    with schema_context(get_public_schema_name()):
        college = College.objects.create(schema_name=code, name=name)
        Domain.objects.create(domain=domain, tenant=college, is_primary=True)

    if admin_username:
        with schema_context(code), transaction.atomic():
            get_user_model().objects.create_superuser(
                username=admin_username.strip(), email=admin_email or "", password=admin_password)
    return college


def _logo_version(college):
    from core.tenants.models import CollegeLogo
    logo = CollegeLogo.objects.filter(college=college).only("updated_at").first()
    return logo.version if logo else None


def college_summary(college, with_counts=True):
    """
    What the platform may know about a college: who it is, its address, its
    status, and TOTALS. Never a student, a mark or a fee - only numbers, plus
    the usernames of the college's admins (needed to help them sign in).
    """
    domains = [d.domain for d in college.domains.order_by("-is_primary", "domain")]
    data = {
        "id": college.id,
        "name": college.name,
        "code": college.schema_name,
        "is_active": college.is_active,
        "created_on": college.created_on.isoformat() if college.created_on else None,
        "domain": domains[0] if domains else None,
        "domains": domains,
        "logo_version": _logo_version(college),          # None = no logo yet
    }
    if with_counts:
        from core.users.models import Department
        User = get_user_model()
        with schema_context(college.schema_name):
            users = User.objects.all()
            data["counts"] = {
                "students": users.filter(role="student").count(),
                "teachers": users.filter(role="teacher").count(),
                "parents": users.filter(role="parent").count(),
                "departments": Department.objects.count(),
            }
            data["admins"] = list(
                users.filter(Q(is_superuser=True) | Q(role="admin"))
                .order_by("username").values_list("username", flat=True))
            data["online_payments"] = _online_payments_status()
    return data


def _online_payments_status():
    """
    PHASE 3 - has this college set up its own Razorpay account?
    Only yes/no and test/live - never a key. Run inside the college's schema.
    """
    from django.apps import apps
    if not apps.is_installed("modules.fees"):
        return {"configured": False, "mode": None, "webhook": False}
    from modules.fees.models import PaymentSettings
    ps = PaymentSettings.current()
    return {"configured": ps.is_configured, "mode": ps.mode, "webhook": ps.has_webhook}
