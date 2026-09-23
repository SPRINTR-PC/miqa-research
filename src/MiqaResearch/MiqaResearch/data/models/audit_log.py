from uuid import uuid7

from django.contrib.auth import get_user_model
from django.db import models

from contract.constants.audit_log import AUTH_METHOD_CHOICES, EVENT_TYPE_CHOICES
from helpers.http import get_client_ip

from .research_project import ResearchProject

User = get_user_model()


class AuditLogManager(models.Manager):
    def record(
        self,
        event_type,
        *,
        user=None,
        request=None,
        auth_method=None,
        ip_address=None,
        session_key=None,
        metadata=None,
        project=None,
    ):
        if request is not None:
            ip_address = ip_address or get_client_ip(request)
            session_key = session_key or getattr(
                getattr(request, "session", None), "session_key", None
            )
        return self.create(
            user=user,
            event_type=event_type,
            ip_address=ip_address,
            session_key=session_key,
            auth_method=auth_method,
            metadata=metadata or {},
            project=project,
        )


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    logtime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, db_index=True)
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    auth_method = models.CharField(max_length=16, choices=AUTH_METHOD_CHOICES, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    project = models.ForeignKey(
        ResearchProject, on_delete=models.SET_NULL, null=True, blank=True, db_index=True,
        help_text="The project an event is scoped to, e.g. an ETL management action; null for account-level events.")

    objects = AuditLogManager()

    class Meta:
        db_table = "mires_audit_log"
        ordering = ['-logtime']

    def __str__(self):
        return f"{self.event_type} ({self.user}) @ {self.logtime}"
