"""
SAAS PHASE 1 - run the tests inside a test college.

With django-tenants the test database starts with only the shared "public"
schema, where no college tables exist. This runner creates one test college
(schema "test") whose address is "testserver" - the host Django's test client
sends - and points the connection at it, so every existing test runs inside
a college exactly as before.

Tests that need more than one college (isolation tests, Phase 5) create
their own extra colleges.
"""
from django.db import connection
from django.test.runner import DiscoverRunner


class TenantTestRunner(DiscoverRunner):
    TEST_SCHEMA = "test"
    TEST_DOMAIN = "testserver"

    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)

        from django_tenants.utils import get_public_schema_name
        from core.tenants.models import College, Domain

        connection.set_schema_to_public()
        College.objects.get_or_create(schema_name=get_public_schema_name(),
                                      defaults={"name": "Test platform"})
        college = College(schema_name=self.TEST_SCHEMA, name="Test College")
        college.save(verbosity=0)                 # builds every tenant table
        Domain.objects.create(domain=self.TEST_DOMAIN, tenant=college, is_primary=True)

        connection.set_tenant(college)
        return old_config
