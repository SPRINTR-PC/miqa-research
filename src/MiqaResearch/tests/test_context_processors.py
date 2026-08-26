import pytest
from django.test import RequestFactory

from MiqaResearch.context_processors import auth_framework


@pytest.fixture
def request_(rf=RequestFactory()):
    return rf.get("/accounts/login/")


def test_auth_framework_disabled_by_default(request_, settings):
    settings.OIDC_LOGIN_ENABLED = False

    context = auth_framework(request_)

    assert context["oidc_login_enabled"] is False
    assert "oidc_login_url" not in context


def test_auth_framework_enabled_exposes_login_url(request_, settings):
    settings.OIDC_LOGIN_ENABLED = True
    settings.OIDC_PROVIDER_DISPLAY_NAME = "Acme SSO"
    settings.OIDC_PROVIDER_ID = "mires-oidc"

    context = auth_framework(request_)

    assert context["oidc_login_enabled"] is True
    assert context["oidc_provider_display_name"] == "Acme SSO"
    assert context["oidc_login_url"] == "/accounts/oidc/mires-oidc/login/"


def test_auth_framework_exposes_passkey_flag_when_yubikey_configured(request_, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"

    context = auth_framework(request_)

    assert context["passkey_login_enabled"] is True
    assert context["eid_login_enabled"] is False
    assert context["bankid_login_enabled"] is False


def test_auth_framework_exposes_eid_flag_when_bankid_configured(request_, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "bankid"

    context = auth_framework(request_)

    assert context["passkey_login_enabled"] is False
    assert context["eid_login_enabled"] is True
    assert context["bankid_login_enabled"] is True
