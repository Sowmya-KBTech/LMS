from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.fees'
    verbose_name = 'Fees & Payments'

    def ready(self):
        import modules.fees.signals  # noqa: F401

        # fees import / export (shared engine in core/dataio)
        from core.dataio.registry import register
        from .importers import FeeImporter
        register(FeeImporter())
