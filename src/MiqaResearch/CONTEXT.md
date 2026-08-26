# Domain Model — MiqaResearch

## Glossary

### Authentication Framework
The configurable system that determines how users authenticate to the MiqaResearch
application. Controlled at runtime by the `MIRES_AUTHENTICATION_FRAMEWORK` environment
variable, which accepts a comma-separated list of modes: `local` (email/password),
`oidc` (generic OIDC via allauth), `adfs` (Microsoft ADFS via allauth), and `yubikey`
(WebAuthn/passkey MFA via allauth). Modes can be combined (e.g., `"oidc,yubikey"` for
two-factor authentication). In development (`DEBUG=True`), local email/password login
is always available in addition to any configured OIDC provider. In production, only
the configured modes are active.

### OIDC (OpenID Connect)
An identity layer on top of the OAuth 2.0 protocol. Used for federated
login where an external Identity Provider (IdP) authenticates the user and
returns claims (e.g., email, name, roles) to the application. In MiqaResearch,
OIDC is integrated via **django-allauth**'s `SocialAccount` framework with the
`openid-connect` provider, which supports both generic OIDC servers and
Microsoft ADFS.

### ADFS (Active Directory Federation Services)
Microsoft's OIDC-compliant identity provider. From the application's perspective,
ADFS is treated as a standard OIDC provider — its discovery and token endpoints
are configured via standard OIDC URLs. No special library or code path is needed
beyond generic OIDC configuration.

### EID (E-identitet / Svensk E-identitet)
A separate, custom authentication flow that connects to the "Svensk E-identitet"
OIDC/SAML broker to provide SITHS and BankID login. This is **distinct** from the
OIDC/ADFS authentication framework and is currently out of scope for the
authentication redesign. Preserved as-is for now.

### MFA (Multi-Factor Authentication)
Secondary authentication layered on top of primary login. MiqaResearch uses
django-allauth's MFA module with WebAuthn (passkey/hardware security key) as the
supported method. Configurable via `MFA_SUPPORTED_TYPES` and
`MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN`.

### Session
A user's authenticated period, managed by Django's session framework. Sessions
are stored server-side and identified by a session key in a cookie. In production,
sessions are subject to two expiration policies:
- **Maximum absolute lifetime**: the session expires after N hours regardless of
  activity (configurable via `MIRES_SESSION_COOKIE_AGE`).
- **Sliding inactivity timeout**: the session expires after N minutes of
  inactivity (configurable via `MIRES_SESSION_IDLE_TIMEOUT`).
In development (`DEBUG=True`), neither timeout is enforced to reduce friction.

### Audit Log
A record of authentication-related events written to the `mires_audit_log`
table (the `AuditLog` model). Each entry captures: event type (login, logout,
session expired, login failed), the authenticated user, IP address, session key,
authentication method (oidc, local, mfa), timestamp, and optional metadata.
Events are emitted via Django's built-in `user_logged_in`, `user_logged_out`,
and `user_login_failed` signals, plus the inactivity-timeout middleware.

### Bearer Token
A long-lived API credential (distinct from OAuth2 access tokens) stored as a
hashed value in the `mires_bearer_token` table. Generated via
`BearerToken.generate_token()`. The custom `BearerToken` model coexists with
django-oauth-toolkit's `AccessToken` model but serves a different purpose.

### JWT (JSON Web Token)
A compact, self-contained token format used for API authentication. In
MiqaResearch, JWT support is provided by **django-oauth-toolkit**'s native JWT
token encoding (configured via `OAUTH2_PROVIDER` settings), not a separate
JWT library. API requests are authenticated via the `ClientCredentialsAuth`
class, which validates JWT-encoded access tokens against scope requirements.

