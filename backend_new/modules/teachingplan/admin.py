# backend/teaching_plans/admin.py
from django.contrib import admin
from .models import TeachingPlan, PlanUnit


class PlanUnitInline(admin.TabularInline):
    model = PlanUnit
    extra = 0


@admin.register(TeachingPlan)
class TeachingPlanAdmin(admin.ModelAdmin):
    list_display = ("subject", "teacher", "class_section", "semester", "status", "created_at")
    list_filter = ("status", "semester", "department")
    search_fields = ("class_section", "teacher__username")
    inlines = [PlanUnitInline]


@admin.register(PlanUnit)
class PlanUnitAdmin(admin.ModelAdmin):
    list_display = ("topic", "plan", "hours", "complete_by", "is_completed")
    list_filter = ("is_completed",)