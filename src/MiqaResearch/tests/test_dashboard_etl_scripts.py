"""View tests for the ETL Scripts section's manage actions (#158): create/edit/archive a custom
Script and add a Version, gated by the ETL permissions policy, each writing an `etl_*` AuditLog
entry. Role-boundary logic itself is unit-tested in test_etl_permissions.py; this file checks that
the dashboard views actually enforce it and that the real DB/audit side effects happen.
"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import (
    EVENT_TYPE_ETL_SCRIPT_ARCHIVED,
    EVENT_TYPE_ETL_SCRIPT_CREATED,
    EVENT_TYPE_ETL_SCRIPT_UPDATED,
    EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED,
)
from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM, ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    AuditLog,
    EtlScript,
    EtlScriptVersion,
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
    return ResearchProject.objects.create(name="ETL Scripts Project", description="desc")


def _user_with_role(project, role_name):
    user = User.objects.create_user(username=f"user-{role_name.lower().replace(' ', '-')}", password="pw")
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    return user


def _client_as(user):
    client = Client()
    client.force_login(user)
    return client


def _scripts_url(project):
    return reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=scripts"


def _create_url(project):
    return reverse("dashboard_tab_etl_scripts_create", args=[project.id])


def _edit_url(project, script):
    return reverse("dashboard_tab_etl_script_edit", args=[project.id, script.id])


def _version_url(project, script):
    return reverse("dashboard_tab_etl_script_version_create", args=[project.id, script.id])


def _archive_url(project, script):
    return reverse("dashboard_tab_etl_script_archive", args=[project.id, script.id])


def _upload(name=b"print('hi')", filename="script.py"):
    return SimpleUploadedFile(filename, name, content_type="text/x-python")


# --- Visibility -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_role_outside_the_visible_set_gets_404_on_the_scripts_section(project):
    client = _client_as(_user_with_role(project, "Contributor"))

    response = client.get(_scripts_url(project))

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_read_only_role_sees_the_section_but_no_create_form(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    body = client.get(_scripts_url(project)).content.decode()

    assert "No scripts registered yet" in body
    assert 'name="name"' not in body  # no create-script form rendered


@pytest.mark.django_db
def test_a_read_only_role_cannot_post_a_create_action(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    response = client.post(_create_url(project), {"name": "x", "description": ""}, **HTMX)

    assert response.status_code == 403
    assert not EtlScript.objects.exists()


@pytest.mark.django_db
def test_the_scripts_section_shows_each_scripts_datatype(project):
    EtlScript.objects.create(
        name="Visit import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="visit_occurrence")
    client = _client_as(_user_with_role(project, "Investigator"))  # read-only: no create form listing choices

    body = client.get(_scripts_url(project)).content.decode()

    assert "visit_occurrence" in body


# --- Create custom script ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_create_a_custom_script(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {
            "name": "REDCap import", "description": "Imports REDCap exports", "datatype": "measurement",
            "source": _upload(),
        },
        **HTMX,
    )

    assert response.status_code == 200
    script = EtlScript.objects.get(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
    assert script.name == "REDCap import"
    assert script.versions.count() == 1
    assert "REDCap import" in response.content.decode()


@pytest.mark.django_db
def test_a_new_script_produces_the_datatype_chosen_at_creation(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {"name": "Visit import", "description": "", "datatype": "visit_occurrence", "source": _upload()},
        **HTMX,
    )

    assert EtlScript.objects.get(project=project).datatype_name == "visit_occurrence"


@pytest.mark.django_db
@pytest.mark.parametrize("datatype", ["not_a_registered_datatype", ""])
def test_a_script_cannot_be_created_without_a_registered_datatype(project, datatype):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project), {"name": "Lab import", "description": "", "datatype": datatype, "source": _upload()},
        **HTMX)

    assert not EtlScript.objects.exists()
    assert "etl-form-error" in response.content.decode()


@pytest.mark.django_db
def test_creating_a_script_records_an_audit_event_scoped_to_the_project_with_no_data_values(project):
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    client.post(
        _create_url(project),
        {"name": "REDCap import", "description": "", "datatype": "measurement", "source": _upload()},
        **HTMX,
    )

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_SCRIPT_CREATED)
    assert entry.user_id == user.id
    assert entry.project_id == project.id
    assert "REDCap" not in str(entry.metadata)
    assert set(entry.metadata.keys()) == {"etl_script_id", "datatype"}
    assert entry.metadata["datatype"] == "measurement"  # a code-registered identifier, not a data value


@pytest.mark.django_db
def test_an_oversized_source_file_is_rejected_with_a_form_error(project, settings):
    settings.ETL_SCRIPT_MAX_SOURCE_BYTES = 4
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(
        _create_url(project),
        {"name": "Too big", "description": "", "datatype": "measurement", "source": _upload(b"way too many bytes")},
        **HTMX)

    assert response.status_code == 200
    assert not EtlScript.objects.filter(name="Too big").exists()
    assert "at most 4 bytes" in response.content.decode()


# --- Edit and add version ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_edit_a_custom_scripts_name_and_description(project):
    script = EtlScript.objects.create(name="Old name", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_edit_url(project, script), {"name": "New name", "description": "Updated"}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 200
    assert script.name == "New name"
    assert script.description == "Updated"
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_UPDATED, project=project).exists()


@pytest.mark.django_db
def test_a_script_created_without_a_datatype_can_have_one_set_by_editing_it(project):
    script = EtlScript.objects.create(name="Legacy import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _edit_url(project, script), {"name": "Legacy import", "description": "", "datatype": "measurement"}, **HTMX)

    script.refresh_from_db()
    assert script.datatype_name == "measurement"


@pytest.mark.django_db
def test_a_scripts_datatype_cannot_be_changed_once_set(project):
    script = EtlScript.objects.create(
        name="Visit import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="visit_occurrence")
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _edit_url(project, script), {"name": "Visit import", "description": "", "datatype": "measurement"}, **HTMX)

    script.refresh_from_db()
    assert script.datatype_name == "visit_occurrence"


@pytest.mark.django_db
@pytest.mark.parametrize(("datatype_name", "offers_picker"), [("", True), ("measurement", False)])
def test_the_edit_form_offers_a_datatype_picker_only_while_none_is_set(project, datatype_name, offers_picker):
    script = EtlScript.objects.create(
        name="Import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name=datatype_name)
    client = _client_as(_user_with_role(project, "Data Manager"))

    body = client.get(_scripts_url(project)).content.decode()

    edit_form = re.search(rf'<form[^>]*{re.escape(_edit_url(project, script))}.*?</form>', body, re.DOTALL)
    assert edit_form is not None
    assert ('name="datatype"' in edit_form.group(0)) is offers_picker


@pytest.mark.django_db
def test_a_data_manager_can_add_a_new_version_to_a_custom_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_version_url(project, script), {"source": _upload(b"v2 source")}, **HTMX)

    assert response.status_code == 200
    assert list(script.versions.order_by("version").values_list("version", flat=True)) == [1, 2]
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED, project=project).exists()


@pytest.mark.django_db
def test_a_native_script_cannot_be_edited_even_by_an_admin(project):
    native = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_edit_url(project, native), {"name": "Hijacked", "description": ""}, **HTMX)

    native.refresh_from_db()
    assert response.status_code == 200
    assert native.name == "Native"
    assert "only this project" in response.content.decode().lower()


# --- Archive (Admin-only) ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_cannot_archive_a_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_archive_url(project, script), {}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 403
    assert script.archived_at is None


@pytest.mark.django_db
def test_an_admin_can_archive_a_custom_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_archive_url(project, script), {}, **HTMX)

    script.refresh_from_db()
    assert response.status_code == 200
    assert script.archived_at is not None
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_ARCHIVED, project=project).exists()


@pytest.mark.django_db
def test_archiving_a_native_script_is_rejected_with_a_visible_error(project):
    native = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    client = _client_as(_user_with_role(project, "Admin"))

    response = client.post(_archive_url(project, native), {}, **HTMX)

    native.refresh_from_db()
    assert response.status_code == 200
    assert native.archived_at is None
    assert "only this project" in response.content.decode().lower()


@pytest.mark.django_db
def test_an_archived_scripts_manage_controls_no_longer_render(project):
    script = EtlScript.objects.create(name="Gone", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    admin = _user_with_role(project, "Admin")
    client = _client_as(admin)
    client.post(_archive_url(project, script), {}, **HTMX)

    body = client.get(_scripts_url(project)).content.decode()

    assert "archived" in body
    row = re.search(r"<li>.*?Gone.*?</li>", body, re.DOTALL)
    assert row is not None
    assert "Archive" not in row.group(0)


# --- Language / sandbox image (#166) --------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(("filename", "image_key"), [("import.py", "python-etl-v1"), ("import.R", "r-etl-v1")])
def test_a_new_scripts_version_runs_on_the_image_for_its_source_files_language(project, settings, filename, image_key):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {"name": "Lab import", "description": "", "datatype": "measurement", "source": _upload(filename=filename)},
        **HTMX)

    assert EtlScriptVersion.objects.get().image_key == image_key


@pytest.mark.django_db
def test_a_new_version_runs_on_the_image_for_its_own_source_files_language(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    script = EtlScript.objects.create(name="Lab import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_version_url(project, script), {"source": _upload(b"main <- function(ctx) NULL", "v2.R")}, **HTMX)

    assert EtlScriptVersion.objects.get(script=script).image_key == "r-etl-v1"


@pytest.mark.django_db
def test_a_source_file_in_an_unsupported_language_is_rejected_with_a_form_error(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {"name": "Lab import", "description": "", "datatype": "measurement", "source": _upload(filename="import.sh")},
        **HTMX)

    assert not EtlScript.objects.exists()
    assert "must be a .py or .r file" in response.content.decode()


# --- Customize a native script (#226) -------------------------------------------------------------------------------


def _customize_url(project, script):
    return reverse("dashboard_tab_etl_script_customize", args=[project.id, script.id])


def _native_script_with_versions(*sources):
    script = EtlScript.objects.create(
        name="CSV → participant consent", description="Reads consent exports.", origin=ETL_SCRIPT_ORIGIN_NATIVE,
        project=None, datatype_name="participant_consent")
    for number, source in enumerate(sources, start=1):
        EtlScriptVersion.objects.create(
            script=script, version=number, source=_upload(source, "csv_participant_consent.py"),
            sha256=str(number) * 64, image_key="python-etl-v1")
    return script


@pytest.mark.django_db
def test_customizing_a_native_script_copies_its_latest_version_into_a_project_script(project):
    native = _native_script_with_versions(b"# v1", b"# v2")
    user = _user_with_role(project, "Data Manager")

    _client_as(user).post(_customize_url(project, native), **HTMX)

    copy = EtlScript.objects.get(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
    assert copy.datatype_name == "participant_consent"
    assert copy.description == "Reads consent exports."
    version = copy.versions.get()
    assert version.version == 1
    assert version.source.read() == b"# v2"
    assert version.image_key == "python-etl-v1"
    entry = AuditLog.objects.get(event_type=EVENT_TYPE_ETL_SCRIPT_CREATED)
    assert entry.user_id == user.id
    assert entry.metadata == {
        "etl_script_id": str(copy.id), "datatype": "participant_consent", "customized_from": str(native.id)}


@pytest.mark.django_db
def test_a_read_only_role_cannot_customize_a_native_script(project):
    native = _native_script_with_versions(b"# v1")

    response = _client_as(_user_with_role(project, "Investigator")).post(_customize_url(project, native), **HTMX)

    assert response.status_code == 403
    assert not EtlScript.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_only_a_native_script_can_be_customized(project):
    custom = EtlScript.objects.create(name="Own", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)

    response = _client_as(_user_with_role(project, "Data Manager")).post(_customize_url(project, custom), **HTMX)

    assert EtlScript.objects.filter(project=project).count() == 1
    assert "Only an active native Script can be customized." in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(("role_name", "can_customize"), [("Data Manager", True), ("Investigator", False)])
def test_only_managers_are_offered_customize_on_a_native_script(project, role_name, can_customize):
    native = _native_script_with_versions(b"# v1")

    body = _client_as(_user_with_role(project, role_name)).get(_scripts_url(project)).content.decode()

    assert "participant_consent" in body
    assert (_customize_url(project, native) in body) is can_customize


# --- Config schema (#238) ---------------------------------------------------------------------------------------

DELIMITER_SCHEMA = {"type": "object", "properties": {"delimiter": {"type": "string"}}}


def _schema_upload(content):
    return SimpleUploadedFile("config.schema.json", content, content_type="application/json")


@pytest.mark.django_db
def test_a_new_script_can_declare_a_config_schema(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {
            "name": "REDCap import", "datatype": "measurement", "source": _upload(),
            "config_schema": _schema_upload(b'{"type": "object", "properties": {"delimiter": {"type": "string"}}}'),
        },
        **HTMX,
    )

    assert EtlScriptVersion.objects.get(script__project=project).config_schema == DELIMITER_SCHEMA


@pytest.mark.django_db
def test_a_script_created_without_a_config_schema_keeps_config_free_form(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_create_url(project), {"name": "REDCap import", "datatype": "measurement", "source": _upload()}, **HTMX)

    assert EtlScriptVersion.objects.get(script__project=project).config_schema is None


@pytest.mark.django_db
def test_a_new_version_can_declare_its_own_config_schema(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _version_url(project, script),
        {"source": _upload(b"v2"), "config_schema": _schema_upload(
            b'{"type": "object", "properties": {"delimiter": {"type": "string"}}}')},
        **HTMX,
    )

    assert list(script.versions.order_by("version").values_list("config_schema", flat=True)) == [
        None, DELIMITER_SCHEMA]


@pytest.mark.django_db
@pytest.mark.parametrize("content, message", [
    (b"{not json", "not valid JSON"),
    (b'["a list"]', "must be a JSON object"),
    (b'{"type": "no-such-type"}', "not a valid JSON Schema"),
])
def test_a_malformed_config_schema_is_rejected_with_a_form_error(project, content, message):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {"name": "REDCap import", "datatype": "measurement", "source": _upload(),
         "config_schema": _schema_upload(content)},
        **HTMX,
    )

    assert not EtlScript.objects.filter(project=project).exists()
    assert message in response.content.decode()


@pytest.mark.django_db
def test_a_malformed_config_schema_on_a_new_version_is_rejected(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _version_url(project, script), {"source": _upload(b"v2"), "config_schema": _schema_upload(b"{nope")}, **HTMX)

    assert script.versions.count() == 1
    assert "not valid JSON" in response.content.decode()


@pytest.mark.django_db
def test_customizing_a_native_script_copies_its_config_schema(project):
    native = _native_script_with_versions(b"# v1")
    EtlScriptVersion.objects.filter(script=native).delete()
    EtlScriptVersion.objects.create(
        script=native, version=1, source=_upload(b"# v1", "csv_participant_consent.py"), sha256="1" * 64,
        config_schema=DELIMITER_SCHEMA)

    _client_as(_user_with_role(project, "Data Manager")).post(_customize_url(project, native), **HTMX)

    assert EtlScriptVersion.objects.get(script__project=project).config_schema == DELIMITER_SCHEMA


@pytest.mark.django_db
def test_the_scripts_section_shows_which_versions_declare_a_config_schema(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64, config_schema=DELIMITER_SCHEMA)

    response = _client_as(_user_with_role(project, "Data Manager")).get(_scripts_url(project), **HTMX)

    assert "Config schema" in response.content.decode()
