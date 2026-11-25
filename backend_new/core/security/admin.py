from django.contrib import admin

from core.security.models import LoginFailure


@admin.register(LoginFailure)
class LoginFailureAdmin(admin.ModelAdmin):
    """Delete rows here to unblock someone before the 15 minutes are up."""
    list_display = ("username", "ip", "at")
    search_fields = ("username", "ip")
