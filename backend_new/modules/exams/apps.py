from django.apps import AppConfig


class ExamsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.exams'

    def ready(self):
        # IA marks + results import/export (shared engine in core/dataio)
        from core.dataio.registry import register
        from .importers import ExamScheduleImporter, IAMarksImporter, ResultsImporter
        register(IAMarksImporter())
        register(ResultsImporter())
        register(ExamScheduleImporter())
