"""Connected Storages in the Django admin (#394): staff manage admin-created storages (env-var names
only, no secret fields); the Default and settings-declared ones are read-only and the Default can't
be deleted."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from MiqaResearch.data.models import EtlStorage
from MiqaResearch.data.models.etl_storage import default_storage

User = get_user_model()


@pytest.fixture
def staff_client(db):
    client = Client()
    client.force_login(User.objects.create_user(username="staff", password="pw", is_staff=True))
    return client


def _url(name, *args):
    return reverse(f"admin:data_etlstorage_{name}", args=args)


FORM = {"name": "Lab", "kind": "s3", "endpoint_url": "http://lab:9000", "region": "eu-west-1",
        "access_key_id_env": "LAB_KEY", "secret_access_key_env": "LAB_SECRET"}


def test_staff_can_create_edit_and_delete_a_storage(staff_client):
    staff_client.post(_url("add"), FORM)
    lab = EtlStorage.objects.get(name="Lab")

    staff_client.post(_url("change", lab.id), {**FORM, "region": "us-east-2"})
    lab.refresh_from_db()
    assert lab.region == "us-east-2"

    staff_client.post(_url("delete", lab.id), {"post": "yes"})
    assert not EtlStorage.objects.filter(name="Lab").exists()


def test_the_form_has_env_var_names_and_vault_refs_but_no_secret_value_field(staff_client):
    fields = set(staff_client.get(_url("add")).context["adminform"].form.fields)

    assert fields == {
        "name", "kind", "endpoint_url", "region", "access_key_id_env", "secret_access_key_env",
        "access_key_id_vault_path", "access_key_id_vault_key",
        "secret_access_key_vault_path", "secret_access_key_vault_key"}


def test_the_default_storage_is_read_only_and_cannot_be_deleted(staff_client):
    default = default_storage()

    staff_client.post(_url("change", default.id), {**FORM, "name": "Hacked"})
    staff_client.post(_url("delete", default.id), {"post": "yes"})

    default.refresh_from_db()
    assert default.name == "Default"


def test_a_settings_managed_storage_is_read_only_and_cannot_be_deleted(staff_client):
    managed = EtlStorage.objects.create(name="Managed", managed_by_settings=True, region="eu-west-1")

    staff_client.post(_url("change", managed.id), {**FORM, "name": "Managed", "region": "us-east-2"})
    staff_client.post(_url("delete", managed.id), {"post": "yes"})

    managed.refresh_from_db()
    assert managed.region == "eu-west-1"


def test_an_unconfigured_credential_is_shown_in_the_list(staff_client, monkeypatch):
    monkeypatch.delenv("LAB_KEY", raising=False)
    EtlStorage.objects.create(name="Lab", access_key_id_env="LAB_KEY", secret_access_key_env="LAB_SECRET")

    html = staff_client.get(_url("changelist")).content.decode()

    assert "credentials not configured" in html
