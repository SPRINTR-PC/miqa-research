# SSO Auto-Provisioning

## Destination

The SSO (OIDC/ADFS) sign-in flow becomes fully frictionless and fully automatic end-to-end:

1. **One click, no intermediate pages.** `SOCIALACCOUNT_LOGIN_ON_GET = True` removes allauth's "Continue to `<provider>`?" confirmation screen. When SSO is the *only* configured auth mode (`MIRES_AUTHENTICATION_FRAMEWORK`), clicking nav "Sign In" skips the method-chooser page entirely and redirects straight to the IdP.
2. **Auto-signup, passwordless.** A first-time SSO login creates the `User` automatically with no signup form — no password fields, no confirmation screen. Email comes from the merged claims: try `OIDC_EMAIL_CLAIM` (new setting, default `"email"`), fall back to `upn` (ADFS-friendly), and only if neither claim is present does the user land on the existing manual signup form to supply one.
3. **Auto-link existing accounts.** If a `User` already exists with a matching, verified email, the SSO login links to and authenticates as that account automatically — no password-confirmation step. Consciously trades away the email-collision guard for convenience, accepted since the IdP is already the trust anchor here. (Mechanism and a password-wiping side effect it may trigger are this map's open research question — see ticket.)
4. **Role mapping keeps working, unchanged.** `CustomSocialAccountAdapter` already re-syncs `user.groups` from `OIDC_ROLES_CLAIM` on every login and on signup — preserved as-is through the above changes. Roles present in claims but unmapped to any `Group` get logged instead of silently dropped.
5. **Dev-mode claims logging.** New setting `MIRES_OIDC_LOG_CLAIMS` (bool, default = `MIRES_DEBUG`'s value, independent of it) gates logging the full merged claims dict (userinfo + decoded id_token) at Python `DEBUG` log level. No hard production gate — the setting is trusted at face value; `DEBUG`-level logging means a typical prod logging config filters it out unless someone deliberately raises verbosity.
6. Passkey/WebAuthn signup stays disabled — already allauth's default (`MFA_PASSKEY_SIGNUP_ENABLED` defaults `False`, never overridden here). No work needed, just don't regress it.

## Notes

- Project: Django 6 + django-allauth 65.19 (`socialaccount` extra now installed for `pyjwt[crypto]`), generic `openid_connect` provider used for both plain OIDC and ADFS.
- Key files: `helpers/authentication/custom_oidc_backend.py` (`CustomSocialAccountAdapter`), `MiqaResearch/interfaces/http/views/accounts/login.py` (custom `LoginView`, HTMX-aware), `templates/account/login.partial.html`, `MiqaResearch/context_processors.py` (`auth_framework`), `MiqaResearch/settings.py` (`MIRES_OIDC_*` / `OIDC_*` settings, `MIRES_AUTHENTICATION_FRAMEWORK`).
- Builds on top of the prior, already-resolved [wayfinder-htmx-login-map](wayfinder-htmx-login-map.md) (HTMX login template split, conditional method display) — don't re-litigate that map's decisions.
- allauth already ships likely primitives for auto-linking by verified email: `SOCIALACCOUNT_EMAIL_AUTHENTICATION` (+ `EMAIL_AUTHENTICATION_AUTO_CONNECT`), wired in `allauth/socialaccount/adapter.py:383-416` / `allauth/socialaccount/models.py:388`, and `is_email_verified`/`VERIFIED_EMAIL` per-provider setting to decide whether an IdP-supplied email counts as verified. **Caution**: `models.py:399` calls `wipe_password()` on the matched local user when this path fires — auto-linking via email match may silently remove a user's existing local password. This needs to be confirmed/resolved by its ticket, not assumed acceptable.
- Consciously accepted security tradeoffs (already grilled with the user, not open for re-litigation): auto-linking by verified email skips allauth's password-confirmation connect step; `SOCIALACCOUNT_LOGIN_ON_GET=True` accepts the well-known login-CSRF surface that setting normally guards against, since this app fully trusts the IdP for authentication.
- Naming convention for new settings: `MIRES_OIDC_*` env var → bare `OIDC_*` Django setting, matching existing pattern (e.g. `MIRES_OIDC_ROLES_CLAIM` → `OIDC_ROLES_CLAIM`).
- Tracker: local markdown under `.agents/trackers/` (gh CLI unavailable; this repo's documented GitHub tracker can't be used). Same layout as the prior htmx-login effort. **`.agents/` is gitignored at the repo root** — these files are intentionally local-only, never committed. This means a fresh `git worktree` can never see them regardless of which commit it checks out; don't use `isolation: "worktree"` for research subagents against this tracker — run them in the main working directory instead (safe here since each writes to a distinct new ticket file).
- Corrected setting name (found during research): it's `SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT`, not the unprefixed guess used while drafting the auto-link ticket.

## Decisions so far

- [Bypass password requirement for automatic passwordless SSO signup](tickets/passwordless-sso-signup.md) — Override `is_auto_signup_allowed()` on `CustomSocialAccountAdapter` to force auto-signup once an email is resolvable; no other adapter/settings changes needed, manual signup form is provably unaffected.
- [Auto-link existing local account to SSO login by verified email](tickets/auto-link-existing-account-by-email.md) — Config-only: `SOCIALACCOUNT_EMAIL_AUTHENTICATION` + `SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT` + per-app `verified_email`/`email_authentication`; keep allauth's `wipe_password()` side effect as-is — it's the real defense against email-collision account takeover, not a bug to route around.
- [Redirect nav Sign-In straight to the IdP when SSO is the sole configured auth mode](tickets/skip-chooser-single-method.md) — New `SSO_ONLY_LOGIN_ENABLED` settings flag; `LoginView.get()` override returns `HttpResponseRedirect` (plain) or `django_htmx`'s `HttpResponseClientRedirect` (HTMX, via `HX-Redirect` header) straight to the IdP, forwarding `next=`/`process=` query params.
- [Hook point and format for dev-mode OIDC claims logging](tickets/oidc-claims-logging-hook.md) — Log inside `update_user_roles()` (not `_pick_claims()`) via `logger = logging.getLogger(__name__)`; new `MIRES_OIDC_LOG_CLAIMS` env var defaulting to `MIRES_DEBUG`'s value via `env(..., default=DEBUG)`; unmatched incoming roles logged unconditionally at `warning` level (not gated by the dev flag).

## Not yet specified

*(none — all four fog items identified during destination-grilling are now resolved tickets; the map is walked)*

## Out of scope

- SITHS/BankID (EID) auth flows — separate, non-OIDC auth mode, untouched by this effort.
- Re-opening the HTMX login-template split — already resolved in [wayfinder-htmx-login-map](wayfinder-htmx-login-map.md).
- Changing how `MIRES_AUTHENTICATION_FRAMEWORK` itself is configured or parsed.
