"""
python manage.py setup_platform

SAAS PHASE 1 - run once on a new database, after `migrate_schemas --shared`.
Creates the platform tenant (schema "public") and the addresses that reach
it. Safe to run again.

    python manage.py setup_platform
    python manage.py setup_platform --domain localhost --domain 127.0.0.1
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name

from core.tenants.models import College, Domain


class Command(BaseCommand):
    help = "Create the platform (public) tenant and its addresses."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="KB Tech Campus platform")
        parser.add_argument("--domain", action="append", dest="domains",
                            help="address of the platform; repeat for more (default: localhost, 127.0.0.1)")

    def handle(self, *args, **opts):
        domains = opts["domains"] or ["localhost", "127.0.0.1"]
        public, created = College.objects.get_or_create(
            schema_name=get_public_schema_name(), defaults={"name": opts["name"]})
        self.stdout.write(f"{'Created' if created else 'Found'} platform tenant: Tenant ID {public.id}")
        for i, d in enumerate(domains):
            dom, made = Domain.objects.get_or_create(
                domain=d, defaults={"tenant": public, "is_primary": i == 0})
            if dom.tenant_id != public.id:
                self.stderr.write(self.style.WARNING(f"  {d} already belongs to {dom.tenant} - left as it is"))
            else:
                self.stdout.write(f"  {'added' if made else 'has'} address {d}")
        self.stdout.write(self.style.SUCCESS("Platform ready."))
