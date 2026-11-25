from django.conf import settings
from django.db import models


# ===================== IMPORT LOG (audit) =====================
class ImportLog(models.Model):
    """
    One row per COMPLETED import: who imported what, when, from which file,
    and how many rows were added / updated.

    Only successful imports are logged - an import either saves every row or
    none (it runs in one transaction), so there is no "half done" import to
    record. Passwords generated for new accounts are NEVER stored here.
    """

    MODE_CHOICES = (
        ("add", "Add new only"),
        ("upsert", "Add and update"),
    )

    importer = models.CharField(max_length=50, db_index=True)   # e.g. "students"
    file_name = models.CharField(max_length=255, blank=True)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default="add")

    rows_total = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.importer} by {self.imported_by} on {self.created_at:%d-%m-%Y %H:%M}"
