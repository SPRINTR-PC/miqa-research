import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_LOGIN
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
