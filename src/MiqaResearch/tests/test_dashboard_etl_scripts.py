"""View tests for the ETL Scripts section's manage actions (#158): create/edit/archive a custom
Script and add a Version, gated by the ETL permissions policy, each writing an `etl_*` AuditLog
entry. Role-boundary logic itself is unit-tested in test_etl_permissions.py; this file checks that
the dashboard views actually enforce it and that the real DB/audit side effects happen.
"""
import html
import json
import re
from pathlib import PurePath

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


def _table_url(project):
    return reverse("api-v1:etl_scripts_table", args=[project.id])


def _new_modal(client, project):
    """The New script modal body."""
    return client.get(_create_url(project), **HTMX).content.decode()


def _edit_modal(client, project, script):
    """The Edit script modal body."""
    return client.get(_edit_url(project, script), **HTMX).content.decode()


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


def _code(source="print('hi')", language=".py"):
    """The editor's posted fields: the code itself, however it was entered, plus its language."""
    return {"source_code": source, "language": language}


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

    # no New script button
    assert "hx-get" not in body.split("<data-table")[0].split("Custom scripts are project-owned")[1]
    assert 'name="name"' not in body


@pytest.mark.django_db
def test_a_read_only_role_cannot_open_the_new_script_modal(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    assert client.get(_create_url(project), **HTMX).status_code == 403


@pytest.mark.django_db
def test_a_read_only_role_cannot_open_the_edit_script_modal(project):
    script = EtlScript.objects.create(name="Mine", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Investigator"))

    assert client.get(_edit_url(project, script), **HTMX).status_code == 403


@pytest.mark.django_db
def test_a_read_only_role_cannot_post_a_create_action(project):
    client = _client_as(_user_with_role(project, "Investigator"))

    response = client.post(_create_url(project), {"name": "x", "description": ""}, **HTMX)

    assert response.status_code == 403
    assert not EtlScript.objects.exists()


@pytest.mark.django_db
def test_the_scripts_table_shows_each_scripts_datatype(project):
    EtlScript.objects.create(
        name="Visit import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="visit_occurrence")
    client = _client_as(_user_with_role(project, "Investigator"))  # read-only: no create form listing choices

    rows = client.get(_table_url(project)).json()["rows"]

    assert [row["datatype_name"] for row in rows] == ["visit_occurrence"]


@pytest.mark.django_db
def test_the_scripts_section_lists_custom_scripts_in_a_data_table_and_offers_new_script_in_a_modal(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    body = client.get(_scripts_url(project)).content.decode()

    assert f'<data-table\n    id="etl-custom-scripts-table"\n    dataUrl="{_table_url(project)}"' in body
    assert f'hx-get="{_create_url(project)}" hx-target="#app-modal-content"' in body
    assert 'data-row-action-url="' + _edit_url(project, EtlScript(id="00000000-0000-0000-0000-000000000000")) in body
    assert "<details>" not in body.split("Built-in scripts")[0]


# --- Create custom script ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_data_manager_can_create_a_custom_script(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {
            "name": "REDCap import", "description": "Imports REDCap exports", "datatype": "measurement",
            **_code(),
        },
        **HTMX,
    )

    assert response.status_code == 200
    script = EtlScript.objects.get(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
    assert script.name == "REDCap import"
    assert script.versions.count() == 1
    assert response["HX-Trigger"] == "close-app-modal"


@pytest.mark.django_db
def test_an_invalid_new_script_reopens_the_modal_with_its_errors(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_create_url(project), {"name": "", "description": "keep me", **_code()}, **HTMX)

    assert response.status_code == 200
    assert response["HX-Retarget"] == "#app-modal-content"
    assert "HX-Trigger" not in response
    body = response.content.decode()
    assert "This field is required." in body
    assert "keep me" in body
    assert not EtlScript.objects.exists()


@pytest.mark.django_db
def test_a_new_script_produces_the_datatype_chosen_at_creation(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {"name": "Visit import", "description": "", "datatype": "visit_occurrence", **_code()},
        **HTMX,
    )

    assert EtlScript.objects.get(project=project).datatype_name == "visit_occurrence"


@pytest.mark.django_db
@pytest.mark.parametrize("datatype", ["not_a_registered_datatype", ""])
def test_a_script_cannot_be_created_without_a_registered_datatype(project, datatype):
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project), {"name": "Lab import", "description": "", "datatype": datatype, **_code()},
        **HTMX)

    assert not EtlScript.objects.exists()
    assert "etl-form-error" in response.content.decode()


@pytest.mark.django_db
def test_creating_a_script_records_an_audit_event_scoped_to_the_project_with_no_data_values(project):
    user = _user_with_role(project, "Admin")
    client = _client_as(user)

    client.post(
        _create_url(project),
        {"name": "REDCap import", "description": "", "datatype": "measurement", **_code()},
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
        {"name": "Too big", "description": "", "datatype": "measurement", **_code("way too many bytes")},
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

    body = _edit_modal(client, project, script)

    edit_form = re.search(rf'<form[^>]*{re.escape(_edit_url(project, script))}.*?</form>', body, re.DOTALL)
    assert edit_form is not None
    assert ('name="datatype"' in edit_form.group(0)) is offers_picker


@pytest.mark.django_db
def test_a_data_manager_can_add_a_new_version_to_a_custom_script(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_version_url(project, script), _code("v2 source"), **HTMX)

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
def test_an_archived_script_can_no_longer_be_opened_for_editing(project):
    script = EtlScript.objects.create(name="Gone", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Admin"))
    client.post(_archive_url(project, script), {}, **HTMX)

    assert client.get(_edit_url(project, script), **HTMX).status_code == 404


@pytest.mark.django_db
def test_another_projects_script_cannot_be_opened_for_editing(project):
    other = ResearchProject.objects.create(name="Other", description="d")
    script = EtlScript.objects.create(name="Theirs", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=other)
    client = _client_as(_user_with_role(project, "Admin"))

    assert client.get(_edit_url(project, script), **HTMX).status_code == 404


@pytest.mark.django_db
def test_the_edit_modal_is_titled_with_the_script_and_prefills_its_settings(project):
    script = EtlScript.objects.create(
        name="Consent import", description="From REDCap", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    body = _edit_modal(client, project, script)

    assert re.search(r'<h2 id="app-modal-title"[^>]*>\s*Edit script: Consent import', body)
    assert 'value="Consent import"' in body
    assert "From REDCap" in body


@pytest.mark.django_db
def test_an_invalid_edit_reopens_the_modal_with_its_errors(project):
    script = EtlScript.objects.create(name="Keep", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_edit_url(project, script), {"name": "", "description": ""}, **HTMX)

    assert response["HX-Retarget"] == "#app-modal-content"
    assert "This field is required." in response.content.decode()
    script.refresh_from_db()
    assert script.name == "Keep"


@pytest.mark.django_db
def test_a_saved_edit_closes_the_modal(project):
    script = EtlScript.objects.create(name="Old", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(_edit_url(project, script), {"name": "New", "description": ""}, **HTMX)

    assert response["HX-Trigger"] == "close-app-modal"


@pytest.mark.django_db
@pytest.mark.parametrize(("role_name", "offers_archive"), [("Data Manager", False), ("Admin", True)])
def test_only_admins_are_offered_archive_in_the_edit_modal(project, role_name, offers_archive):
    script = EtlScript.objects.create(name="Mine", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, role_name))

    body = _edit_modal(client, project, script)

    assert (_archive_url(project, script) in body) is offers_archive


# --- Language / sandbox image (#166) --------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(("extension", "image_key"), [(".py", "python-etl-v1"), (".r", "r-etl-v1")])
def test_a_new_scripts_version_runs_on_the_image_for_its_source_files_language(project, settings, extension, image_key):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {"name": "Lab import", "description": "", "datatype": "measurement", **_code(language=extension)},
        **HTMX)

    assert EtlScriptVersion.objects.get().image_key == image_key


@pytest.mark.django_db
def test_a_new_version_runs_on_the_image_for_its_own_source_files_language(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    script = EtlScript.objects.create(name="Lab import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_version_url(project, script), _code("main <- function(ctx) NULL", ".r"), **HTMX)

    assert EtlScriptVersion.objects.get(script=script).image_key == "r-etl-v1"


@pytest.mark.django_db
def test_a_source_file_in_an_unsupported_language_is_rejected_with_a_form_error(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    client = _client_as(_user_with_role(project, "Data Manager"))

    response = client.post(
        _create_url(project),
        {"name": "Lab import", "description": "", "datatype": "measurement", **_code(language=".sh")},
        **HTMX)

    assert not EtlScript.objects.exists()
    assert "Select a valid choice" in response.content.decode()


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
    """The config schema is typed (or loaded from a file) into an editor, so it is posted as text."""
    return content.decode()


@pytest.mark.django_db
def test_a_new_script_can_declare_a_config_schema(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {
            "name": "REDCap import", "datatype": "measurement", **_code(),
            "config_schema": _schema_upload(b'{"type": "object", "properties": {"delimiter": {"type": "string"}}}'),
        },
        **HTMX,
    )

    assert EtlScriptVersion.objects.get(script__project=project).config_schema == DELIMITER_SCHEMA


@pytest.mark.django_db
def test_a_script_created_without_a_config_schema_keeps_config_free_form(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(_create_url(project), {"name": "REDCap import", "datatype": "measurement", **_code()}, **HTMX)

    assert EtlScriptVersion.objects.get(script__project=project).config_schema is None


@pytest.mark.django_db
def test_a_new_version_can_declare_its_own_config_schema(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _version_url(project, script),
        {**_code("v2"), "config_schema": _schema_upload(
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
        {"name": "REDCap import", "datatype": "measurement", **_code(),
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
        _version_url(project, script), {**_code("v2"), "config_schema": _schema_upload(b"{nope")}, **HTMX)

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


@pytest.mark.django_db
def test_add_version_offers_a_required_code_editor_and_an_optional_config_schema_editor(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    version_form = re.search(r'<form[^>]*/versions/"[^>]*>.*?</form>', body, re.S)
    assert version_form is not None
    assert re.search(r'<textarea[^>]*name="source_code"[^>]*required', version_form.group(0))
    config_schema_input = re.search(r'<textarea[^>]*name="config_schema"[^>]*>', version_form.group(0))
    assert config_schema_input is not None
    assert "required" not in config_schema_input.group(0)


# --- Code editor, synthesized filename, schema preview (#393) -------------------------------------------------------


def _preview_url(project):
    return reverse("dashboard_tab_etl_datatype_schema", args=[project.id])


@pytest.mark.django_db
@pytest.mark.parametrize(("name", "extension", "stored"), [
    ("My Consent Import!", ".py", "my-consent-import.py"),
    ("Lab import", ".r", "lab-import.r"),
    ("???", ".py", "script.py"),
])
def test_typed_code_is_stored_under_a_filename_built_from_the_script_name_and_language(
        project, name, extension, stored):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project), {"name": name, "description": "", "datatype": "measurement", **_code(language=extension)},
        **HTMX)

    version = EtlScriptVersion.objects.get()
    assert PurePath(version.source.name).name == stored
    assert version.source.read() == b"print('hi')"


@pytest.mark.django_db
def test_a_script_needs_some_code(project):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project),
        {"name": "Empty", "description": "", "datatype": "measurement", **_code("")}, **HTMX)

    assert not EtlScript.objects.exists()


@pytest.mark.django_db
def test_the_create_form_offers_a_code_editor_a_language_choice_and_loading_from_a_file(project):
    client = _client_as(_user_with_role(project, "Data Manager"))
    body = _new_modal(client, project)
    assert re.search(r"<textarea[^>]*data-etl-code-editor[^>]*name=\"source_code\"|"
                     r"<textarea[^>]*name=\"source_code\"[^>]*data-etl-code-editor", body)
    assert re.search(r"<select[^>]*data-etl-language", body)
    assert '<option value=".py"' in body
    assert '<option value=".r"' in body
    assert "data-etl-load-file" in body
    assert "js/etl-code-editor.js" in client.get(_scripts_url(project), **HTMX).content.decode()


@pytest.mark.django_db
def test_add_version_prefills_the_editor_with_the_latest_versions_source(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(b"print('v1')", "script.py"), sha256="0" * 64)
    script.versions.create(version=2, source=_upload(b"print('v2 <b>')", "script.py"), sha256="1" * 64)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    assert "print(&#x27;v2 &lt;b&gt;&#x27;)" in body


@pytest.mark.django_db
def test_add_version_preselects_the_language_of_the_latest_version(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(b"x", "script.R"), sha256="0" * 64)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    assert re.search(r'<option value="\.r" selected', body)


@pytest.mark.django_db
def test_picking_a_datatype_shows_its_schema_and_an_example_row(project):
    response = _client_as(_user_with_role(project, "Data Manager")).get(
        _preview_url(project), {"datatype": "participant_consent"}, **HTMX)

    body = response.content.decode()
    assert response.status_code == 200
    for field in ("person_source_value", "consent_type", "consent_signed_date", "clinic_code"):
        assert field in body
    assert "required" in body
    assert "optional" in body
    assert "datetime" in body
    assert "etl-schema-example" in body
    assert "&quot;consent_type&quot;" in body


@pytest.mark.django_db
def test_the_consent_schema_documents_every_field(project):
    from MiqaResearch.etl_datatypes import get_datatype

    properties = get_datatype("participant_consent").schema.model_json_schema()["properties"]

    assert all(prop.get("description") for prop in properties.values())


@pytest.mark.django_db
def test_an_unknown_datatype_previews_nothing(project):
    response = _client_as(_user_with_role(project, "Data Manager")).get(
        _preview_url(project), {"datatype": "nope"}, **HTMX)

    assert response.status_code == 200
    assert "etl-schema-example" not in response.content.decode()


@pytest.mark.django_db
def test_a_read_only_role_cannot_preview_a_schema_through_the_manage_endpoint(project):
    response = _client_as(_user_with_role(project, "Annotator")).get(
        _preview_url(project), {"datatype": "participant_consent"}, **HTMX)

    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_the_edit_modal_still_renders_when_a_versions_source_cannot_be_read(project):
    script = EtlScript.objects.create(name="Broken", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    version = script.versions.create(version=1, source=_upload(b"x", "script.py"), sha256="0" * 64)
    version.source.storage.delete(version.source.name)

    response = _client_as(_user_with_role(project, "Data Manager")).get(_edit_url(project, script), **HTMX)

    assert response.status_code == 200
    assert "Broken" in response.content.decode()


@pytest.mark.django_db
def test_the_example_row_is_pretty_printed_over_several_lines(project):
    from MiqaResearch.etl_datatypes.describe import describe_datatype

    example = describe_datatype("participant_consent").example_row

    assert example.startswith("{\n  ")
    assert example.count("\n") > 5


# --- Config schema help (#393) --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_config_schema_label_has_a_help_button_opening_an_explanation(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)

    client = _client_as(_user_with_role(project, "Data Manager"))
    body = client.get(_scripts_url(project), **HTMX).content.decode()

    popover = re.search(r'<div[^>]*id="etl-config-schema-help"[^>]*popover[^>]*>.*?</div>', body, re.S)
    assert popover is not None
    assert "JSON Schema" in popover.group(0)
    assert "additionalProperties" in popover.group(0)
    # the button sits in each modal form that has the field: New script and the script's Add version
    for modal in (_new_modal(client, project), _edit_modal(client, project, script)):
        buttons = re.findall(r'<button[^>]*popovertarget="etl-config-schema-help"[^>]*>', modal)
        assert len([b for b in buttons if "popovertargetaction" not in b]) == 1
        assert all('type="button"' in b for b in buttons)


@pytest.mark.django_db
def test_a_read_only_role_gets_no_config_schema_help(project):
    body = _client_as(_user_with_role(project, "Annotator")).get(_scripts_url(project), **HTMX).content.decode()

    assert "etl-config-schema-help" not in body


@pytest.mark.django_db
def test_the_script_code_label_has_a_help_button_describing_the_script_format(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)

    client = _client_as(_user_with_role(project, "Data Manager"))
    body = client.get(_scripts_url(project), **HTMX).content.decode()

    popover = re.search(r'<div[^>]*id="etl-script-code-help"[^>]*popover[^>]*>.*?</div>', body, re.S)
    assert popover is not None
    expected_snippets = (
        "main(ctx)", "ctx.input_dir", "ctx.datatype", "ctx.config", "emit(", "ctx$input_dir", "manifest.json",
    )
    for expected in expected_snippets:
        assert expected in popover.group(0)
    for modal in (_new_modal(client, project), _edit_modal(client, project, script)):  # New script, Add version
        buttons = re.findall(r'<button[^>]*popovertarget="etl-script-code-help"[^>]*>', modal)
        assert len([b for b in buttons if "popovertargetaction" not in b]) == 1


@pytest.mark.django_db
def test_the_help_popovers_mark_their_code_examples_with_a_language_for_highlighting(project):
    body = _client_as(_user_with_role(project, "Data Manager")).get(_scripts_url(project), **HTMX).content.decode()

    languages = re.findall(r'<pre data-etl-highlight="(\w+)"', body)
    assert sorted(languages) == ["json", "python", "r"]


# --- Starter code per language (#393) -------------------------------------------------------------------------------


def _textarea_html(body, scope_start):
    start = body.index(scope_start)
    return re.search(r'<textarea[^>]*name="source_code"[^>]*>(.*?)</textarea>', body[start:], re.S)


@pytest.mark.django_db
def test_a_new_script_starts_from_a_python_skeleton_with_a_main_that_does_nothing(project):
    body = _new_modal(_client_as(_user_with_role(project, "Data Manager")), project)

    code = html.unescape(_textarea_html(body, "New script").group(1))
    assert "import csv" in code
    assert "def main(ctx):" in code
    assert re.search(r"def main\(ctx\):\n(?:\s+(?:#.*|\"\"\".*\"\"\")\n)*\s+pass\b", code)


@pytest.mark.django_db
def test_the_editor_is_given_a_starter_template_for_every_language(project, settings):
    settings.ETL_SCRIPT_IMAGE_KEYS = {".py": "python-etl-v1", ".r": "r-etl-v1"}
    body = _new_modal(_client_as(_user_with_role(project, "Data Manager")), project)

    attribute = re.search(r'<textarea[^>]*data-etl-templates="([^"]*)"', body)
    templates = json.loads(html.unescape(attribute.group(1)))
    assert "def main(ctx):" in templates[".py"]
    assert "main <- function(ctx)" in templates[".r"]


@pytest.mark.django_db
def test_add_version_starts_from_the_skeleton_when_the_script_has_no_version_yet(project):
    script = EtlScript.objects.create(name="Fresh", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    assert "def main(ctx):" in html.unescape(_textarea_html(body, "Add version").group(1))


def test_there_is_a_starter_template_for_each_configured_language():
    from MiqaResearch.interfaces.http.forms.etl import script_template

    assert "def main(ctx):" in script_template(".py")
    assert "main <- function(ctx)" in script_template(".r")
    assert script_template(".sh") == ""


# --- Required-field markers (#393) ----------------------------------------------------------------------------------


def _label_texts(form_html):
    """Each field label's text in a form, with a trailing "*" when it carries the required marker."""
    labels = {}
    for match in re.finditer(r'<(?:label|div) class="etl-field"[^>]*><span>(.*?)</span>', form_html, re.S):
        span = match.group(1)
        text = re.sub(r"<[^>]+>", "", re.sub(r'<button.*?</button>', "", span, flags=re.S)).strip()
        marked = 'class="etl-required"' in span
        labels[text.rstrip("* ").strip()] = marked
    return labels


@pytest.mark.django_db
def test_required_fields_of_the_new_script_form_are_marked_with_an_asterisk_after_the_label(project):
    create_form = _new_modal(_client_as(_user_with_role(project, "Data Manager")), project)
    marked = _label_texts(create_form)

    assert marked["Name"] and marked["Datatype"] and marked["Script code"] and marked["Language"]
    assert not marked["Description"]
    assert not marked["Config schema (optional JSON Schema)"]
    assert not marked["Load from file"]
    assert '<span class="etl-required" aria-hidden="true">*</span>' in create_form


# --- Config schema editor (#393) ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_config_schema_is_edited_in_a_json_code_editor_with_its_own_load_from_file(project):
    create_form = _new_modal(_client_as(_user_with_role(project, "Data Manager")), project)
    config_schema = re.search(r'<textarea[^>]*name="config_schema"[^>]*>', create_form).group(0)
    assert "data-etl-code-editor" in config_schema
    assert 'data-etl-fixed-language=".json"' in config_schema
    assert 'data-etl-load-file="config_schema"' in create_form
    assert 'data-etl-load-file="source_code"' in create_form  # the script code keeps its own, separate input
    assert 'type="file" name="config_schema"' not in create_form


@pytest.mark.django_db
@pytest.mark.parametrize("blank", ["", "   \n  "])
def test_a_blank_config_schema_means_no_schema(project, blank):
    client = _client_as(_user_with_role(project, "Data Manager"))

    client.post(
        _create_url(project), {"name": "REDCap import", "datatype": "measurement", **_code(), "config_schema": blank},
        **HTMX)

    assert EtlScriptVersion.objects.get(script__project=project).config_schema is None


@pytest.mark.django_db
def test_add_version_prefills_the_config_schema_editor_with_the_latest_versions_schema(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64, config_schema={"type": "object"})
    script.versions.create(version=2, source=_upload(), sha256="1" * 64, config_schema=DELIMITER_SCHEMA)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    version_form = re.search(r'<form[^>]*/versions/"[^>]*>.*?</form>', body, re.S).group(0)
    textarea = re.search(r'<textarea[^>]*name="config_schema"[^>]*>(.*?)</textarea>', version_form, re.S)
    prefilled = html.unescape(textarea.group(1))
    assert json.loads(prefilled) == DELIMITER_SCHEMA
    assert "\n  " in prefilled  # pretty-printed, not one long line


@pytest.mark.django_db
def test_add_version_leaves_the_config_schema_editor_empty_when_the_latest_version_has_none(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)

    body = _edit_modal(_client_as(_user_with_role(project, "Data Manager")), project, script)

    version_form = re.search(r'<form[^>]*/versions/"[^>]*>.*?</form>', body, re.S).group(0)
    assert re.search(r'<textarea[^>]*name="config_schema"[^>]*>\s*</textarea>', version_form)


@pytest.mark.django_db
def test_help_buttons_are_not_inside_a_label_so_clicking_the_field_or_its_label_cannot_open_a_popover(project):
    script = EtlScript.objects.create(name="Script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    script.versions.create(version=1, source=_upload(), sha256="0" * 64)

    client = _client_as(_user_with_role(project, "Data Manager"))

    for body in (_new_modal(client, project), _edit_modal(client, project, script)):
        labels = re.findall(r"<label\b.*?</label>", body, re.S)
        assert labels  # the plain fields still use labels
        assert not [label for label in labels if "popovertarget" in label]
        # the buttons are still there, one per popover in each modal
        for popover in ("etl-script-code-help", "etl-config-schema-help"):
            opener = rf'<button[^>]*popovertarget="{popover}"(?![^>]*popovertargetaction)[^>]*>'
            assert len(re.findall(opener, body)) == 1
