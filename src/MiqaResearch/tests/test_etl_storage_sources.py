"""Connected Storages (#394): a Source Location, and the Binding made from it, live in one storage;
a Location Grant only authorises its own storage, and the same bucket/prefix in two storages is two
different places."""
import pytest
from asgiref.sync import async_to_sync
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.actions.etl.bindings import create_pipeline_binding
from MiqaResearch.actions.etl.exceptions import EtlLocationInUse, EtlLocationOutsideGrant
from MiqaResearch.actions.etl.sources import (
    create_location_grant,
    create_source_location,
    delete_location_grant,
)
from MiqaResearch.data.models import (
    EtlLocationGrant,
    EtlScript,
    EtlScriptVersion,
    EtlSourceLocation,
    EtlStorage,
    PipelineBinding,
    ResearchProject,
)
from MiqaResearch.data.models.etl_storage import default_storage


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Storage sources project", description="")


@pytest.fixture
def lab(db):
    return EtlStorage.objects.create(name="Lab", access_key_id_env="A", secret_access_key_env="B")


def _call(action, **kwargs):
    return async_to_sync(action)(user=None, request=None, **kwargs)


def test_a_grant_on_another_storage_does_not_authorise_a_location(project, lab):
    EtlLocationGrant.objects.create(project=project, storage=default_storage(), bucket="incoming", prefix="")

    with pytest.raises(EtlLocationOutsideGrant):
        _call(create_source_location, project=project, storage=lab, name="Lab in", bucket="incoming", prefix="")


def test_a_location_takes_the_storage_of_the_grant_that_allows_it(project, lab):
    _call(create_location_grant, project=project, storage=lab, bucket="incoming", prefix="")

    location = _call(create_source_location, project=project, storage=lab, name="Lab in", bucket="incoming", prefix="")

    assert location.storage == lab


def test_the_same_bucket_and_prefix_in_two_storages_is_allowed(project, lab):
    _call(create_location_grant, project=project, storage=default_storage(), bucket="incoming", prefix="")
    _call(create_location_grant, project=project, storage=lab, bucket="incoming", prefix="")

    _call(create_source_location, project=project, storage=default_storage(), name="A", bucket="incoming", prefix="")
    _call(create_source_location, project=project, storage=lab, name="B", bucket="incoming", prefix="")

    assert EtlSourceLocation.objects.count() == 2


def test_deleting_a_grant_is_only_blocked_by_locations_in_its_own_storage(project, lab):
    default_grant = _call(
        create_location_grant, project=project, storage=default_storage(), bucket="incoming", prefix="")
    _call(create_location_grant, project=project, storage=lab, bucket="incoming", prefix="")
    _call(create_source_location, project=project, storage=lab, name="B", bucket="incoming", prefix="")

    _call(delete_location_grant, project=project, grant=default_grant)  # the lab location is not affected

    assert not EtlLocationGrant.objects.filter(storage=default_storage()).exists()


def test_deleting_a_grant_its_own_storage_location_needs_is_blocked(project, lab):
    grant = _call(create_location_grant, project=project, storage=lab, bucket="incoming", prefix="")
    _call(create_source_location, project=project, storage=lab, name="B", bucket="incoming", prefix="")

    with pytest.raises(EtlLocationInUse):
        _call(delete_location_grant, project=project, grant=grant)


def _script_version():
    script = EtlScript.objects.create(name="Native", origin=ETL_SCRIPT_ORIGIN_NATIVE, project=None)
    return EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("s.py", b"print()"), sha256="0" * 64)


def test_a_binding_takes_its_source_locations_storage_and_two_storages_do_not_conflict(project, lab):
    version = _script_version()
    locations = []
    for storage in (default_storage(), lab):
        _call(create_location_grant, project=project, storage=storage, bucket="incoming", prefix="")
        locations.append(_call(
            create_source_location, project=project, storage=storage, name=storage.name, bucket="incoming",
            prefix=""))

    bindings = [
        _call(create_pipeline_binding, project=project, source_location=location, script_version_id=version.id,
              raw_bucket="raw", raw_prefix="")
        for location in locations
    ]

    assert [b.storage for b in bindings] == [default_storage(), lab]
    assert PipelineBinding.objects.count() == 2


def _binding_form_data(location):
    return {"source_location": str(location.id), "script_version": "1", "raw_retention": "move",
            "raw_bucket": "raw", "raw_prefix": "", "grouping_mode": "file"}


def test_the_raw_bucket_must_be_granted_on_the_bindings_storage(project, lab):
    from MiqaResearch.interfaces.http.forms.etl import EtlBindingCreateForm

    EtlLocationGrant.objects.create(project=project, storage=lab, bucket="incoming", prefix="")
    EtlLocationGrant.objects.create(project=project, storage=default_storage(), bucket="raw", prefix="")
    location = EtlSourceLocation.objects.create(project=project, storage=lab, name="L", bucket="incoming", prefix="")

    form = EtlBindingCreateForm(
        _binding_form_data(location), location_grants=list(EtlLocationGrant.objects.filter(project=project)),
        source_locations=[location], script_version_choices=[("1", "v1")], can_choose_delete=False)

    assert not form.is_valid()
    assert "raw_bucket" in form.errors  # `raw` is only granted on the Default storage, not on Lab


def test_a_location_without_a_storage_takes_it_from_the_one_grant_that_allows_it(project, lab):
    _call(create_location_grant, project=project, storage=lab, bucket="incoming", prefix="")

    location = _call(create_source_location, project=project, name="Lab in", bucket="incoming", prefix="")

    assert location.storage == lab


def test_a_location_allowed_in_two_storages_needs_one_chosen(project, lab):
    from MiqaResearch.actions.etl.exceptions import EtlLocationConflict

    for storage in (default_storage(), lab):
        _call(create_location_grant, project=project, storage=storage, bucket="incoming", prefix="")

    with pytest.raises(EtlLocationConflict, match="storage"):
        _call(create_source_location, project=project, name="Either", bucket="incoming", prefix="")


@pytest.mark.parametrize(("can_choose_delete", "expected_initial"), [(True, "delete"), (False, "move")])
def test_datatype_delete_default_is_not_preselected_when_the_user_cannot_choose_delete(
        can_choose_delete, expected_initial):
    """Documents current behaviour (#411 review): a Datatype's "delete" Raw Retention default is preselected in the
    Binding wizard only for users who may choose Delete (project Admin); for others no default is preselected,
    so the field falls back to its own initial. Binding creation by the action does not gate on role."""
    from MiqaResearch.interfaces.http.forms.etl import EtlBindingCreateForm

    form = EtlBindingCreateForm(
        None, location_grants=[], source_locations=[], script_version_choices=[("1", "v1")],
        can_choose_delete=can_choose_delete, raw_retention_defaults={"1": "delete"})

    assert form.fields["raw_retention"].initial == expected_initial
