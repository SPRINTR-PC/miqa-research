from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from contract.constants.audit_log import (
    AUTH_METHOD_LOCAL,
    AUTH_METHOD_MFA,
    AUTH_METHOD_OIDC,
    EVENT_TYPE_LOGIN,
    EVENT_TYPE_LOGIN_FAILED,
    EVENT_TYPE_LOGOUT,
)
from MiqaResearch.data.models import AuditLog, ParticipantConsent, ParticipantConsentType
from MiqaResearch.tasks.consent.update_consent_summary import rebuild_consent_daily_active_summary

# allauth records how the current session authenticated (password/socialaccount/mfa)
# under this session key (see allauth.account.internal.flows.login.record_authentication).
# Not part of allauth's public API - hardcoded rather than imported; if it ever moves,
# this silently falls back to "local" rather than breaking.
_AUTHENTICATION_METHODS_SESSION_KEY = "account_authentication_methods"

_METHOD_MAP = {
    "password": AUTH_METHOD_LOCAL,
    "socialaccount": AUTH_METHOD_OIDC,
    "mfa": AUTH_METHOD_MFA,
}


def _resolve_auth_method(request):
    methods = request.session.get(_AUTHENTICATION_METHODS_SESSION_KEY, [])
    if not methods:
        return AUTH_METHOD_LOCAL
    return _METHOD_MAP.get(methods[-1].get("method"), AUTH_METHOD_LOCAL)


@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    AuditLog.objects.record(
        EVENT_TYPE_LOGIN, user=user, request=request, auth_method=_resolve_auth_method(request)
    )


@receiver(user_logged_out)
def log_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return
    AuditLog.objects.record(EVENT_TYPE_LOGOUT, user=user, request=request)


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request=None, **kwargs):
    AuditLog.objects.record(
        EVENT_TYPE_LOGIN_FAILED, request=request, metadata={"credentials": credentials}
    )


def _enqueue_consent_summary_rebuild(project_id: str) -> None:
    rebuild_consent_daily_active_summary.enqueue(project_id=project_id)


@receiver(post_save, sender=ParticipantConsent, dispatch_uid="data.consent_summary_on_save")
@receiver(post_delete, sender=ParticipantConsent, dispatch_uid="data.consent_summary_on_delete")
def schedule_consent_summary_rebuild(sender, instance, **kwargs):
    """Rebuild once per project per transaction, after commit."""
    project_id = (
        ParticipantConsentType.objects.filter(pk=instance.consent_type_id)
        .values_list("research_project_id", flat=True)
        .first()
    )
    if project_id is None:  # consent type gone (cascade delete)
        return
    project_id = str(project_id)
    pending = connection.__dict__.setdefault("_consent_summary_pending", set())
    if project_id in pending:
        return
    pending.add(project_id)

    def _run():
        pending.discard(project_id)
        _enqueue_consent_summary_rebuild(project_id)

    transaction.on_commit(_run)
