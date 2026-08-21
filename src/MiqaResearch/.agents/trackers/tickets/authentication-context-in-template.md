# Authentication Context in Login Template

Part of: wayfinder-htmx-login-map

## Question

How should we pass authentication framework configuration to the login template so it can conditionally display login options?

Currently, the context processor `auth_framework` provides `oidc_login_enabled` and `oidc_provider_display_name` to all templates. However, the login template needs more granular information about which specific authentication methods are enabled:

- OIDC login (already handled via context processor)
- YubiKey/Passkey (MFA - currently always shown)
- SITHS/BankID (E-ID login - currently always shown)

Should we:
1. Extend the existing context processor with more granular auth method flags?
2. Create a separate context processor specifically for login options?
3. Use template tags to check settings directly?

The goal is to make the login page visually reflect only the enabled authentication methods as configured by `MIRES_AUTHENTICATION_FRAMEWORK`.

## Type
grilling

## Status
resolved