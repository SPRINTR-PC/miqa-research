import pytest
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from contract.constants.audit_log import (
    AUTH_METHOD_LOCAL,
    AUTH_METHOD_OIDC,
    EVENT_TYPE_LOGIN,
    EVENT_TYPE_LOGIN_FAILED,
    EVENT_TYPE_LOGOUT,
)
from MiqaResearch.data.models import AuditLog

User = get_user_model()


def _request_with_session():
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


@pytest.fixture
def user(db):
    return User.objects.create_user(username="signaluser", email="signal@example.com")


@pytest.mark.django_db
def test_login_signal_creates_audit_log_with_local_method(user):
    request = _request_with_session()
    request.session["account_authentication_methods"] = [{"method": "password", "at": 0}]

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_LOGIN)
    assert entry.user == user
    assert entry.auth_method == AUTH_METHOD_LOCAL
    assert entry.session_key == request.session.session_key


@pytest.mark.django_db
def test_login_signal_detects_oidc_method(user):
    request = _request_with_session()
    request.session["account_authentication_methods"] = [{"method": "socialaccount", "at": 0}]

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_LOGIN)
    assert entry.auth_method == AUTH_METHOD_OIDC


@pytest.mark.django_db
def test_login_signal_defaults_to_local_without_tracked_methods(user):
    request = _request_with_session()

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_LOGIN)
    assert entry.auth_method == AUTH_METHOD_LOCAL


@pytest.mark.django_db
def test_logout_signal_creates_audit_log(user):
    request = _request_with_session()
    request.user = user
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    logout(request)

    assert AuditLog.objects.filter(event_type=EVENT_TYPE_LOGOUT, user=user).exists()


@pytest.mark.django_db
def test_login_failed_signal_creates_audit_log_without_user(db):
    request = _request_with_session()

    authenticate(request, username="no-such-user", password="wrong")

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_LOGIN_FAILED)
    assert entry.user is None
    assert entry.metadata["credentials"]["username"] == "no-such-user"
