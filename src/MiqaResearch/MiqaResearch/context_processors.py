from django.conf import settings
from django.urls import reverse


def auth_framework(request):
    auth_modes = set(settings.MIRES_AUTHENTICATION_FRAMEWORK.split(","))
    context = {
        "oidc_login_enabled": settings.OIDC_LOGIN_ENABLED,
        "oidc_provider_display_name": settings.OIDC_PROVIDER_DISPLAY_NAME,
        "passkey_login_enabled": "yubikey" in auth_modes,
        "eid_login_enabled": bool({"siths", "bankid"} & auth_modes),
        "siths_login_enabled": "siths" in auth_modes,
        "bankid_login_enabled": "bankid" in auth_modes,
    }
    if settings.OIDC_LOGIN_ENABLED:
        context["oidc_login_url"] = reverse(
            "openid_connect_login", kwargs={"provider_id": settings.OIDC_PROVIDER_ID}
        )
    return context
