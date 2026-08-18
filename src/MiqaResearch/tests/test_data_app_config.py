import pytest
from django.apps import apps
from django.contrib.auth.models import Group

from MiqaResearch.data.models import OIDCRoleMapping


@pytest.mark.django_db
def test_ready_seeds_role_mappings_when_table_empty(monkeypatch):
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    apps.get_app_config("data").ready()

    assert OIDCRoleMapping.objects.filter(oidc_role="admin").exists()


@pytest.mark.django_db
def test_ready_does_not_reseed_when_table_has_rows(monkeypatch):
    existing_group = Group.objects.create(name="Old")
    OIDCRoleMapping.objects.create(oidc_role="old-role", group=existing_group)
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    apps.get_app_config("data").ready()

    assert not OIDCRoleMapping.objects.filter(oidc_role="admin").exists()
