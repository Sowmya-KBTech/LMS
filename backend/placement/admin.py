from django.contrib import admin

from .models import (
    PlacementCoordinator,
    Company,
    Drive,
    JobRole,
    EligibilityRule,
    Application,
    DriveAttendance,
    Offer,
)


@admin.register(PlacementCoordinator)
class PlacementCoordinatorAdmin(admin.ModelAdmin):
    list_display = ("teacher", "department", "is_active", "assigned_at")
    list_filter = ("is_active", "department")
    search_fields = ("teacher__username", "teacher__employee_id", "department__name")
    ordering = ("department__name", "-assigned_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "contact_person", "contact_email")


class JobRoleInline(admin.TabularInline):
    """
    Roles shown inside their drive. A drive is meaningless without its roles --
    that is where the package and the eligibility live -- so editing them on
    separate pages means holding two screens in your head.
    """
    model = JobRole
    extra = 0
    fields = ("title", "package_lpa", "job_location", "openings", "is_active")


@admin.register(Drive)
class DriveAdmin(admin.ModelAdmin):
    list_display = ("company", "title", "status", "drive_date", "application_deadline")
    list_filter = ("status", "company")
    search_fields = ("company__name", "title")
    date_hierarchy = "drive_date"
    inlines = [JobRoleInline]


@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display = ("title", "drive", "package_lpa", "openings", "is_active")
    list_filter = ("is_active", "drive__company")
    search_fields = ("title", "drive__company__name")


@admin.register(EligibilityRule)
class EligibilityRuleAdmin(admin.ModelAdmin):
    list_display = (
        "job_role",
        "min_cgpa",
        "max_arrears",
        "min_tenth_percent",
        "min_twelfth_percent",
        "placed_package_cap",
    )
    # A M2M renders as an unusable multi-select without this.
    filter_horizontal = ("allowed_departments",)
    search_fields = ("job_role__title", "job_role__drive__company__name")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("student", "job_role", "status", "applied_at")
    list_filter = ("status", "job_role__drive__company")
    search_fields = ("student__username", "student__roll_number", "job_role__title")
    # The snapshot is a record of why the student was allowed to apply at the
    # time. Editing it would rewrite history, so it is shown but locked.
    readonly_fields = ("eligibility_snapshot", "applied_at", "updated_at")


@admin.register(DriveAttendance)
class DriveAttendanceAdmin(admin.ModelAdmin):
    list_display = ("application", "status", "od_request", "marked_by", "marked_at")
    list_filter = ("status",)
    search_fields = (
        "application__student__username",
        "application__student__roll_number",
    )
    # The OD is created by placement/services.py, which also writes the
    # duty_leave attendance rows. Re-pointing it here would leave those rows
    # attached to an OD nothing references.
    readonly_fields = ("od_request",)


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("application", "package_lpa", "status", "offered_on", "decided_at")
    list_filter = ("status", "application__job_role__drive__company")
    search_fields = (
        "application__student__username",
        "application__student__roll_number",
    )
    # Stamped when the STUDENT answers. An officer setting it here would
    # record a decision the student never made.
    readonly_fields = ("decided_at",)