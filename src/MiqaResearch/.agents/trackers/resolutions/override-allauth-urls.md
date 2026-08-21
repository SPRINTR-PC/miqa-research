## Resolution: Override Allauth URLs

**Decision**: Define a custom `account_login` path in the URL configuration before including allauth URLs.

### Approach

In `MiqaResearch/urls.py`, add the custom login view before the allauth include:

```python
from MiqaResearch.interfaces.http.views.accounts import LoginView

urlpatterns = [
    # ... other paths
    path('accounts/login/', LoginView.as_view(), name='account_login'),
    path('accounts/', include('allauth.urls')),
    # ... other paths
]
```

### Rationale

1. **URL precedence**: Django resolves URLs in order, so defining `accounts/login/` before the allauth include will take precedence
2. **Clean separation**: Keeps custom views in the project's URL conf while still leveraging allauth's other functionality
3. **Minimal disruption**: Doesn't require changes to allauth's configuration or settings
4. **Explicit**: Makes it clear in the URL conf which views are customized

### Implementation Details

- Import the custom LoginView from `MiqaResearch.interfaces.http.views.accounts`
- Place the custom path before `path('accounts/', include('allauth.urls'))` 
- Keep the same URL pattern and name (`account_login`) as allauth expects
- All other allauth URLs (logout, signup, password reset, etc.) will continue to work as before

### Related

- The navigation.html already references `{% url 'account_login' %}` for the login button
- The login form in `account/login.partial.html` submits to `{% url 'account_login' %}`
- This approach maintains backward compatibility with all allauth features except login view customization