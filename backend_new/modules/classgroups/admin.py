# backend/classgroups/admin.py
from django.contrib import admin

from .models import ClassGroup, ClassMessage


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "academic_year",
                    "announcement_only", "students_can_message", "is_archived")
    list_filter = ("kind", "academic_year", "announcement_only")


@admin.register(ClassMessage)
class ClassMessageAdmin(admin.ModelAdmin):
    list_display = ("group", "sender", "message_type", "title",
                    "is_pinned", "is_deleted", "created_at")
    list_filter = ("message_type", "is_pinned", "is_deleted")
    search_fields = ("title", "text", "attachment_name")