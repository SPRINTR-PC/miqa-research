import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_SESSION_EXPIRED
from MiqaResearch.data.models import AuditLog
from MiqaResearch.middleware import SessionTimeoutMiddleware

User = get_user_model()


def _request_with_session():
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


@pytest.fixture
def user(db):
    return User.objects.create_user(username="timeoutuser", email="timeout@example.com")


@pytest.mark.django_db
def test_skips_enforcement_for_anonymous_user(settings):
    settings.DEBUG = False
    request = _request_with_session()
    request.user = AnonymousUser()

    result = SessionTimeoutMiddleware(lambda r: "response")(request)

    assert result == "response"


@pytest.mark.django_db
def test_skips_enforcement_when_debug_true(user, settings):
    settings.DEBUG = True
    request = _request_with_session()
    request.user = user
    request.session["_mires_session_created_at"] = 0

    SessionTimeoutMiddleware(lambda r: "response")(request)

    assert request.user == user


@pytest.mark.django_db
def test_initializes_timestamps_on_first_request(user, settings):
    settings.DEBUG = False
    request = _request_with_session()
    request.user = user

    SessionTimeoutMiddleware(lambda r: "response")(request)

    assert "_mires_session_created_at" in request.session
    assert "_mires_session_last_activity" in request.session
    assert request.user == user


@pytest.mark.django_db
def test_updates_last_activity_when_within_limits(user, settings):
    settings.DEBUG = False
    request = _request_with_session()
    request.user = user
    now = timezone.now().timestamp()
    request.session["_mires_session_created_at"] = now
    request.session["_mires_session_last_activity"] = now - 10

    SessionTimeoutMiddleware(lambda r: "response")(request)

    assert request.user == user
    assert request.session["_mires_session_last_activity"] > now - 10


@pytest.mark.django_db
def test_logs_out_and_records_audit_log_on_idle_timeout(user, settings):
    settings.DEBUG = False
    settings.SESSION_IDLE_TIMEOUT = 1800
    settings.SESSION_COOKIE_AGE = 28800
    request = _request_with_session()
    request.user = user
    now = timezone.now().timestamp()
    request.session["_mires_session_created_at"] = now
    request.session["_mires_session_last_activity"] = now - 1801

    SessionTimeoutMiddleware(lambda r: HttpResponse("ok"))(request)

    assert request.user.is_authenticated is False
    entry = AuditLog.objects.get(event_type=EVENT_TYPE_SESSION_EXPIRED)
    assert entry.user == user
    assert entry.metadata["reason"] == "idle_timeout"


@pytest.mark.django_db
def test_logs_out_on_max_lifetime_exceeded(user, settings):
    settings.DEBUG = False
    settings.SESSION_IDLE_TIMEOUT = 1800
    settings.SESSION_COOKIE_AGE = 28800
    request = _request_with_session()
    request.user = user
    now = timezone.now().timestamp()
    request.session["_mires_session_created_at"] = now - 28801
    request.session["_mires_session_last_activity"] = now

    SessionTimeoutMiddleware(lambda r: HttpResponse("ok"))(request)

    entry = AuditLog.objects.get(event_type=EVENT_TYPE_SESSION_EXPIRED)
    assert entry.metadata["reason"] == "max_lifetime"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "created_ago, idle_for",
    [pytest.param(28801, 0, id="max_lifetime"), pytest.param(0, 1801, id="idle_timeout")],
)
def test_response_after_expiry_clears_the_browser_cache(user, settings, created_ago, idle_for):
    """Cached WADO frames/metadata must not outlive the session (#276)."""
    settings.DEBUG = False
    settings.SESSION_IDLE_TIMEOUT = 1800
    settings.SESSION_COOKIE_AGE = 28800
    request = _request_with_session()
    request.user = user
    now = timezone.now().timestamp()
    request.session["_mires_session_created_at"] = now - created_ago
    request.session["_mires_session_last_activity"] = now - idle_for

    response = SessionTimeoutMiddleware(lambda r: HttpResponse("ok"))(request)

    assert response["Clear-Site-Data"] == '"cache"'


@pytest.mark.django_db
def test_response_within_limits_keeps_the_browser_cache(user, settings):
    settings.DEBUG = False
    request = _request_with_session()
    request.user = user
    now = timezone.now().timestamp()
    request.session["_mires_session_created_at"] = now
    request.session["_mires_session_last_activity"] = now

    response = SessionTimeoutMiddleware(lambda r: HttpResponse("ok"))(request)

    assert "Clear-Site-Data" not in response
