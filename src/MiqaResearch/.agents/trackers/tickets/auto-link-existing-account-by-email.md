# Auto-link existing local account to SSO login by verified email

Part of: wayfinder-sso-auto-provisioning-map

## Question

Destination decision (already settled with the user, not open for re-litigation): if a Django `User` already exists with a matching, verified email, a first-time SSO login for that email should automatically link to and authenticate as that existing account, with no password-confirmation step — consciously trading away the email-collision guard for convenience, since this app already trusts the IdP.

What's open is the **mechanism**. django-allauth 65.19 (`.venv/lib/python3.14/site-packages/allauth/`) appears to already support most of this:

- `DefaultSocialAccountAdapter.authenticate_by_email()` / `can_authenticate_by_email()` (`allauth/socialaccount/adapter.py:383-416`), gated by `SOCIALACCOUNT_EMAIL_AUTHENTICATION` (global) or a provider's `email_authentication` app setting, and wired into the login flow at `allauth/socialaccount/models.py:388`.
- Whether the IdP-supplied email counts as "verified" at all is controlled separately by `DefaultSocialAccountAdapter.is_email_verified()` / the provider's `verified_email` app setting or global `SOCIALACCOUNT_PROVIDERS[...]["VERIFIED_EMAIL"]` (`allauth/socialaccount/adapter.py:356-379`) — confirm what this needs to be set to for the `openid_connect` provider app (`SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]`, `MiqaResearch/settings.py`) given ADFS/OIDC email claims aren't independently verified by allauth (no email-confirmation link is sent).
- `EMAIL_AUTHENTICATION_AUTO_CONNECT` (`allauth/socialaccount/app_settings.py:117`) controls whether the `SocialAccount` gets permanently connected to the matched user vs. only authenticating for that one login — decide which is wanted (permanent connect is almost certainly what "auto-link" means here).
- **Important side effect to resolve**: `allauth/socialaccount/models.py:399` calls `wipe_password(request, self.user, ...)` on the matched user when `authenticate_by_email` succeeds and auto-connect is on. This means a user's existing local password may be silently removed the first time they SSO in with a matching email. Determine whether this is acceptable here (likely fine if SSO becomes the sole credential going forward) or needs to be prevented/surfaced, and document the conclusion clearly since it's a real behavior change for any existing password-based user.

