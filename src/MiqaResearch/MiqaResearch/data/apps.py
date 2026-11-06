from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_oidc_role_mappings(sender, **kwargs):
    from MiqaResearch.data.models import OIDCRoleMapping

    OIDCRoleMapping.objects.seed_from_env(only_if_empty=True)


def _sync_native_etl_scripts(sender, **kwargs):
    from django.conf import settings

    if not settings.ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE:
        return
    from MiqaResearch.actions.etl.native_scripts import sync_native_etl_scripts

    sync_native_etl_scripts()


def _sync_etl_storages(sender, **kwargs):
    from MiqaResearch.actions.etl.storages import sync_etl_storages

    sync_etl_storages()


class DataConfig(AppConfig):
    name = "MiqaResearch.data"

    def ready(self):
        from MiqaResearch.data import signals  # noqa: F401

        post_migrate.connect(
            _seed_oidc_role_mappings, sender=self, dispatch_uid="data.seed_oidc_role_mappings"
        )
        post_migrate.connect(
            _sync_native_etl_scripts, sender=self, dispatch_uid="data.sync_native_etl_scripts"
        )
        post_migrate.connect(_sync_etl_storages, sender=self, dispatch_uid="data.sync_etl_storages")
