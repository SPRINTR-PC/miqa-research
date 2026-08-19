from allauth.account.views import LoginView as AllauthLoginView


class LoginView(AllauthLoginView):
    """
    Custom LoginView that extends allauth's LoginView to support HTMX requests.
    
    For HTMX requests, renders the login partial template (account/login.partial.html)
    which is a fragment suitable for swapping into the page via HTMX.
    
    For regular requests, falls back to the default allauth behavior, rendering
    the full page template (account/login.html).
    """

    def get_template_names(self):
        """
        Return different templates based on whether the request is an HTMX request.
        
        HTMX requests get the partial template (fragment), regular requests
        get the full page template.
        """
        if self.request.headers.get("HX-Request") == "true":
            return ["account/login.partial.html"]
        return super().get_template_names()