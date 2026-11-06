from django.core.management.base import BaseCommand

from MiqaResearch.actions.etl.storages import sync_etl_storages


class Command(BaseCommand):
    help = "Sync the Connected Storages in MIRES_ETL_STORAGES into the database (also runs after every migrate)."

    def handle(self, *args, **options):
        sync_etl_storages()
        self.stdout.write(self.style.SUCCESS("Connected Storages are in sync."))
