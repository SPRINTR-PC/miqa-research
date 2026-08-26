from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from contract.constants.audit_log import (
    AUTH_METHOD_LOCAL,
    AUTH_METHOD_MFA,
    AUTH_METHOD_OIDC,
    EVENT_TYPE_LOGIN,
    EVENT_TYPE_LOGIN_FAILED,
    EVENT_TYPE_LOGOUT,
)
from MiqaResearch.data.models import AuditLog

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
