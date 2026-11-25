"""
python manage.py move_media_to_colleges            # show what would happen (changes nothing)
python manage.py move_media_to_colleges --apply    # copy the files
python manage.py move_media_to_colleges --apply --remove-old   # copy, then delete the old shared copies

PHASE 4 - run ONCE after switching to per-college files.

Before Phase 4 every college's uploads were saved in one shared folder:
    media/student_photos/ravi.jpg
Now a college reads its files from its own folder:
    media/abc/student_photos/ravi.jpg
The database keeps the same short name ("student_photos/ravi.jpg"), so no
record changes - only the file moves. For every college, this command looks
at every file field of every record, and copies the file it points to from
the old shared place into that college's folder.

Safe to run again: files already in the college folder are skipped.
"""
import os
import shutil

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College


def file_fields():
    """(model, [file field names]) for every college (tenant) model that stores uploads."""
    tenant_apps = set(settings.TENANT_APPS)
    for model in apps.get_models():
        if model._meta.app_config.name not in tenant_apps:
            continue
        names = [f.name for f in model._meta.get_fields()
                 if isinstance(f, models.FileField) and not f.many_to_many]
        if names and not model._meta.proxy:
            yield model, names


class Command(BaseCommand):
    help = "Copy uploads from the old shared media folder into each college's own folder."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="actually copy (without it, only a report is shown)")
        parser.add_argument("--remove-old", action="store_true",
                            help="with --apply: delete each old shared file once every college that uses it has its copy")
        parser.add_argument("--only", help="one college code, e.g. abc")

    def handle(self, *args, **opts):
        apply, remove_old = opts["apply"], opts["remove_old"]
        root = settings.MEDIA_ROOT
        colleges = College.objects.exclude(schema_name=get_public_schema_name()).order_by("id")
        if opts["only"]:
            colleges = colleges.filter(schema_name=opts["only"].lower())

        totals = {"copied": 0, "already": 0, "missing": 0}
        copied_sources = set()

        for college in colleges:
            code = college.schema_name
            counts = {"copied": 0, "already": 0, "missing": 0}
            with schema_context(code):
                for model, names in file_fields():
                    for row in model.objects.values_list(*names):
                        for name in row:
                            if not name:
                                continue
                            target = os.path.join(root, code, name)
                            source = os.path.join(root, name)
                            if os.path.isfile(target):
                                counts["already"] += 1
                            elif os.path.isfile(source):
                                counts["copied"] += 1
                                copied_sources.add(source)
                                if apply:
                                    os.makedirs(os.path.dirname(target), exist_ok=True)
                                    shutil.copy2(source, target)
                                else:
                                    self.stdout.write(f"  [{code}] would copy {name}")
                            else:
                                counts["missing"] += 1
                                self.stdout.write(self.style.WARNING(f"  [{code}] file not found: {name}"))

            word = "copied" if apply else "to copy"
            self.stdout.write(
                f"{college.name} ({code}): {counts['copied']} {word}, "
                f"{counts['already']} already in place, {counts['missing']} missing")
            for k in totals:
                totals[k] += counts[k]

        if apply and remove_old:
            for source in sorted(copied_sources):
                os.remove(source)
            self.stdout.write(f"Removed {len(copied_sources)} old shared file(s).")

        if apply:
            self.stdout.write(self.style.SUCCESS(
                f"Done: {totals['copied']} copied, {totals['already']} already in place, "
                f"{totals['missing']} missing."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Nothing changed. {totals['copied']} file(s) would be copied. "
                "Run again with --apply to copy them."))
