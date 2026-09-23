"""Unit tests for the ETL permissions policy module (#158): the sole source of truth for the
manage/admin-only/read-only/404 role boundaries on the ETL Pipelines tab. Pure and DB-free -- role
names are passed in directly rather than loaded from `ResearchProjectUserRoleMap`.
"""
import pytest

from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_CONTRIBUTOR,
    PROJECT_ROLE_DATA_MANAGER,
    PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
    PROJECT_ROLE_PI,
)
from MiqaResearch.readers.etl_permissions import etl_permissions_for_roles


def _permissions(*role_names, is_superuser=False):
    return etl_permissions_for_roles(is_superuser=is_superuser, role_names=role_names)


@pytest.mark.parametrize("role", [PROJECT_ROLE_ADMIN, PROJECT_ROLE_DATA_MANAGER])
def test_admin_and_data_manager_can_view_and_manage(role):
    permissions = _permissions(role)

    assert permissions.can_view
    assert permissions.can_manage


def test_admin_can_manage_admin_only_actions():
    assert _permissions(PROJECT_ROLE_ADMIN).can_manage_admin_only


def test_data_manager_cannot_manage_admin_only_actions():
    permissions = _permissions(PROJECT_ROLE_DATA_MANAGER)

    assert permissions.can_manage
    assert not permissions.can_manage_admin_only


@pytest.mark.parametrize("role", [PROJECT_ROLE_PI, PROJECT_ROLE_INVESTIGATOR])
def test_pi_and_investigator_can_view_but_not_manage(role):
    permissions = _permissions(role)

    assert permissions.can_view
    assert not permissions.can_manage
    assert not permissions.can_manage_admin_only


@pytest.mark.parametrize("role", [
    PROJECT_ROLE_CONTRIBUTOR, PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_PARTICIPANT_RECRUITER,
])
def test_other_roles_cannot_even_view(role):
    permissions = _permissions(role)

    assert not permissions.can_view
    assert not permissions.can_manage
    assert not permissions.can_manage_admin_only


def test_a_user_with_no_project_role_at_all_cannot_view():
    permissions = _permissions()

    assert not permissions.can_view


def test_superuser_can_view_manage_and_manage_admin_only_regardless_of_role():
    permissions = etl_permissions_for_roles(is_superuser=True, role_names=[])

    assert permissions.can_view
    assert permissions.can_manage
    assert permissions.can_manage_admin_only


def test_holding_multiple_roles_takes_the_most_permissive():
    permissions = _permissions(PROJECT_ROLE_CONTRIBUTOR, PROJECT_ROLE_ADMIN)

    assert permissions.can_view
    assert permissions.can_manage
    assert permissions.can_manage_admin_only
