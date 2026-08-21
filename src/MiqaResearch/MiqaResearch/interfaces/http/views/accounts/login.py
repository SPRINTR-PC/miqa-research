from allauth.account.views import LoginView as AllauthLoginView
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django_htmx.http import HttpResponseClientRedirect


class LoginView(AllauthLoginView):
    """
    Custom LoginView that extends allauth's LoginView to support HTMX requests.

    For HTMX requests, renders the login partial template (account/login.partial.html)
    which is a fragment suitable for swapping into the page via HTMX.

    For regular requests, falls back to the default allauth behavior, rendering
    the full page template (account/login.html).

    When SSO is the only configured auth method, skips the chooser entirely
    and redirects straight to the IdP.
    """

    def get(self, request, *args, **kwargs):
        if settings.SSO_ONLY_LOGIN_ENABLED:
            return self._redirect_to_sso(request)
        return super().get(request, *args, **kwargs)

    def _redirect_to_sso(self, request):
        target = reverse("openid_connect_login", kwargs={"provider_id": settings.OIDC_PROVIDER_ID})
        query = request.GET.urlencode()
        if query:
            target = f"{target}?{query}"

        if request.htmx:
            return HttpResponseClientRedirect(target)
        return HttpResponseRedirect(target)

    def get_template_names(self):
        """
        Return different templates based on whether the request is an HTMX request.

        HTMX requests get the partial template (fragment), regular requests
        get the full page template.
        """
        if self.request.headers.get("HX-Request") == "true":
            return ["account/login.partial.html"]
        return super().get_template_names()
