"""Connected Storages (#394): MIRES_ETL_STORAGES is synced into the database after migrate, like
native scripts (ADR 0030). Settings-managed storages are read-only in the admin; one removed from
settings is deleted only if nothing references it, otherwise kept and flagged."""
import pytest
from django.core.management import call_command

from MiqaResearch.actions.etl.storages import sync_etl_storages
from MiqaResearch.data.models import EtlLocationGrant, EtlStorage, ResearchProject

LAB = {
    "name": "Lab", "kind": "s3", "endpoint_url": "http://lab.example:9000", "region": "eu-west-1",
    "access_key_id_env": "LAB_KEY", "secret_access_key_env": "LAB_SECRET",
}


@pytest.fixture(autouse=True)
def _declared(settings):
    settings.ETL_STORAGES = [LAB]


def test_a_declared_storage_appears_as_settings_managed(db):
    sync_etl_storages()

    lab = EtlStorage.objects.get(name="Lab")
    assert (lab.endpoint_url, lab.region, lab.access_key_id_env, lab.secret_access_key_env) == (
        "http://lab.example:9000", "eu-west-1", "LAB_KEY", "LAB_SECRET")
    assert lab.managed_by_settings and not lab.no_longer_in_settings and not lab.is_default


def test_the_management_command_syncs_too(db):
    call_command("sync_etl_storages")

    assert EtlStorage.objects.filter(name="Lab", managed_by_settings=True).exists()


def test_a_storage_removed_from_settings_is_deleted_when_nothing_references_it(db, settings):
    sync_etl_storages()
    settings.ETL_STORAGES = []

    sync_etl_storages()

    assert not EtlStorage.objects.filter(name="Lab").exists()


def test_a_referenced_storage_removed_from_settings_is_kept_and_flagged(db, settings):
    sync_etl_storages()
    project = ResearchProject.objects.create(name="P", description="")
    EtlLocationGrant.objects.create(project=project, storage=EtlStorage.objects.get(name="Lab"), bucket="b")
    settings.ETL_STORAGES = []

    sync_etl_storages()

    assert EtlStorage.objects.get(name="Lab").no_longer_in_settings


def test_a_flagged_storage_declared_again_is_unflagged_and_updated(db, settings):
    sync_etl_storages()
    EtlStorage.objects.filter(name="Lab").update(no_longer_in_settings=True)
    settings.ETL_STORAGES = [{**LAB, "region": "us-east-2"}]

    sync_etl_storages()

    lab = EtlStorage.objects.get(name="Lab")
    assert not lab.no_longer_in_settings and lab.region == "us-east-2"


def test_the_default_storage_and_admin_created_storages_are_never_touched(db, settings):
    admin_made = EtlStorage.objects.create(name="Admin made", access_key_id_env="A", secret_access_key_env="B")
    EtlStorage.objects.get_or_create(is_default=True, defaults={"name": "Default"})
    settings.ETL_STORAGES = [{**LAB, "name": "Admin made"}]

    sync_etl_storages()

    admin_made.refresh_from_db()
    assert not admin_made.managed_by_settings and admin_made.access_key_id_env == "A"
    assert EtlStorage.objects.filter(is_default=True).exists()


def test_the_sync_runs_after_migrate(db):
    from django.apps import apps
    from django.db.models.signals import post_migrate

    post_migrate.send(sender=apps.get_app_config("data"), app_config=apps.get_app_config("data"), verbosity=0,
                      interactive=False, using="default", apps=apps, plan=[])

    assert EtlStorage.objects.filter(name="Lab", managed_by_settings=True).exists()


def test_vault_fields_are_synced_from_settings(db, settings):
    settings.ETL_STORAGES = [{
        "name": "Vaulted",
        "access_key_id_vault_path": "mires/lab", "access_key_id_vault_key": "Id",
        "secret_access_key_vault_path": "mires/lab", "secret_access_key_vault_key": "Secret"}]
    sync_etl_storages()
    storage = EtlStorage.objects.get(name="Vaulted")
    assert (storage.access_key_id_vault_path, storage.access_key_id_vault_key) == ("mires/lab", "Id")
    assert (storage.secret_access_key_vault_path, storage.secret_access_key_vault_key) == ("mires/lab", "Secret")
