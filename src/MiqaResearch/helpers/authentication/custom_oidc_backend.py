import json
import os

from django.conf import settings
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class CustomOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def update_user_roles(self, user, claims):
        oidc_roles = claims.get(settings.OIDC_ROLES_CLAIM, [])

        if isinstance(oidc_roles, str):
            oidc_roles = [oidc_roles]

        role_mapping = json.loads(os.getenv("MIRES_OIDC_ROLE_MAPPING", "{}"))

        target_group_names = [role_mapping.get(role) for role in oidc_roles]
        target_groups = Group.objects.filter(name__in=target_group_names)
        user.groups.set(target_groups)
