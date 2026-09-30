from django.core.management.base import BaseCommand

from MiqaResearch.actions.etl.native_scripts import sync_native_etl_scripts


class Command(BaseCommand):
    help = "Create or update the native (built-in) ETL Scripts from the codebase (also runs after every migrate)."

    def handle(self, *args, **options):
        sync_native_etl_scripts()
        self.stdout.write(self.style.SUCCESS("Native ETL Scripts are in sync."))
