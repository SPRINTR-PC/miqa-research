"""The ETL Scripts section's custom-script Data Table endpoint: project scoping, role gating, edit action column."""
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM, ETL_SCRIPT_ORIGIN_NATIVE
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
    PROJECT_ROLE_PI,
)
from MiqaResearch.data.models import (
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)

User = get_user_model()


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Scripts Table Project", description="desc")


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name}-{uuid4().hex[:6]}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _script(project, name, **extra):
    return EtlScript.objects.create(
        name=name, project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM, datatype_name="participant_consent", **extra)


def _get(user, project, **query):
    client = Client()
    client.force_login(user)
    url = reverse("api-v1:etl_scripts_table", kwargs={"project_id": project.id})
    return client.get(url, {"include_columns": "true", **query})


@pytest.mark.django_db
def test_a_viewer_sees_only_this_projects_custom_scripts(project):
    _script(project, "Mine", description="desc")
    _script(ResearchProject.objects.create(name="Other", description="d"), "Theirs")
    EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, datatype_name="participant_consent")

    response = _get(_user_with_role(project, PROJECT_ROLE_PI), project)

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [(row["name"], row["description"], row["datatype_name"], row["version_count"]) for row in rows] == [
        ("Mine", "desc", "participant_consent", 0)]


@pytest.mark.django_db
def test_a_read_only_role_gets_no_edit_column(project):
    _script(project, "Mine")

    body = _get(_user_with_role(project, PROJECT_ROLE_PI), project).json()

    assert "edit_id" not in body["rows"][0]
    assert "edit_id" not in [column["accessor"] for column in body["columns"]]


@pytest.mark.django_db
def test_a_manager_gets_an_edit_action_for_each_active_script_only(project):
    active = _script(project, "Active")
    _script(project, "Archived", archived_at=timezone.now())

    response = _get(_user_with_role(project, PROJECT_ROLE_ADMIN), project, sort="name")

    assert [(row["name"], row["edit_id"]) for row in response.json()["rows"]] == [
        ("Active", str(active.id)), ("Archived", None)]


@pytest.mark.django_db
def test_the_edit_column_is_declared_as_a_button_column(project):
    response = _get(_user_with_role(project, PROJECT_ROLE_ADMIN), project)

    column = next(column for column in response.json()["columns"] if column["accessor"] == "edit_id")
    assert column["data_type"] == "button"
    assert column["button_label"]


@pytest.mark.django_db
def test_a_member_without_an_etl_role_gets_404(project):
    response = _get(_user_with_role(project, PROJECT_ROLE_PARTICIPANT_RECRUITER), project)

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_non_member_gets_404(project):
    outsider = User.objects.create_user(username="outsider", password="pw")

    assert _get(outsider, project).status_code == 404


@pytest.mark.django_db
def test_the_datatype_filter_offers_the_datatypes_in_use_sorted_alphabetically(project):
    for name, datatype in (("A", "visit_occurrence"), ("B", "measurement"), ("C", "visit_occurrence")):
        EtlScript.objects.create(name=name, project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM, datatype_name=datatype)

    columns = _get(_user_with_role(project, PROJECT_ROLE_PI), project).json()["columns"]

    column = next(column for column in columns if column["accessor"] == "datatype_name")
    assert column["filter"] == {"kind": "dropdown", "options": [
        {"value": "measurement", "label": "measurement"}, {"value": "visit_occurrence", "label": "visit_occurrence"}]}


def _superuser_with_role(project):
    user = _user_with_role(project, PROJECT_ROLE_ADMIN)
    user.is_superuser = True
    user.save()
    return user


def _version(script):
    return EtlScriptVersion.objects.create(
        script=script, version=1, sha256="0" * 64, source=SimpleUploadedFile("s.py", b"x"))


@pytest.mark.django_db
def test_a_superuser_gets_a_delete_action_for_unused_archived_scripts_only(project):
    _script(project, "Active")
    unused = _script(project, "Unused", archived_at=timezone.now())
    used = _script(project, "Used", archived_at=timezone.now())
    PipelineBinding.objects.create(
        project=project, source_bucket="in", source_prefix="", raw_bucket="raw", raw_prefix="",
        script_version=_version(used))

    body = _get(_superuser_with_role(project), project, sort="name").json()

    assert [(row["name"], row["delete_id"]) for row in body["rows"]] == [
        ("Active", None), ("Unused", str(unused.id)), ("Used", None)]
    column = next(column for column in body["columns"] if column["accessor"] == "delete_id")
    assert (column["data_type"], bool(column["button_label"]), column["button_style"]) == (
        "button", True, "destructive")


@pytest.mark.django_db
def test_an_admin_who_is_not_a_superuser_gets_no_delete_column(project):
    _script(project, "Unused", archived_at=timezone.now())

    body = _get(_user_with_role(project, PROJECT_ROLE_ADMIN), project).json()

    assert "delete_id" not in body["rows"][0]
