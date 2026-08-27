# backend/classgroups/apps.py
from django.apps import AppConfig


class ClassgroupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "classgroups"
    verbose_name = "Class Groups"
