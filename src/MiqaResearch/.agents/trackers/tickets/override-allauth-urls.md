# Override Allauth URLs

Part of: wayfinder-htmx-login-map

## Question

How should we wire our custom login view into the URL configuration, replacing allauth's default `account_login` URL?

Currently, the project includes allauth URLs via:
```python
path('accounts/', include('allauth.urls')),
```

This means `account_login` maps to allauth's default LoginView. To use our custom view, we need to either:

1. Define a custom `account_login` path before the allauth include
2. Use `ACCOUNT_FORMS` setting if applicable
3. Use `ACCOUNT_LOGIN_URL` setting

What's the cleanest way to override just the login view while keeping all other allauth functionality intact?

## Type
research

## Status
open