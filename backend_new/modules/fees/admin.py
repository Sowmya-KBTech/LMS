from django.contrib import admin
from .models import Fee


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display  = ['student', 'term', 'amount', 'due_date', 'status']
    list_filter   = ['status', 'term']
    list_editable = ['status']