Record: the exact settings to add/change (`SOCIALACCOUNT_EMAIL_AUTHENTICATION`, `EMAIL_AUTHENTICATION_AUTO_CONNECT`, the `openid_connect` provider's `verified_email`/`email_authentication` app settings), whether any adapter override is still needed beyond configuration, and the resolution on the `wipe_password` side effect.

## Type
research

## Status
resolved

## Findings

**Source provenance.** All findings below are read directly from the actual installed `django-allauth` 65.19.1 source at `.venv/lib/python3.14/site-packages/allauth/` and verified independently against that source in this session (file+line confirmed). An earlier draft of this research flagged an apparent `uv.lock` (65.16.1) vs. installed-`.venv` (65.19.1) version mismatch — that's stale: `uv.lock` was already updated to `65.19.1` earlier in this session (adding the `socialaccount` extra to fix the original `ModuleNotFoundError: No module named 'jwt'` bug), the draft just read the pre-update committed history via `git show`. No real mismatch exists.

### (a) Exact settings to add

Global settings (`allauth/socialaccount/app_settings.py`, both default `False`):

```python
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
```

(Note the corrected name: `SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT`, not the unprefixed `EMAIL_AUTHENTICATION_AUTO_CONNECT` guessed in this ticket's original Question section.)

`EMAIL_AUTHENTICATION` gates whether a social login is allowed to authenticate into an existing local account purely by matching a verified email (no prior `SocialAccount` link). `EMAIL_AUTHENTICATION_AUTO_CONNECT` controls whether that match is *persisted* as a permanent `SocialAccount` link — without it, every future SSO login would re-run the email match instead of short-circuiting via the normal "existing SocialAccount" lookup, i.e. it would not be "permanently connected." Both are needed.

Per-app overrides on the `openid_connect` provider (inside the same `"settings"` sub-dict on `SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]` that already holds `server_url`, `fetch_userinfo`, etc.):

```python
SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["verified_email"] = True
SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["email_authentication"] = True
```

- `verified_email` (bool or list of trusted domains) force-overrides the IdP's own `email_verified` claim during email-address cleanup, before any login/lookup happens. Only set to `True` if the IdP is trusted to have verified the email out-of-band but doesn't reliably send an `email_verified` claim — if ADFS/OIDC's `email_verified` claim is trustworthy, prefer leaving this unset and relying on the claim itself (`openid_connect/provider.py: extract_email_addresses()`, `verified=data.get("email_verified", False)`).
- `email_authentication` is a per-app override; if explicitly set (even to `False`) it wins outright over the global `SOCIALACCOUNT_EMAIL_AUTHENTICATION` setting (`adapter.py: can_authenticate_by_email()`, `ret is None` guard).

Priority order confirmed from source: per-app `settings["email_authentication"]` > global `SOCIALACCOUNT_EMAIL_AUTHENTICATION` OR'd with a global per-provider `SOCIALACCOUNT_PROVIDERS["openid_connect"]["EMAIL_AUTHENTICATION"]` key (upper-case, directly under the provider dict, not inside `"settings"`). `EMAIL_AUTHENTICATION_AUTO_CONNECT` has **no** per-app override — global flag only.

### (b) Is a `CustomSocialAccountAdapter` override still needed?

**No — configuration alone is sufficient.** None of the three relevant `DefaultSocialAccountAdapter` methods (`is_email_verified`, `can_authenticate_by_email`, `authenticate_by_email`) need overriding; the settings above drive their default behavior exactly as required, and the auto-connect happens inside allauth's internal `SocialLogin._accept_login()` flow when `EMAIL_AUTHENTICATION_AUTO_CONNECT=True`. There is no password-confirmation view anywhere in this code path — allauth never prompts for a password on the email-match path; the settings just gate whether the match/connect is *permitted*. `CustomSocialAccountAdapter` needs no changes for this ticket, and in particular **should not** be extended to suppress `wipe_password` (see (c)).

### (c) THE CRUX — `wipe_password`: what it does, and keep it

`wipe_password` lives at `allauth/socialaccount/internal/flows/email_authentication.py` (verified directly, full source read):

```python
def wipe_password(request, user, email) -> None:
    """
    Consider a scenario where an attacker signs up for an account using the
    email address of a victim. Obviously, the email address cannot be
    verified, yet the attacker -- knowing the password -- can wait until the
    victim appears. When the victim signs in using email authentication, it
    is not obvious that the victim is signing into an account that was not
    created by the victim. As a result, both the attacker and the victim now
    have access to the account. To prevent this, we wipe the password of the
    account in case the email address was not verified, effectively locking
    out the attacker.
    """
    try:
        address = EmailAddress.objects.get_for_user(user, email)
    except EmailAddress.DoesNotExist:
        address = None
    if address and address.verified:
        return  # verified email address, no reason to worry
    if user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])
    if allauth_settings.USERSESSIONS_ENABLED:
        from allauth.usersessions.internal.flows.sessions import end_other_sessions
        end_other_sessions(request, user)
```

allauth's own docstring states the exact threat model this defends against. Behavior, confirmed:

1. It looks up the **matched local user's own** `EmailAddress` row for that address. If one exists **and** is `verified=True`, it returns immediately — no wipe. Safe case.
2. Otherwise (no local `EmailAddress` row, or an unverified one) it calls `set_unusable_password()` + a targeted `save(update_fields=["password"])` — a real, irreversible password mutation, nothing else touched.
3. It does not itself end other sessions unless the optional `allauth.usersessions` app is installed (`USERSESSIONS_ENABLED`) — not the case in MiqaResearch's `INSTALLED_APPS`, so that branch is inert here.
4. **Django's own session machinery makes explicit session termination unnecessary anyway**: `AbstractBaseUser.get_session_auth_hash()` is an HMAC over the `password` field, recomputed and compared by `django.contrib.auth.get_user()` on every request. Wiping the password changes this hash, so an attacker's session gets flushed on their very next request, with zero extra configuration (Django 6.0.8, `django/contrib/auth/base_user.py` + `__init__.py`).

**When it fires**: only on the very first SSO login for a given social identity, when matched to a local user purely via email match (no pre-existing `SocialAccount` row) — exactly this ticket's scenario. It is **never** invoked by the separate, manually-initiated "connect a new provider to my already-logged-in account" flow (`internal/flows/connect.py`), so a user deliberately linking a second SSO identity from their account settings while already authenticated is unaffected.

**Recommendation: keep `wipe_password` exactly as-is. Do not override or suppress it.**

Reasoning against the pre-hijacking threat model (attacker registers locally with the victim's email + a password only the attacker knows, before the victim ever tries SSO):

- "Auto-connect only matches verified local emails" is only half true and shouldn't be relied on as the sole defense. `authenticate_by_email` requires the **incoming/IdP-side** email to be verified, but the local-side lookup (`filter_users_by_email(prefer_verified=True)`, `allauth/account/utils.py`) only *prefers* a verified local `EmailAddress` match — if none exists, it falls back to matching **any** `EmailAddress` row for that address, verified or not. Under this project's current `ACCOUNT_EMAIL_VERIFICATION='optional'`, an attacker-created, never-verified shadow account is a valid fallback match.
- `wipe_password` is precisely the mitigation for that residual case: the attacker's local `EmailAddress` is unverified, so the very first time the real user logs in via SSO, the attacker's known password is immediately invalidated and any live attacker session is killed on its next request — with no configuration required. This is the load-bearing defense against the named attack, not an incidental side effect.
- Suppressing it would gain nothing: "no password-confirmation step for the legitimate user" is already fully satisfied by (a)/(b) alone — `wipe_password` and "no password prompt" are orthogonal. Removing it would only reopen the pre-hijacking hole.
- **Side-recommendation** (not a blocker for this ticket): consider tightening `ACCOUNT_EMAIL_VERIFICATION` from `'optional'` to `'mandatory'` for local signups now that SSO auto-linking is being introduced — this closes most of the practical risk further upstream, though `wipe_password` alone is sufficient to ship this ticket safely either way.

### Answers to the original bullet questions

- Settings to add: see (a) above (corrects the ticket's original guessed setting name).
- Adapter override needed beyond configuration: **no** (b).
- `wipe_password` resolution: **keep it, don't suppress it** — it's the actual defense against email-collision account takeover, not a bug to route around (c).
