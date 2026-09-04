import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate

from MiqaResearch.data.models import OIDCRoleMapping


@pytest.mark.django_db
def test_post_migrate_seeds_role_mappings_when_table_empty(monkeypatch):
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')
    app_config = apps.get_app_config("data")

    post_migrate.send(sender=app_config, app_config=app_config)

    assert OIDCRoleMapping.objects.filter(oidc_role="admin").exists()


@pytest.mark.django_db
def test_post_migrate_does_not_reseed_when_table_has_rows(monkeypatch):
    existing_group = Group.objects.create(name="Old")
    OIDCRoleMapping.objects.create(oidc_role="old-role", group=existing_group)
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')
    app_config = apps.get_app_config("data")

    post_migrate.send(sender=app_config, app_config=app_config)

    assert not OIDCRoleMapping.objects.filter(oidc_role="admin").exists()
