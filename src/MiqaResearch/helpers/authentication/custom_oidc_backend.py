import logging

from allauth.account.utils import user_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import Group

from MiqaResearch.data.models import OIDCRoleMapping

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_auto_signup_allowed(self, request, sociallogin):
        # First-time SSO logins must auto-create the User with zero extra
        # screens whenever we already have a resolvable email, regardless of
        # the SOCIALACCOUNT_AUTO_SIGNUP default. ACCOUNT_SIGNUP_FIELDS / the
        # manual email+password signup form is a separate code path and is
        # unaffected by this.
        if sociallogin.email_addresses or user_email(sociallogin.user):
            return True
        return super().is_auto_signup_allowed(request, sociallogin)

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
        if settings.OIDC_LOG_CLAIMS:
            logger.debug("Merged OIDC claims for user %s: %s", user, claims)

        oidc_roles = claims.get(settings.OIDC_ROLES_CLAIM, [])

        if isinstance(oidc_roles, str):
            oidc_roles = [oidc_roles]

        matched_roles = set(
            OIDCRoleMapping.objects.filter(oidc_role__in=oidc_roles).values_list("oidc_role", flat=True)
        )
        unmatched_roles = set(oidc_roles) - matched_roles
        if unmatched_roles:
            logger.warning(
                "User %s presented OIDC role(s) %s with no configured OIDCRoleMapping; "
                "no group will be granted for these roles.",
                user, sorted(unmatched_roles),
            )

        target_groups = Group.objects.filter(oidc_role_mappings__oidc_role__in=oidc_roles)
        user.groups.set(target_groups)
