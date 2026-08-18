from types import SimpleNamespace

import pytest
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from helpers.authentication.custom_oidc_backend import CustomSocialAccountAdapter

User = get_user_model()


def _request_with_session():
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


@pytest.fixture
def user(db):
    return User.objects.create_user(username="oidcuser", email="oidc@example.com")


@pytest.fixture
def adapter():
    return CustomSocialAccountAdapter()


@pytest.mark.django_db
def test_update_user_roles_maps_single_role_string_to_group(adapter, user, settings, monkeypatch):
    settings.OIDC_ROLES_CLAIM = "role"
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')
    Group.objects.create(name="Administrators")

    adapter.update_user_roles(user, {"role": "admin"})

    assert list(user.groups.values_list("name", flat=True)) == ["Administrators"]


@pytest.mark.django_db
def test_update_user_roles_maps_multiple_roles(adapter, user, settings, monkeypatch):
    settings.OIDC_ROLES_CLAIM = "role"
    monkeypatch.setenv(
        "MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators", "viewer": "Viewers"}'
    )
    Group.objects.create(name="Administrators")
    Group.objects.create(name="Viewers")

    adapter.update_user_roles(user, {"role": ["admin", "viewer"]})

    assert set(user.groups.values_list("name", flat=True)) == {"Administrators", "Viewers"}


@pytest.mark.django_db
def test_update_user_roles_clears_groups_when_no_roles_claim(adapter, user, settings, monkeypatch):
    settings.OIDC_ROLES_CLAIM = "role"
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", "{}")
    existing_group = Group.objects.create(name="Stale")
    user.groups.add(existing_group)

    adapter.update_user_roles(user, {})

    assert list(user.groups.all()) == []


@pytest.mark.django_db
def test_pre_social_login_updates_roles_for_existing_user(adapter, user, settings, monkeypatch):
    settings.OIDC_ROLES_CLAIM = "role"
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')
    Group.objects.create(name="Administrators")
    sociallogin = SimpleNamespace(
        is_existing=True,
        user=user,
        account=SimpleNamespace(extra_data={"userinfo": {"role": "admin"}}),
    )

    adapter.pre_social_login(request=None, sociallogin=sociallogin)

    assert list(user.groups.values_list("name", flat=True)) == ["Administrators"]


@pytest.mark.django_db
def test_pre_social_login_does_nothing_for_new_user(adapter, settings):
    settings.OIDC_ROLES_CLAIM = "role"
    sociallogin = SimpleNamespace(is_existing=False, user=None, account=None)

    adapter.pre_social_login(request=None, sociallogin=sociallogin)  # must not raise


@pytest.mark.django_db
def test_save_user_updates_roles_on_first_signup(adapter, settings, monkeypatch):
    settings.OIDC_ROLES_CLAIM = "role"
    monkeypatch.setenv("MIRES_OIDC_ROLE_MAPPING", '{"admin": "Administrators"}')
    Group.objects.create(name="Administrators")

    new_user = User(username="new-oidc-user", email="new@example.com")
    account = SocialAccount(
        provider="mires-oidc",
        uid="external-123",
        extra_data={"userinfo": {"role": "admin", "email": "new@example.com"}},
    )
    sociallogin = SocialLogin(user=new_user, account=account)
    request = _request_with_session()

    saved_user = adapter.save_user(request, sociallogin)

    assert saved_user.pk is not None
    assert list(saved_user.groups.values_list("name", flat=True)) == ["Administrators"]
