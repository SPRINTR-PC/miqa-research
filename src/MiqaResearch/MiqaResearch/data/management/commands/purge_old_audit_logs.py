import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from MiqaResearch.data.models import AuditLog


class Command(BaseCommand):
    help = "Delete AuditLog rows older than settings.AUDIT_LOG_RETENTION_DAYS."

    def handle(self, *args, **options):
        cutoff = timezone.now() - datetime.timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
        deleted_count, _ = AuditLog.objects.filter(logtime__lt=cutoff).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} audit log record(s) older than "
                f"{settings.AUDIT_LOG_RETENTION_DAYS} days."
            )
        )
