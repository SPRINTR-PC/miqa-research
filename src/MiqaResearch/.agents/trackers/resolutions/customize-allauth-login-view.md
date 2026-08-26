## Resolution: Customize Allauth LoginView for HTMX Support

**Decision**: Subclass allauth's LoginView and override `get_template_names()` to return different templates based on HTMX request detection.

### Approach

Create a custom LoginView that extends allauth's LoginView:

```python
from allauth.account.views import LoginView as AllauthLoginView

class LoginView(AllauthLoginView):
    def get_template_names(self):
        if self.request.headers.get('HX-Request') or self.request.htmx:
            return ["account/login.partial.html"]
        return super().get_template_names()
```

### Rationale

1. **Cleanest approach**: Subclassing with template name override is the recommended Django pattern for customizing allauth behavior
2. **Minimal code**: Only requires overriding one method
3. **Maintainable**: Leverages allauth's existing functionality while adding HTMX support
4. **Extensible**: Can easily add more customization (like context data) to the same view class

### Implementation Details

- Use `django_htmx`'s `request.htmx` property (already installed and configured in middleware)
- Or use header detection: `request.headers.get('HX-Request')`
- Override in a custom view in `MiqaResearch.interfaces.http.views.accounts`
- Wire it in URLs by defining `account_login` path before including allauth URLs

### Related

- `django_htmx` is already in INSTALLED_APPS and middleware
- The navigation.html already makes HTMX requests to `account_login`
- Templates `account/login.html` and `account/login.partial.html` already exist