### Social Account
A user account linked to an external identity provider (e.g., an OIDC IdP)
via django-allauth's `SocialAccount` framework. When an OIDC user authenticates
for the first time, a Django user is auto-provisioned from the IdP's claims
(email, first name, last name). Role-to-group mapping is applied from
database-stored `OIDCRoleMapping` records (seeded from the `MIRES_OIDC_ROLE_MAPPING`
environment variable if no database records exist yet).

### Role Mapping
The process of translating OIDC role claims (e.g., a `role` claim in the ID
token) to Django group assignments. Stored in the `OIDCRoleMapping` database
model (mapping IdP role strings to Django `Group` instances). Initial values
can be seeded from the `MIRES_OIDC_ROLE_MAPPING` JSON environment variable on
first run. Applied during OIDC user provisioning.

### OIDC Provider Configuration
A single OIDC provider per deployment, configured via environment variables:
`MIRES_OIDC_DISCOVERY_URL` (the provider's OIDC discovery document URL),
`MIRES_OIDC_CLIENT_ID`, and `MIRES_OIDC_CLIENT_SECRET`. For Microsoft ADFS,
the discovery URL is at `https://adfs.example.com/adfs/.well-known/openid-configuration`.
Secrets are fetched from Vault in production, environment variables in development.

### OIDC Authentication Framework
The `MIRES_AUTHENTICATION_FRAMEWORK` environment variable historically controlled
which OIDC library was used (`"adfs"` for `django_auth_adfs`, `"oidc"` for
`mozilla_django_oidc`). The old `"yubikey"` default did not activate either
branch, falling through to local-only auth. This is being replaced by a
mode-based system: `MIRES_AUTHENTICATION_FRAMEWORK` can be `"local"` (no OIDC),
`"oidc"` (generic OIDC via allauth), or `"adfs"` (OIDC with ADFS-specific
endpoint derivation). The `"oidc"` and `"adfs"` modes are now both handled by
allauth's SocialAccount with the same code path; the difference is only in how
the discovery URL is derived. A deprecation warning is emitted when the old
`"adfs"` or `"oidc"` values are used without `MIRES_OIDC_DISCOVERY_URL`.

### OIDC Authentication Modes
The complete set of authentication modes available per deployment, combinable
with MFA (see below):
- **local**: No OIDC. Username/password via django-allauth only. Used in
  development when no IdP is configured.
- **oidc**: Generic OIDC provider via allauth SocialAccount. Configured via
  `MIRES_OIDC_DISCOVERY_URL`. Available in both development and production.
- **adfs**: Microsoft ADFS as OIDC provider. Same allauth code path as `"oidc"`
  but derives discovery URL from `MIRES_ADFS_AUTHORITY` with ADFS-specific path
  (`/adfs/.well-known/openid-configuration`).
- **yubikey**: WebAuthn/passkey-based authentication via allauth MFA. Can be
  used as a standalone login method (if `MFA_PASSKEY_LOGIN_ENABLED = True`) or
  as a second factor after OIDC or local login. This mode can be combined with
  `"oidc"` or `"adfs"` modes to provide two-factor authentication in production
  installations.

### MFA (WebAuthn / Passkey)
A cross-cutting authentication concern that provides an additional verification
step using hardware security keys or platform authenticators (e.g., Touch ID,
Windows Hello). Configurable via `MFA_SUPPORTED_TYPES = ["webauthn"]` and
`MFA_PASSKEY_LOGIN_ENABLED = True`. MFA can be combined with any primary
authentication mode (`oidc`, `adfs`, `local`) to provide two-factor
authentication. In production, operators can require MFA after OIDC login by
setting `ACCOUNT_MFA_REQUIRED = True` (via django-allauth). The `yubikey`
authentication framework mode enables MFA as a standalone login option on the
login page — useful when OIDC is not available but hardware-key authentication
is desired.

### Login Page Rendering
The login page (`templates/account/login.partial.html`) conditionally renders
sections based on configuration:
- **OIDC section**: Shown when `MIRES_OIDC_DISCOVERY_URL` is configured or
  `MIRES_AUTHENTICATION_FRAMEWORK` is `"oidc"` or `"adfs"`. Displays a single
  "Sign in with SSO" button (or `MIRES_OIDC_PROVIDER_DISPLAY_NAME` if set).
  Rendered server-side via template conditionals — not hidden via CSS.
- **YubiKey/Passkey section**: Shown when `MIRES_AUTHENTICATION_FRAMEWORK`
  includes `"yubikey"` or when MFA is available. Provides a "Sign in with Passkey"
  link to allauth's `mfa_reauthenticate` flow for users who have previously
  registered a WebAuthn credential. This section can appear alongside the OIDC
  section, enabling MFA as an additional option.
- **SITHS/BankID section**: Always shown (existing EID flow, deferred for redesign).
- **Local email/password section**: Always shown when `DEBUG=True` or when
  `MIRES_AUTHENTICATION_FRAMEWORK=local`. Hidden in production otherwise.

## Decisions (ADRs)

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | Use django-allauth SocialAccount for OIDC integration | Accepted |
| 0002 | Enable local email/password login in development | Accepted |
| 0003 | Use django-oauth-toolkit JWT support for API tokens | Accepted |
| 0004 | Implement sliding inactivity timeout for sessions | Accepted |
| 0005 | Extend AuditLog model for session audit logging | Accepted |
| 0006 | Single OIDC provider via environment variables | Accepted |
| 0007 | Discovery URL for OIDC provider endpoint configuration | Accepted |
| 0008 | Just-in-time provisioning with group-based access control | Accepted |
| 0009 | Database-stored role mapping with env-var seeding | Accepted |
| 0010 | 8h max session / 30min idle timeout; 90-day audit log retention | Accepted |
| 0011 | Env-var superuser creation + OIDC role-based superuser | Accepted |
| 0012 | Remove django_auth_adfs from dependencies | Accepted |
| 0013 | App-startup seeding + management command for role mappings | Accepted |
| 0014 | Generic SSO button with configurable display name | Accepted |
| 0015 | Unit tests for adapter/model + responses-mocked integration tests | Accepted |
| 0016 | MIRES_AUTHENTICATION_FRAMEWORK retains mode selector (local/oidc/adfs/yubikey) | Accepted |
| 0017 | YubiKey/WebAuthn MFA as combinable second factor with OIDC | Accepted |

### ADR 0017 — YubiKey/WebAuthn MFA as combinable second factor with OIDC

**Context**: The original `MIRES_AUTHENTICATION_FRAMEWORK` defaulted to `"yubikey"`,
which did not match any code branch in `settings.py` and was effectively a no-op.
The login page template (`login.partial.html`) already has a YubiKey/Passkey
section linking to allauth's `mfa_reauthenticate` URL.

**Decision**: The `"yubikey"` mode is retained as a valid authentication framework
mode alongside `"local"`, `"oidc"`, and `"adfs"`. It enables WebAuthn/passkey
authentication via django-allauth's MFA module. Unlike the other modes,
`"yubikey"` can be **combined** with `"oidc"` or `"adfs"` to provide two-factor
authentication (OIDC as first factor, WebAuthn as second). The mode is selected
via the `MIRES_AUTHENTICATION_FRAMEWORK` env var, which can accept a
comma-separated list (e.g., `"oidc,yubikey"`) to enable multiple modes
simultaneously.

**Consequences**:
- The login page dynamically shows the YubiKey/Passkey section when `"yubikey"`
  is among the active modes.
- In production, operators can set `MIRES_AUTHENTICATION_FRAMEWORK=oidc,yubikey`
  to require both OIDC login and WebAuthn verification.
- The `MFA_PASSKEY_LOGIN_ENABLED` setting controls whether passkeys can be used
  as a standalone login method (not just as a second factor after password).
- This preserves the existing login page template structure while adding
  conditional rendering based on the active authentication modes.