from django.apps import AppConfig


class TimetableConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.timetable'

    def ready(self):
        import modules.timetable.signals  # noqa: F401  (Redis/Celery work: shared cache)
