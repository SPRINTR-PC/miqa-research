from django.core.management.base import BaseCommand

from MiqaResearch.data.models import OIDCRoleMapping


class Command(BaseCommand):
    help = "Seed or update OIDCRoleMapping rows from the MIRES_OIDC_ROLE_MAPPING environment variable."

    def handle(self, *args, **options):
        count = OIDCRoleMapping.objects.seed_from_env(only_if_empty=False)
        self.stdout.write(self.style.SUCCESS(f"Seeded/updated {count} OIDC role mapping(s)."))
