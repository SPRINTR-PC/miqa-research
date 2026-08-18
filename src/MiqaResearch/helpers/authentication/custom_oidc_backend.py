import json
import os

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import Group


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            self.update_user_roles(sociallogin.user, self._pick_claims(sociallogin))

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        self.update_user_roles(user, self._pick_claims(sociallogin))
        return user

    @staticmethod
    def _pick_claims(sociallogin):
        extra_data = sociallogin.account.extra_data
        return extra_data.get("userinfo") or extra_data.get("id_token") or extra_data

    def update_user_roles(self, user, claims):
        oidc_roles = claims.get(settings.OIDC_ROLES_CLAIM, [])

        if isinstance(oidc_roles, str):
            oidc_roles = [oidc_roles]

        role_mapping = json.loads(os.getenv("MIRES_OIDC_ROLE_MAPPING", "{}"))

        target_group_names = [role_mapping.get(role) for role in oidc_roles]
        target_groups = Group.objects.filter(name__in=target_group_names)
        user.groups.set(target_groups)
