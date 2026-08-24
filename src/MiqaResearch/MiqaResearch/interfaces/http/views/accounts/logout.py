from allauth.account.views import LogoutView as AllauthLogoutView


class LogoutView(AllauthLogoutView):
    """
    Custom LogoutView that extends allauth's LogoutView to support HTMX requests.

    For HTMX requests, renders the logout confirmation partial template
    (account/logout.partial.html), a fragment suitable for swapping into the
    app's modal via HTMX.

    For regular requests, falls back to the default allauth behavior, rendering
    the full page template (account/logout.html).
    """

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["account/logout.partial.html"]
        return super().get_template_names()
