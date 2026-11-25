from django.apps import AppConfig


class SecurityConfig(AppConfig):
    """PHASE 5 PART 4 - login protection (failed-attempt counts, signed-out tokens).

    Listed in BOTH SHARED_APPS and TENANT_APPS, so its two small tables exist in
    the platform (public) schema AND in every college's schema: each college's
    counts stay inside that college.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "core.security"
    label = "security"
    verbose_name = "Login protection"
