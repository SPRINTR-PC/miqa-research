from django.conf import settings
from django.urls import reverse


def auth_framework(request):
    context = {
        "oidc_login_enabled": settings.OIDC_LOGIN_ENABLED,
        "oidc_provider_display_name": settings.OIDC_PROVIDER_DISPLAY_NAME,
    }
    if settings.OIDC_LOGIN_ENABLED:
        context["oidc_login_url"] = reverse(
            "openid_connect_login", kwargs={"provider_id": settings.OIDC_PROVIDER_ID}
        )
    return context
