from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.attendance'

    def ready(self):
        # attendance import / export (shared engine in core/dataio)
        from core.dataio.registry import register
        from .importers import AttendanceImporter
        register(AttendanceImporter())
