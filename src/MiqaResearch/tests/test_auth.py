from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone
from ninja.errors import HttpError
from oauth2_provider.models import AccessToken, Application

from MiqaResearch.interfaces.http.api.auth_types import ClientCredentialsAuth

User = get_user_model()

@pytest.fixture
def factory():
    return RequestFactory()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", email="test@example.com", password="password")


@pytest.fixture
def application(user):
    return Application.objects.create(
        name="test-app",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )


@pytest.fixture
def access_token(user, application):
    return AccessToken.objects.create(
        user=user,
        application=application,
        token="valid-token",
        scope="read",
        expires=timezone.now() + timedelta(hours=1),
    )


@pytest.fixture
def auth():
    return ClientCredentialsAuth(required_scopes=["read"])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_authenticate_success(factory, auth: ClientCredentialsAuth, application, access_token):
    request = factory.get("/")
    authenticated_application = await auth.authenticate(request, access_token.token)
    assert authenticated_application == application
    assert request.application == application
    assert request.access_token == access_token


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_authenticate_invalid_token(factory, auth: ClientCredentialsAuth):
    request = factory.get("/")
    authenticated_user = await auth.authenticate(request, "invalid-token")
    assert authenticated_user is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_authenticate_expired_token(factory, auth: ClientCredentialsAuth, access_token):
    access_token.expires = timezone.now() - timedelta(minutes=1)
    await access_token.asave(update_fields=["expires"])

    request = factory.get("/")
    authenticated_user = await auth.authenticate(request, access_token.token)
    assert authenticated_user is None


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_authenticate_insufficient_scope(factory, application, access_token):
    auth = ClientCredentialsAuth(required_scopes=["write"])
    request = factory.get("/")

    with pytest.raises(HttpError) as exc_info:
        await auth.authenticate(request, access_token.token)

    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Insufficient scope"


