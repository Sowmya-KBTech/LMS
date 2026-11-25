# backend/mentoring/admin.py
from django.contrib import admin

from .models import MentorAllocation, MentoringSetting, MentorChangeRequest


@admin.register(MentoringSetting)
class MentoringSettingAdmin(admin.ModelAdmin):
    list_display = ("department", "max_students_per_mentor",
                    "band_a_min", "band_b_min", "route_via_advisor")


@admin.register(MentorAllocation)
class MentorAllocationAdmin(admin.ModelAdmin):
    list_display = ("student", "mentor", "academic_year", "grade_band",
                    "status", "source", "is_active", "start_date", "end_date")
    list_filter = ("academic_year", "status", "source", "grade_band", "department")
    search_fields = ("student__username", "student__roll_number",
                     "mentor__username", "mentor__employee_id")
    # history must survive: no bulk delete from the admin either
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(MentorChangeRequest)
class MentorChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "current_mentor", "reason", "status",
                    "is_confidential", "academic_year", "created_at")
    list_filter = ("status", "is_confidential", "raised_role", "academic_year")
    search_fields = ("student__username", "student__roll_number",
                     "current_mentor__username")
    autocomplete_fields = ()