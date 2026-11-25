from django.apps import AppConfig


class TenantsConfig(AppConfig):
    """
    SAAS PHASE 1: the tenant layer.

    One row in College per college that uses KB Tech Campus. Its id is the
    Tenant ID and its schema_name is the PostgreSQL schema holding all of that
    college's tables. Stored once, in the shared "public" schema.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "core.tenants"
    label = "tenants"
    verbose_name = "Colleges (tenants)"
