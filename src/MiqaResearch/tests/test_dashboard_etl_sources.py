"""View tests for the ETL Sources section (#268): who sees it, who may change Source Locations
and location grants through it, and the Binding wizard picking its source from a Source Location.
Role boundaries themselves are unit-tested in test_etl_permissions.py; the data rules in
test_etl_source_locations.py.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    EtlSourceLocation,
    PipelineBinding,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)

User = get_user_model()

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="ETL Sources Project", description="desc")


@pytest.fixture
def grant(project):
    return EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="redcap/")


@pytest.fixture
def location(project, grant):
    return EtlSourceLocation.objects.create(project=project, name="REDCap A", bucket="incoming", prefix="redcap/a/")


def _member(project, role_name, **user_flags):
    user = User.objects.create_user(
        username=f"user-{role_name.lower().replace(' ', '-')}-{len(user_flags)}", password="pw", **user_flags)
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    return client


def _admin(project):
    return _member(project, "Admin")


def _staff(project):
    return _member(project, "Contributor", is_staff=True)


def _sources_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=sources"


def _url(name, project, *args):
    return reverse(name, args=[project.id, *args])


# Visibility

@pytest.mark.django_db
@pytest.mark.parametrize("make_client", [
    _admin, _staff, lambda project: _member(project, "Contributor", is_superuser=True)])
def test_admins_staff_and_superusers_see_the_sources_section(project, location, make_client):
    response = make_client(project).get(_sources_url(project), **HTMX)

    assert response.status_code == 200
    content = response.content.decode()
    assert "REDCap A" in content
    assert "?section=sources" in content  # the sidebar link


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Data Manager", "PI"])
def test_other_etl_viewers_get_no_sources_link_and_a_404(project, location, role):
    client = _member(project, role)

    bindings = client.get(_url("dashboard_tab_etl_pipelines_content", project) + "?section=bindings", **HTMX)
    sources = client.get(_sources_url(project), **HTMX)

    assert bindings.status_code == 200
    assert "?section=sources" not in bindings.content.decode()
    assert sources.status_code == 404


@pytest.mark.django_db
def test_admins_see_grants_read_only_and_staff_get_the_grant_form(project, grant):
    admin_page = _admin(project).get(_sources_url(project), **HTMX).content.decode()
    staff_page = _staff(project).get(_sources_url(project), **HTMX).content.decode()

    grants_create = _url("dashboard_tab_etl_location_grants_create", project)
    assert "incoming/redcap/" in admin_page
    assert grants_create not in admin_page
    assert grants_create in staff_page


# Source Locations

@pytest.mark.django_db
def test_an_admin_creates_a_source_location_inside_a_grant(project, grant):
    response = _admin(project).post(
        _url("dashboard_tab_etl_source_locations_create", project),
        {"name": "REDCap B", "bucket": "incoming", "prefix": "redcap/b/"}, **HTMX)

    assert response.status_code == 200
    assert EtlSourceLocation.objects.filter(project=project, name="REDCap B", prefix="redcap/b/").exists()
    assert "REDCap B" in response.content.decode()


@pytest.mark.django_db
def test_a_source_location_outside_the_grants_is_shown_as_an_error(project, grant):
    response = _admin(project).post(
        _url("dashboard_tab_etl_source_locations_create", project),
        {"name": "Outside", "bucket": "elsewhere", "prefix": ""}, **HTMX)

    assert not EtlSourceLocation.objects.exists()
    assert "not inside any of this project" in response.content.decode()


@pytest.mark.django_db
def test_an_admin_renames_and_deletes_a_source_location(project, location):
    client = _admin(project)

    client.post(_url("dashboard_tab_etl_source_location_rename", project, location.id), {"name": "Renamed"}, **HTMX)
    location.refresh_from_db()
    assert location.name == "Renamed"

    client.post(_url("dashboard_tab_etl_source_location_delete", project, location.id), **HTMX)
    assert not EtlSourceLocation.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Data Manager", "PI", "Contributor"])
def test_non_admin_members_cannot_change_source_locations(project, location, role):
    client = _member(project, role)

    responses = [
        client.post(_url("dashboard_tab_etl_source_locations_create", project),
                    {"name": "X", "bucket": "incoming", "prefix": "redcap/x/"}, **HTMX),
        client.post(_url("dashboard_tab_etl_source_location_rename", project, location.id), {"name": "Y"}, **HTMX),
        client.post(_url("dashboard_tab_etl_source_location_delete", project, location.id), **HTMX),
    ]

    assert {response.status_code for response in responses} == {404}
    assert list(EtlSourceLocation.objects.values_list("name", flat=True)) == ["REDCap A"]


# Location grants

@pytest.mark.django_db
def test_staff_create_and_delete_location_grants(project):
    client = _staff(project)

    client.post(_url("dashboard_tab_etl_location_grants_create", project), {"bucket": "lab", "prefix": ""}, **HTMX)
    created = EtlLocationGrant.objects.get(project=project, bucket="lab")
    client.post(_url("dashboard_tab_etl_location_grant_delete", project, created.id), **HTMX)

    assert not EtlLocationGrant.objects.exists()


@pytest.mark.django_db
def test_an_admin_cannot_create_or_delete_grants(project, grant):
    client = _admin(project)

    create = client.post(
        _url("dashboard_tab_etl_location_grants_create", project), {"bucket": "lab", "prefix": ""}, **HTMX)
    delete = client.post(_url("dashboard_tab_etl_location_grant_delete", project, grant.id), **HTMX)

    assert (create.status_code, delete.status_code) == (403, 403)
    assert list(EtlLocationGrant.objects.values_list("bucket", flat=True)) == ["incoming"]


@pytest.mark.django_db
def test_deleting_a_grant_a_location_needs_is_refused_with_a_message(project, location, grant):
    response = _staff(project).post(_url("dashboard_tab_etl_location_grant_delete", project, grant.id), **HTMX)

    assert EtlLocationGrant.objects.filter(id=grant.id).exists()
    assert "only allowed by this grant" in response.content.decode()


# Binding wizard

@pytest.fixture
def native_version(db):
    script = EtlScript.objects.create(name="Native importer", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print()"), sha256="0" * 64)


def _binding_payload(native_version, source_location):
    return {
        "source_location": str(source_location), "script_version": str(native_version.id),
        "raw_retention": "move", "raw_bucket": "incoming", "raw_prefix": "redcap/raw/",
        "grouping_mode": "file", "quiescence_seconds": "", "config": "",
        "timeout_seconds_override": "", "memory_mb_override": "", "cpu_millicores_override": "",
    }


@pytest.mark.django_db
def test_the_wizard_offers_the_projects_source_locations_instead_of_free_text(project, location):
    content = _member(project, "Data Manager").get(
        _url("dashboard_tab_etl_pipelines_content", project) + "?section=bindings", **HTMX).content.decode()

    assert 'name="source_location"' in content
    assert "REDCap A" in content
    assert 'name="source_bucket"' not in content


@pytest.mark.django_db
def test_a_binding_created_from_a_source_location_copies_its_bucket_and_prefix(project, location, native_version):
    _member(project, "Data Manager").post(
        _url("dashboard_tab_etl_bindings_create", project), _binding_payload(native_version, location.id), **HTMX)

    binding = PipelineBinding.objects.get(project=project)
    assert (binding.source_location_id, binding.source_bucket, binding.source_prefix) == (
        location.id, "incoming", "redcap/a/")


@pytest.mark.django_db
def test_another_projects_source_location_cannot_be_chosen(project, location, native_version):
    other = ResearchProject.objects.create(name="Other", description="")
    theirs = EtlSourceLocation.objects.create(project=other, name="Theirs", bucket="incoming", prefix="redcap/z/")

    _member(project, "Data Manager").post(
        _url("dashboard_tab_etl_bindings_create", project), _binding_payload(native_version, theirs.id), **HTMX)

    assert not PipelineBinding.objects.exists()
