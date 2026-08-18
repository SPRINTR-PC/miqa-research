import pytest
from django.core.management import call_command

from MiqaResearch.data.models import OIDCRoleMapping


@pytest.mark.django_db
def test_command_seeds_role_mappings(monkeypatch):
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')

    call_command("seed_oidc_role_mappings")

    assert OIDCRoleMapping.objects.filter(oidc_role="admin").exists()
