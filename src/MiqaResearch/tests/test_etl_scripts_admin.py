"""Django admin hard delete of an ETL Script: superuser only, archived only, and only while no Binding or
Job points at any of its Versions. Audited."""
from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from contract.constants.audit_log import EVENT_TYPE_ETL_SCRIPT_DELETED
from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    AuditLog,
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
)

User = get_user_model()


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Script admin project", description="")


@pytest.fixture
def script(project):
    script = EtlScript.objects.create(
        name="Old", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, archived_at=datetime.now(UTC))
    EtlScriptVersion.objects.create(
        script=script, version=1, sha256="0" * 64,
        source=SimpleUploadedFile("script.py", b"print('hi')", content_type="text/x-python"))
    return script


@pytest.fixture
def admin_client(db):
    client = Client()
    client.force_login(User.objects.create_superuser(username="root", password="pw", email="root@example.org"))
    return client


def _delete(client, script):
    return client.post(reverse("admin:data_etlscript_delete", args=[script.id]), {"post": "yes"})


@pytest.mark.django_db
def test_superuser_deletes_an_unused_archived_script(admin_client, script):
    _delete(admin_client, script)

    assert not EtlScript.objects.exists()
    assert not EtlScriptVersion.objects.exists()
    [event] = AuditLog.objects.filter(event_type=EVENT_TYPE_ETL_SCRIPT_DELETED)
    assert event.metadata == {"etl_script_id": str(script.id)}


@pytest.mark.django_db
def test_an_active_script_is_not_deleted(admin_client, script):
    EtlScript.objects.filter(pk=script.pk).update(archived_at=None)

    _delete(admin_client, script)

    assert EtlScript.objects.filter(pk=script.pk).exists()


@pytest.mark.django_db
def test_a_script_with_a_binding_is_not_deleted(admin_client, project, script):
    PipelineBinding.objects.create(
        project=project, source_bucket="in", source_prefix="", raw_bucket="raw", raw_prefix="",
        script_version=script.versions.get())

    _delete(admin_client, script)

    assert EtlScript.objects.filter(pk=script.pk).exists()


@pytest.mark.django_db
def test_a_script_with_a_job_is_not_deleted(admin_client, project, script):
    version = script.versions.get()
    other = EtlScriptVersion.objects.create(
        script=EtlScript.objects.create(name="Other", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project),
        version=1, sha256="1" * 64, source=SimpleUploadedFile("o.py", b"x"))
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="in", source_prefix="", raw_bucket="raw", raw_prefix="",
        script_version=other)
    EtlJob.objects.create(binding=binding, script_version=version)

    _delete(admin_client, script)

    assert EtlScript.objects.filter(pk=script.pk).exists()


@pytest.mark.django_db
def test_a_non_superuser_staff_cannot_delete(script):
    staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
    client = Client()
    client.force_login(staff)

    _delete(client, script)

    assert EtlScript.objects.filter(pk=script.pk).exists()
