"""View tests for Connected Storages in the ETL Sources section (#394): staff pick a storage when
granting a location and browse its buckets/folders; others can't. Data rules live in
test_etl_storage_*.py."""
import boto3
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from moto import mock_aws

from contract.constants.audit_log import EVENT_TYPE_ETL_STORAGE_BROWSED
from MiqaResearch.data.models import (
    AuditLog,
    EtlLocationGrant,
    EtlStorage,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.data.models.etl_storage import default_storage

User = get_user_model()
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Storage views project", description="desc")


@pytest.fixture
def lab(db):
    return EtlStorage.objects.create(
        name="Lab", access_key_id_env="LAB_VIEW_KEY", secret_access_key_env="LAB_VIEW_SECRET"
    )


def _member(project, role_name, **flags):
    user = User.objects.create_user(username=f"u-{role_name}-{len(flags)}", password="pw", **flags)
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.create(user=user, project=project, role=role)
    client = Client()
    client.force_login(user)
    return client


def _staff(project):
    return _member(project, "Contributor", is_staff=True)


def _browse_url(project, storage):
    return reverse("dashboard_tab_etl_storage_browse", args=[project.id, storage.id])


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="alpha")
        client.put_object(Bucket="alpha", Key="a/x/1.csv", Body=b"top secret contents")
        client.put_object(Bucket="alpha", Key="a/top.csv", Body=b"x")
        yield client


def test_staff_browse_buckets_then_folders_and_never_see_contents(project, s3):
    client = _staff(project)

    buckets = client.get(_browse_url(project, default_storage()), **HTMX).content.decode()
    folders = client.get(_browse_url(project, default_storage()) + "?bucket=alpha&prefix=a/", **HTMX).content.decode()

    assert "alpha" in buckets
    assert "a/x/" in folders and "a/top.csv" in folders
    assert "top secret contents" not in folders
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_STORAGE_BROWSED).count() == 2


@pytest.mark.parametrize("role", ["Admin", "Data Manager", "PI"])
def test_project_roles_without_staff_cannot_browse(project, s3, role):
    response = _member(project, role).get(_browse_url(project, default_storage()), **HTMX)

    assert response.status_code in (403, 404)
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_STORAGE_BROWSED).exists()


def test_a_browse_failure_is_shown_inline_with_the_typed_fallback_still_possible(project, lab, monkeypatch):
    monkeypatch.delenv("LAB_VIEW_KEY", raising=False)

    response = _staff(project).get(_browse_url(project, lab), **HTMX)

    assert response.status_code == 200
    assert "credentials not configured" in response.content.decode()


def test_the_grant_form_offers_every_storage(project, lab):
    page = _staff(project).get(
        reverse("dashboard_tab_etl_pipelines_content", args=[project.id]) + "?section=sources", **HTMX
    ).content.decode()

    assert 'name="storage"' in page and "Lab" in page and "Default" in page


def test_a_grant_is_created_on_the_chosen_storage(project, lab):
    _staff(project).post(
        reverse("dashboard_tab_etl_location_grants_create", args=[project.id]),
        {"storage": str(lab.id), "bucket": "alpha", "prefix": "a/"}, **HTMX)

    assert EtlLocationGrant.objects.get(bucket="alpha").storage == lab


def test_a_grant_without_a_storage_uses_the_default(project):
    _staff(project).post(
        reverse("dashboard_tab_etl_location_grants_create", args=[project.id]),
        {"bucket": "alpha", "prefix": ""}, **HTMX)

    assert EtlLocationGrant.objects.get(bucket="alpha").storage == default_storage()
