import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from contract.constants.audit_log import AUTH_METHOD_LOCAL, EVENT_TYPE_LOGIN
from MiqaResearch.data.models import AuditLog

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="audituser", email="audit@example.com")


@pytest.mark.django_db
def test_record_extracts_ip_and_session_key_from_request(user):
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.5")
    request.session = type("FakeSession", (), {"session_key": "abc123"})()

    entry = AuditLog.objects.record(
        EVENT_TYPE_LOGIN, user=user, request=request, auth_method=AUTH_METHOD_LOCAL
    )

    assert entry.ip_address == "10.0.0.5"
    assert entry.session_key == "abc123"
    assert entry.auth_method == AUTH_METHOD_LOCAL
    assert entry.user == user


@pytest.mark.django_db
def test_record_allows_explicit_overrides_without_request():
    entry = AuditLog.objects.record(
        EVENT_TYPE_LOGIN, ip_address="1.2.3.4", session_key="xyz", metadata={"reason": "test"}
    )

    assert entry.ip_address == "1.2.3.4"
    assert entry.session_key == "xyz"
    assert entry.metadata == {"reason": "test"}
    assert entry.user is None


@pytest.mark.django_db
def test_record_defaults_metadata_to_empty_dict():
    entry = AuditLog.objects.record(EVENT_TYPE_LOGIN)

    assert entry.metadata == {}
