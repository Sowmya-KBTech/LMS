from django.apps import AppConfig


class TeachingplanConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.teachingplan'

    def ready(self):
        # COURSE PLAN (Part C): Excel template / import / export (shared engine in core/dataio)
        from core.dataio.registry import register
        from .importers import CoursePlanImporter
        register(CoursePlanImporter())
