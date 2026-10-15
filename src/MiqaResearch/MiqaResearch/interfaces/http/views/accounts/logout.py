from allauth.account.views import LogoutView as AllauthLogoutView

from helpers.http import CLEAR_SITE_DATA_CACHE


class LogoutView(AllauthLogoutView):
    """
    Custom LogoutView that extends allauth's LogoutView to support HTMX requests.

    For HTMX requests, renders the logout confirmation partial template
    (account/logout.partial.html), a fragment suitable for swapping into the
    app's modal via HTMX.

    For regular requests, falls back to the default allauth behavior, rendering
    the full page template (account/logout.html).

    The logout response carries `Clear-Site-Data: "cache"` so cached WADO
    frames/metadata don't outlive the session (#276).
    """

    def post(self, *args, **kwargs):
        response = super().post(*args, **kwargs)
        response["Clear-Site-Data"] = CLEAR_SITE_DATA_CACHE
        return response

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["account/logout.partial.html"]
        return super().get_template_names()
