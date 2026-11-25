"""
python manage.py create_platform_admin <username> --password "<password>" [--email you@kbtechnosoft.com]

PLATFORM CONSOLE - creates a KB Technosoft account for the platform console
(sign in at the platform address: localhost:5173, later admin.kbtechcampus.in).
It is NOT a college account and cannot sign in at any college.
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import PlatformAdmin


class Command(BaseCommand):
    help = "Create (or reset the password of) a KB Technosoft platform admin."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **opts):
        try:
            validate_password(opts["password"])
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))

        with schema_context(get_public_schema_name()):
            admin, created = PlatformAdmin.objects.get_or_create(
                username=opts["username"].strip(), defaults={"email": opts["email"]})
            admin.set_password(opts["password"])
            admin.is_active = True
            if opts["email"]:
                admin.email = opts["email"]
            admin.save()
        word = "Created" if created else "Updated password for"
        self.stdout.write(self.style.SUCCESS(
            f"{word} platform admin '{admin.username}'. Sign in at the platform address."))
