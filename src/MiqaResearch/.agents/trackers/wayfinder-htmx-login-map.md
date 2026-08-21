## Destination

Custom LoginView that serves `account/login.partial.html` for HTMX requests and `account/login.html` for regular requests, with the login options dynamically displayed based on the configured authentication methods.

## Notes

- Project uses Django with django-allauth for authentication
- Authentication methods are configured via `MIRES_AUTHENTICATION_FRAMEWORK` environment variable
- The navigation.html login button already uses HTMX (`hx-get` attribute)
- Templates already exist: `account/login.html` and `account/login.partial.html`
- Allauth's LoginView uses template name pattern `account/login.{TEMPLATE_EXTENSION}`
- Project follows a clean architecture with views in `MiqaResearch.interfaces.http.views`
- The login view needs to detect HTMX requests and use different templates
- Login options should reflect configured authentication methods (OIDC, YubiKey/MFA, SITHS/BankID)

## Decisions so far

- [Override Allauth URLs](resolutions/override-allauth-urls.md) — Define custom `account_login` path before allauth include in URLconf to override allauth's default login view
- [Customize Allauth LoginView for HTMX Support](resolutions/customize-allauth-login-view.md) — Subclass allauth's LoginView and override `get_template_names()` to serve `account/login.partial.html` for HTMX requests and `account/login.html` for regular requests
- [Authentication Context in Login Template](resolutions/authentication-context-in-template.md) — Extend existing `auth_framework` context processor with granular boolean flags for each auth method to conditionally render login options in templates

## Not yet specified

- Whether the partial template should be updated to better support HTMX responses

## Out of scope

- Changing how authentication methods are configured
- Modifying the OIDC/SITHS/BankID authentication flows themselves