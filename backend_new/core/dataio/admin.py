from django.contrib import admin

from .models import ImportLog


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ("importer", "mode", "rows_total", "created_count", "updated_count", "imported_by", "created_at")
    list_filter = ("importer", "mode")
    search_fields = ("file_name", "imported_by__username")
    readonly_fields = [f.name for f in ImportLog._meta.fields]
