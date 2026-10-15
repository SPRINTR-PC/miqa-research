import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", email="test@example.com", password="password")


@pytest.mark.django_db
def test_regular_get_renders_full_logout_page(client, user):
    client.force_login(user)

    response = client.get("/accounts/logout/")

    assert response.status_code == 200
    assert [t.name for t in response.templates][0] == "account/logout.html"


@pytest.mark.django_db
def test_htmx_get_renders_logout_partial(client, user):
    client.force_login(user)

    response = client.get("/accounts/logout/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert [t.name for t in response.templates][0] == "account/logout.partial.html"


@pytest.mark.django_db
def test_logout_partial_excludes_allauth_menu_and_messages(client, user):
    client.force_login(user)

    response = client.get("/accounts/logout/", HTTP_HX_REQUEST="true")
    content = response.content.decode()

    assert "Menu:" not in content
    assert "Messages:" not in content
    assert "Are you sure you want to sign out?" in content


@pytest.mark.django_db
def test_post_logs_the_user_out(client, user):
    client.force_login(user)

    response = client.post("/accounts/logout/")

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_logout_clears_the_browser_cache(client, user):
    """Cached WADO frames/metadata must not outlive the session (#276)."""
    client.force_login(user)

    response = client.post("/accounts/logout/")

    assert response["Clear-Site-Data"] == '"cache"'
