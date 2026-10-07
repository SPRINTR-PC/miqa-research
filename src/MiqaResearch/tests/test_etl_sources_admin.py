"""Django admin for location grants and Source Locations (#268): the admin follows the same rules
as the Sources section. A grant is audited when added or deleted, can't be deleted while a Source
Location or Binding needs it, and its project/bucket/prefix are fixed once created. Source Locations
are read-only there -- they're managed in the Sources section, which keeps them inside a grant.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import EVENT_TYPE_ETL_LOCATION_GRANT_CREATED, EVENT_TYPE_ETL_LOCATION_GRANT_DELETED
from MiqaResearch.data.models import AuditLog, EtlLocationGrant, EtlSourceLocation, ResearchProject

User = get_user_model()


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Admin sources project", description="")


@pytest.fixture
def grant(project):
    return EtlLocationGrant.objects.create(project=project, bucket="incoming", prefix="")


@pytest.fixture
def admin_client(db):
    client = Client()
    client.force_login(User.objects.create_superuser(username="root", password="pw", email="root@example.org"))
    return client


def _url(name, *args):
    return reverse(f"admin:data_{name}", args=args)


@pytest.mark.django_db
def test_adding_a_grant_in_the_admin_is_audited(admin_client, project):
    admin_client.post(_url("etllocationgrant_add"), {"project": project.id, "bucket": "lab", "prefix": ""})

    grant = EtlLocationGrant.objects.get(bucket="lab")
    [event] = AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_LOCATION_GRANT_CREATED)
    assert event.metadata == {"etl_location_grant_id": str(grant.id)}


@pytest.mark.django_db
def test_deleting_an_unused_grant_in_the_admin_is_audited(admin_client, grant):
    admin_client.post(_url("etllocationgrant_delete", grant.id), {"post": "yes"})

    assert not EtlLocationGrant.objects.exists()
    assert AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_LOCATION_GRANT_DELETED).count() == 1


@pytest.mark.django_db
def test_a_grant_a_source_location_needs_is_not_deleted_in_the_admin(admin_client, project, grant):
    EtlSourceLocation.objects.create(project=project, name="Inside", bucket="incoming", prefix="a/")

    response = admin_client.post(_url("etllocationgrant_delete", grant.id), {"post": "yes"}, follow=True)

    assert EtlLocationGrant.objects.filter(id=grant.id).exists()
    assert "only allowed by this grant" in response.content.decode()
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_LOCATION_GRANT_DELETED).exists()


@pytest.mark.django_db
def test_grants_have_no_bulk_delete_action_that_would_skip_the_check(admin_client, grant):
    response = admin_client.get(_url("etllocationgrant_changelist"))

    assert "delete_selected" not in response.content.decode()


@pytest.mark.django_db
def test_an_existing_grants_project_bucket_and_prefix_cannot_be_changed(admin_client, project, grant):
    other = ResearchProject.objects.create(name="Other", description="")

    admin_client.post(_url("etllocationgrant_change", grant.id), {"project": other.id, "bucket": "x", "prefix": "y/"})

    grant.refresh_from_db()
    assert (grant.project_id, grant.bucket, grant.prefix) == (project.id, "incoming", "")


@pytest.mark.django_db
def test_source_locations_are_read_only_in_the_admin(admin_client, project, grant):
    location = EtlSourceLocation.objects.create(project=project, name="Inside", bucket="incoming", prefix="a/")
    other = ResearchProject.objects.create(name="Other", description="")

    add = admin_client.get(_url("etlsourcelocation_add"))
    admin_client.post(_url("etlsourcelocation_change", location.id), {"project": other.id, "name": "Moved"})
    delete = admin_client.post(_url("etlsourcelocation_delete", location.id), {"post": "yes"})

    location.refresh_from_db()
    assert add.status_code == 403
    assert (location.project_id, location.name) == (project.id, "Inside")
    assert delete.status_code == 403
