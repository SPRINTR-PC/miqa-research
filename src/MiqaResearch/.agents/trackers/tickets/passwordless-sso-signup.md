# Bypass password requirement for automatic passwordless SSO signup

Part of: wayfinder-sso-auto-provisioning-map

## Question

`ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']` (`MiqaResearch/settings.py`) requires a password, which a social/SSO login can never supply — this is what currently forces allauth to fall back to a manual signup form for first-time SSO logins instead of auto-creating the account.

The destination requires: a first-time SSO login auto-creates the `User` with **zero** extra screens (no signup form, no password fields) whenever `CustomSocialAccountAdapter` can resolve an email from claims (see `OIDC_EMAIL_CLAIM` fallback chain — a sibling concern, not this ticket's job to design). The regular email+password self-signup form and its password requirement must remain completely unaffected for non-SSO signups.

Investigate django-allauth 65.19's `DefaultSocialAccountAdapter` / `DefaultAccountAdapter` API (installed at `.venv/lib/python3.14/site-packages/allauth/`) and decide the cleanest mechanism, e.g.:

- Overriding `is_auto_signup_allowed(request, sociallogin)` on `CustomSocialAccountAdapter` (`allauth/socialaccount/adapter.py:212`) to force `True` once an email is available, regardless of `ACCOUNT_SIGNUP_FIELDS`.
- Whether `populate_user()` / `save_user()` on the adapter need overriding to skip password creation for socially-created users (e.g. `user.set_unusable_password()`), and whether that alone bypasses the form, or whether `ACCOUNT_SIGNUP_FIELDS` is even consulted at all on the auto-signup path vs. only on the manual-form path.
- Whether `is_open_for_signup()` (`allauth/socialaccount/adapter.py:219`) needs anything special.
- Confirm the manual email+password signup form (`account_signup`, `ACCOUNT_SIGNUP_FIELDS`) is untouched by whatever mechanism is chosen — trace what actually reads `ACCOUNT_SIGNUP_FIELDS` (likely `allauth.account.forms`) to be sure a social-only override doesn't leak into it.

Record: the exact adapter method(s) to override, their implementation sketch, and confirmation that the regular signup form's password requirement is unaffected.

## Type
research

## Status
resolved

## Findings

### Decision

Override a single method on `CustomSocialAccountAdapter` (`helpers/authentication/custom_oidc_backend.py`):

- **`is_auto_signup_allowed(self, request, sociallogin)`** — force `True` whenever an email is resolvable from the social login, instead of relying implicitly on the `SOCIALACCOUNT_AUTO_SIGNUP` Django setting.

No change is needed to `populate_user()`, `save_user()`, or `is_open_for_signup()` — see reasoning below. This keeps the change minimal and localized to the one decision point that actually gates "auto-create vs. show a form".

### Why `is_auto_signup_allowed` is the right (and sufficient) lever

Traced the full call chain for a first-time social login, all in `.venv/lib/python3.14/site-packages/allauth/`:

1. `socialaccount/helpers.py:complete_social_login()` → `socialaccount/internal/flows/login.py:complete_login()` → `_authenticate()` → since `sociallogin.is_existing` is `False` for a first-time login: `process_signup(request, sociallogin)` (`socialaccount/internal/flows/signup.py:109`).
2. `process_signup()` first checks `get_adapter().is_open_for_signup(request, sociallogin)` (raises `SignupClosedException` if closed), then calls `process_auto_signup(request, sociallogin)` (`signup.py:44`).
3. `process_auto_signup()` calls `get_adapter().is_auto_signup_allowed(request, sociallogin)` **first**. If that's falsy, it returns `(False, None)` immediately and `process_signup()` takes the `redirect_to_signup()` branch — this is what lands the user on the `socialaccount_signup` form (the one that inherits `ACCOUNT_SIGNUP_FIELDS`, see below). If it's truthy, it goes on to `process_auto_signup_email()` (checks `assess_unique_email()` — `True`/unique → proceed, `False`/conflict → fall back to the form, `None`/enumeration-prevention → send a "check your email" style response, not the form) and `process_auto_signup_phone()` (a no-op unless a `phone` field is configured in `ACCOUNT_SIGNUP_FIELDS`, which it isn't here).
4. If auto-signup is allowed: `process_signup()` calls `get_adapter().save_user(request, sociallogin, form=None)` directly (`signup.py:132`) — **note `form=None`** — then `complete_social_signup()`. No form, no view render, no extra screen.

`DefaultSocialAccountAdapter.is_auto_signup_allowed` (`socialaccount/adapter.py:212-217`, verified directly) just returns `app_settings.AUTO_SIGNUP`, which resolves to the `SOCIALACCOUNT_AUTO_SIGNUP` Django setting, **defaulting to `True`**. `MiqaResearch/settings.py` never sets `SOCIALACCOUNT_AUTO_SIGNUP`, so today this already evaluates to `True` by default. The override is still worth adding explicitly rather than relying on the implicit default, for two reasons: (a) it documents the intent ("SSO with a resolvable email always auto-signs-up") directly on the adapter that owns OIDC-specific behavior, and (b) it hardens against a future, unrelated change to `SOCIALACCOUNT_AUTO_SIGNUP` (e.g. someone disabling it for a different provider) silently reintroducing the manual-form fallback for OIDC.

### Why `populate_user()` / `save_user()` don't need changes

`DefaultSocialAccountAdapter.save_user()` (`socialaccount/adapter.py:153-166`, verified directly) already does the password bypass unconditionally, *before* branching on whether a form was supplied:

```python
def save_user(self, request, sociallogin, form=None):
    u = sociallogin.user
    u.set_unusable_password()
    account_adapter = get_account_adapter()
    if form:
        account_adapter.save_user(request, u, form)
    else:
        account_adapter.populate_username(request, u)
    sociallogin.save(request)
    return u
```

`set_unusable_password()` runs regardless of the `form` branch, so a socially-created user never needs a password, with or without any override. `CustomSocialAccountAdapter.save_user()` already does `super().save_user(request, sociallogin, form)` before its own role-assignment logic, so this behavior is inherited for free. On the auto-signup path `form` is always `None` (per step 4 above), so the `account_adapter.save_user(request, u, form)` branch that would otherwise validate `password1`/`password2` from a form is never even reached. `populate_user()` only fills `username`/`first_name`/`last_name`/`email` from provider data (verified directly) and has no password logic to bypass — no override needed.

### Why `is_open_for_signup()` doesn't need anything special

`DefaultSocialAccountAdapter.is_open_for_signup()` (`socialaccount/adapter.py:219-227`, verified directly) delegates straight to `get_account_adapter(request).is_open_for_signup(request)` — i.e. the *account* adapter's method, shared with the manual signup path. `DefaultAccountAdapter.is_open_for_signup()` just returns `True` unconditionally, and the project doesn't set `ACCOUNT_ADAPTER` to a custom class or any setting that would change this. Leave it alone.

### Confirmed: `ACCOUNT_SIGNUP_FIELDS` cannot leak into the auto-signup path

Traced where `ACCOUNT_SIGNUP_FIELDS` is actually read (verified directly against `allauth/account/forms.py`):

- `allauth/account/app_settings.py` — `SIGNUP_FIELDS` property reads the `ACCOUNT_SIGNUP_FIELDS` Django setting into a `{field_name: {"required": bool}}` dict.
- The **only** consumer of `app_settings.SIGNUP_FIELDS` is `allauth/account/forms.py`: `BaseSignupForm` (`signup_fields = app_settings.SIGNUP_FIELDS`, line ~320) and its subclass `SignupForm` (conditionally adds `password1`/`password2` fields based on that dict).
- `BaseSignupForm`/`SignupForm` is used by exactly two views, both requiring an actual HTTP GET/POST to a form-rendering view — neither is on the auto-signup call path:
  - `allauth.account.views.SignupView` → the `account_signup` URL. This is the **manual** email+password self-signup entry point. Nothing in this ticket's change touches `ACCOUNT_ADAPTER`, this view, or this form — it is structurally unreachable from any code path a `SOCIALACCOUNT_ADAPTER` override runs on.
  - `allauth.socialaccount.views.SignupView` → the `socialaccount_signup` URL. This is only ever reached via `redirect_to_signup()` (`socialaccount/internal/flows/signup.py:27-29`), which is only called when `process_auto_signup()` returned `False` (step 3 above). Once `is_auto_signup_allowed()` is forced `True` for resolvable-email OIDC logins, `redirect_to_signup()` — and therefore this form and its `ACCOUNT_SIGNUP_FIELDS`-derived password fields — is simply never invoked for the happy path this ticket targets.

So: `ACCOUNT_SIGNUP_FIELDS` is read once, by one form base class, consumed by two views that both require rendering a page — and the fix works entirely by making sure the OIDC auto-signup flow never reaches either of those views. The manual signup form/view is a completely separate code path and is provably unaffected by anything done in `CustomSocialAccountAdapter`.

### Implementation sketch

```python
# helpers/authentication/custom_oidc_backend.py
from allauth.account.utils import user_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import Group


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_auto_signup_allowed(self, request, sociallogin):
        # First-time SSO logins must auto-create the User with zero extra
        # screens whenever we already have a resolvable email (see the
        # OIDC_EMAIL_CLAIM fallback chain elsewhere) — don't depend on the
        # SOCIALACCOUNT_AUTO_SIGNUP default for this. This only affects the
        # SOCIALACCOUNT_ADAPTER path; ACCOUNT_SIGNUP_FIELDS / the manual
        # email+password signup form is untouched (see ticket Findings).
        if sociallogin.email_addresses or user_email(sociallogin.user):
            return True
        return super().is_auto_signup_allowed(request, sociallogin)

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            self.update_user_roles(sociallogin.user, self._pick_claims(sociallogin))

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)  # already sets an unusable password
        self.update_user_roles(user, self._pick_claims(sociallogin))
        return user

    # ... _pick_claims / update_user_roles unchanged
```

Notes on the sketch:

- `is_auto_signup_allowed` is the only new method. Everything else in `custom_oidc_backend.py` stays as-is.
- Deliberately does **not** unconditionally `return True` — only forces auto-signup when an email is actually present, so the pre-existing "email required but missing" and "duplicate email" safety checks in `process_auto_signup_email()`/`assess_unique_email()` still run and can still fall back to the (rare, edge-case) form or enumeration-safe response. That fallback is out of this ticket's "zero-screens happy path" scope and is an acceptable, existing allauth safety net.
- No settings.py change is required or recommended: `ACCOUNT_SIGNUP_FIELDS` stays exactly as-is and continues to govern only the manual signup form.
