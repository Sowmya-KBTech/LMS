# backend/mentoring/apps.py
from django.apps import AppConfig


class MentoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'modules.mentoring'
    verbose_name = "Mentoring"