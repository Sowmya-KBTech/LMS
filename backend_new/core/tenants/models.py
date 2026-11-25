"""
SAAS PHASE 1 - THE TENANT TABLES (public schema, one copy for the platform).

College  = one tenant. Its id is the Tenant ID; schema_name ("abc") is the
           private schema with all of that college's tables.
Domain   = a web address that leads to a college ("abc.localhost",
           later "abc.kbtechcampus.in"). A college can have several.

The platform itself is the College with schema_name "public".
"""
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class College(TenantMixin):
    # TenantMixin adds: schema_name
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(
        default=True,
        help_text="Switch off to stop a college's users from using the app. Data is kept.",
    )
    created_on = models.DateField(auto_now_add=True)

    # build the college's schema (every tenant table) the moment it is saved
    auto_create_schema = True
    # deleting a College row never deletes its data - dropping a schema is a
    # deliberate, separate step taken after a backup
    auto_drop_schema = False

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    # DomainMixin adds: domain, tenant (-> College), is_primary
    pass


class CollegeLogo(models.Model):
    """
    COLLEGE LOGO - shown on the college's login page (before anyone signs in).

    Kept in the public schema, in its own table: the login page needs it
    BEFORE sign-in (college files need a sign-in), and keeping the bytes out
    of College means they are not loaded on every request. Set by KB
    Technosoft in the platform console; always a cleaned PNG (core/tenants/logos.py).
    """
    college = models.OneToOneField(College, on_delete=models.CASCADE, related_name="logo")
    image = models.BinaryField()
    content_type = models.CharField(max_length=30, default="image/png")
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def version(self):
        return int(self.updated_at.timestamp() * 1000)      # ms: a new upload = a new ?v=

    def __str__(self):
        return f"Logo of {self.college.schema_name}"


class PlatformAdmin(models.Model):
    """
    PLATFORM CONSOLE - a KB Technosoft account (public schema).

    Completely separate from every college's users: it lives in the shared
    schema, signs in only at the platform address, and its token is refused
    at every college address. It manages colleges; it never sees students,
    marks or fees - only totals.
    """
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["username"]

    # what DRF needs from request.user
    is_authenticated = True
    is_anonymous = False

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.username
