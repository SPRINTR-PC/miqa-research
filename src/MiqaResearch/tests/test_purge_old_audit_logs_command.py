import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_DICOM_RAW_GRANTED, EVENT_TYPE_LOGIN, EVENT_TYPE_WADO_CLIENT_ACCESS
from MiqaResearch.data.models import AuditLog


@pytest.mark.django_db
def test_purge_deletes_entries_older_than_retention_window(settings):
    settings.AUDIT_LOG_RETENTION_DAYS = 90
    old_entry = AuditLog.objects.record(EVENT_TYPE_LOGIN)
    AuditLog.objects.filter(pk=old_entry.pk).update(
        logtime=timezone.now() - datetime.timedelta(days=91)
    )
    recent_entry = AuditLog.objects.record(EVENT_TYPE_LOGIN)

    call_command("purge_old_audit_logs")

    assert not AuditLog.objects.filter(pk=old_entry.pk).exists()
    assert AuditLog.objects.filter(pk=recent_entry.pk).exists()


@pytest.mark.django_db
def test_data_access_events_are_kept_on_their_own_longer_retention(settings):
    """ADR 0024: data-access events (e.g. `dicom:raw` grants, client WADO fetches) outlive auth events."""
    settings.AUDIT_LOG_RETENTION_DAYS = 90
    settings.DATA_ACCESS_AUDIT_RETENTION_DAYS = 3650
    aged_access = AuditLog.objects.record(EVENT_TYPE_DICOM_RAW_GRANTED)
    expired_access = AuditLog.objects.record(EVENT_TYPE_WADO_CLIENT_ACCESS)
    aged_login = AuditLog.objects.record(EVENT_TYPE_LOGIN)
    AuditLog.objects.filter(pk__in=[aged_access.pk, aged_login.pk]).update(
        logtime=timezone.now() - datetime.timedelta(days=91))
    AuditLog.objects.filter(pk=expired_access.pk).update(logtime=timezone.now() - datetime.timedelta(days=3651))

    call_command("purge_old_audit_logs")

    assert AuditLog.objects.filter(pk=aged_access.pk).exists()
    assert not AuditLog.objects.filter(pk=expired_access.pk).exists()
    assert not AuditLog.objects.filter(pk=aged_login.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("event_type", [
    "annotation_created", "annotation_superseded", "annotation_retired",
    "segmentation_created", "segmentation_superseded", "segmentation_retired",
])
def test_annotation_and_segmentation_events_are_data_access_events(settings, event_type):
    """#287: create, supersede and retire of Annotations/Segmentations are data-access events (ADR 0024)."""
    settings.AUDIT_LOG_RETENTION_DAYS = 90
    settings.DATA_ACCESS_AUDIT_RETENTION_DAYS = 3650
    entry = AuditLog.objects.record(event_type)
    AuditLog.objects.filter(pk=entry.pk).update(logtime=timezone.now() - datetime.timedelta(days=91))

    call_command("purge_old_audit_logs")

    assert AuditLog.objects.filter(pk=entry.pk).exists()
