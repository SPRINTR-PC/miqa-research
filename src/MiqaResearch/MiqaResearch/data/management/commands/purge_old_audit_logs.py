import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from contract.constants.audit_log import DATA_ACCESS_EVENT_TYPES
from MiqaResearch.data.models import AuditLog


class Command(BaseCommand):
    help = (
        "Delete AuditLog rows past retention: data-access events (ADR 0024) after "
        "settings.DATA_ACCESS_AUDIT_RETENTION_DAYS, everything else after settings.AUDIT_LOG_RETENTION_DAYS."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        auth_days, access_days = settings.AUDIT_LOG_RETENTION_DAYS, settings.DATA_ACCESS_AUDIT_RETENTION_DAYS
        deleted_count, _ = AuditLog.objects.filter(
            logtime__lt=now - datetime.timedelta(days=auth_days)
        ).exclude(event_type__in=DATA_ACCESS_EVENT_TYPES).delete()
        deleted_access_count, _ = AuditLog.objects.filter(
            logtime__lt=now - datetime.timedelta(days=access_days), event_type__in=DATA_ACCESS_EVENT_TYPES
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} audit log record(s) older than {auth_days} days and "
                f"{deleted_access_count} data-access record(s) older than {access_days} days."
            )
        )
