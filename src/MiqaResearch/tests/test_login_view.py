import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


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
