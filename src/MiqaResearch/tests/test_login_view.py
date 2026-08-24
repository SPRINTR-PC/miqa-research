from unittest.mock import PropertyMock, patch

import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


FAKE_OIDC_SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "mires-oidc",
                "name": "Mires OIDC",
                "client_id": "test-client-id",
                "secret": "test-secret",
                "settings": {"server_url": "https://idp.example.com/.well-known/openid-configuration"},
            }
        ]
    }
}

FAKE_OPENID_CONFIG = {
    "authorization_endpoint": "https://idp.example.com/authorize",
    "token_endpoint": "https://idp.example.com/token",
    "userinfo_endpoint": "https://idp.example.com/userinfo",
    "jwks_uri": "https://idp.example.com/jwks",
    "issuer": "https://idp.example.com",
}


def _sso_only_settings(settings):
    settings.SSO_ONLY_LOGIN_ENABLED = True
    settings.OIDC_PROVIDER_ID = "mires-oidc"
    settings.SOCIALACCOUNT_PROVIDERS = FAKE_OIDC_SOCIALACCOUNT_PROVIDERS


def _mock_openid_config():
    return patch(
        "allauth.socialaccount.providers.openid_connect.views.OpenIDConnectOAuth2Adapter.openid_config",
        new_callable=PropertyMock,
        return_value=FAKE_OPENID_CONFIG,
    )


@pytest.mark.django_db
def test_regular_request_renders_full_login_page(client, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"

    response = client.get("/accounts/login/")

    assert response.status_code == 200
    assert [t.name for t in response.templates][0] == "account/login.html"


@pytest.mark.django_db
def test_htmx_request_renders_login_partial(client, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"

    response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert [t.name for t in response.templates][0] == "account/login.partial.html"


@pytest.mark.django_db
def test_only_configured_auth_methods_are_rendered(client, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"

    response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")
    content = response.content.decode()

    assert "YubiKey / Passkey" in content
    assert "SITHS / BankID" not in content


@pytest.mark.django_db
def test_eid_methods_rendered_when_configured(client, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "siths,bankid"

    response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")
    content = response.content.decode()

    assert "YubiKey / Passkey" not in content
    assert "SITHS / BankID" in content
    assert 'href="/accounts/siths/login/"' in content
    assert 'href="/accounts/bankid/login/"' in content


@pytest.mark.django_db
def test_only_configured_eid_method_is_rendered(client, settings):
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "siths"

    response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")
    content = response.content.decode()

    assert 'href="/accounts/siths/login/"' in content
    assert 'href="/accounts/bankid/login/"' not in content


@pytest.mark.django_db
def test_sso_only_plain_get_redirects_to_idp(client, settings):
    _sso_only_settings(settings)

    with _mock_openid_config():
        response = client.get("/accounts/login/")

    assert response.status_code == 302
    assert response["Location"].startswith("https://idp.example.com/authorize?")
    assert "client_id=test-client-id" in response["Location"]


@pytest.mark.django_db
def test_sso_only_htmx_get_returns_hx_redirect_header(client, settings):
    _sso_only_settings(settings)

    with _mock_openid_config():
        response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert response["HX-Redirect"].startswith("https://idp.example.com/authorize?")


@pytest.mark.django_db
def test_sso_only_get_forwards_query_params(client, settings):
    _sso_only_settings(settings)

    with _mock_openid_config():
        response = client.get("/accounts/login/?next=/foo")

    assert response.status_code == 302
    ((state, _timestamp),) = client.session["socialaccount_states"].values()
    assert state["next"] == "/foo"


@pytest.mark.django_db
def test_chooser_still_renders_when_sso_is_not_the_only_method(client, settings):
    settings.SSO_ONLY_LOGIN_ENABLED = False
    settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"

    response = client.get("/accounts/login/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert [t.name for t in response.templates][0] == "account/login.partial.html"
