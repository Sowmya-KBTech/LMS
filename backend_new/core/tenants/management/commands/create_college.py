"""
python manage.py create_college <code> "<College name>" [options]

ONBOARDING A COLLEGE (the platform console's "Add college" form does the same):
  1. a College row in the public schema   -> its Tenant ID
  2. a private schema named <code>, with every tenant table built in it
  3. its address: <code>.<COLLEGE_DOMAIN_SUFFIX>  (abc.localhost by default)
  4. optionally its first college admin (a superuser inside that college)

Examples:
    python manage.py create_college demo "Demo Engineering College"
    python manage.py create_college abc "ABC Engineering College" --admin-username abcadmin --admin-password "Change@123"
    python manage.py create_college abc "ABC Engineering College" --domain abc.kbtechcampus.in
"""
from django.core.management.base import BaseCommand, CommandError

from core.tenants.services import CollegeError, create_college


class Command(BaseCommand):
    help = "Add a college (a tenant): its schema, its address and optionally its first admin."

    def add_arguments(self, parser):
        parser.add_argument("code", help="short permanent code: lowercase letters/digits, starts with a letter, e.g. abc")
        parser.add_argument("name", help='full name, e.g. "ABC Engineering College"')
        parser.add_argument("--domain", help="address (default: <code>.<COLLEGE_DOMAIN_SUFFIX>)")
        parser.add_argument("--admin-username", help="create the college's first admin with this username")
        parser.add_argument("--admin-password", help="password for that admin (required with --admin-username)")
        parser.add_argument("--admin-email", default="", help="email for that admin")

    def handle(self, *args, **opts):
        try:
            college = create_college(
                code=opts["code"], name=opts["name"], domain=opts["domain"],
                admin_username=opts["admin_username"], admin_password=opts["admin_password"],
                admin_email=opts["admin_email"],
            )
        except CollegeError as exc:
            raise CommandError(str(exc))

        domain = college.domains.get(is_primary=True).domain
        self.stdout.write(self.style.SUCCESS(
            f"Created {college.name}: Tenant ID {college.id}, schema '{college.schema_name}', address {domain}"))
        if opts["admin_username"]:
            self.stdout.write(self.style.SUCCESS(
                f"  First college admin '{opts['admin_username']}' created inside {college.schema_name}."))
