from django.contrib import admin

from .models import Survey


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "status", "department", "start_date", "end_date")
    list_filter = ("audience", "status")
