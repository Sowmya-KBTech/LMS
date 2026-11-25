from django.apps import AppConfig


class LearningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.learning'
    verbose_name = 'Learning (lectures, assignments, quizzes, materials)'

    def ready(self):
        import modules.learning.signals  # noqa: F401

        # WAVE 3 PART 3b: question bank import / export (shared engine in core/dataio)
        from core.dataio.registry import register
        from .importers import QuestionBankImporter
        register(QuestionBankImporter())
