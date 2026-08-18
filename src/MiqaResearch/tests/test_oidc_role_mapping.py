import pytest
from django.contrib.auth.models import Group

from MiqaResearch.data.models import OIDCRoleMapping


@pytest.mark.django_db
def test_seed_from_env_creates_mapping_and_group(monkeypatch):
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    created = OIDCRoleMapping.objects.seed_from_env()

    assert created == 1
    mapping = OIDCRoleMapping.objects.get(oidc_role="admin")
    assert mapping.group.name == "Administrators"


@pytest.mark.django_db
def test_seed_from_env_reuses_existing_group(monkeypatch):
    Group.objects.create(name="Administrators")
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    OIDCRoleMapping.objects.seed_from_env()

    assert Group.objects.filter(name="Administrators").count() == 1


@pytest.mark.django_db
def test_seed_from_env_only_if_empty_skips_when_table_has_rows(monkeypatch):
    existing_group = Group.objects.create(name="Old")
    OIDCRoleMapping.objects.create(oidc_role="old-role", group=existing_group)
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    created = OIDCRoleMapping.objects.seed_from_env(only_if_empty=True)

    assert created == 0
    assert not OIDCRoleMapping.objects.filter(oidc_role="admin").exists()


@pytest.mark.django_db
def test_seed_from_env_upserts_when_not_only_if_empty(monkeypatch):
    old_group = Group.objects.create(name="Old")
    OIDCRoleMapping.objects.create(oidc_role="admin", group=old_group)
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    OIDCRoleMapping.objects.seed_from_env(only_if_empty=False)

    mapping = OIDCRoleMapping.objects.get(oidc_role="admin")
    assert mapping.group.name == "Administrators"


@pytest.mark.django_db
def test_seed_from_env_with_empty_env_var_creates_nothing(monkeypatch):
    monkeypatch.delenv("MIRES_OIDC_ROLE_MAPPING", raising=False)

    created = OIDCRoleMapping.objects.seed_from_env()

    assert created == 0
    assert OIDCRoleMapping.objects.count() == 0
