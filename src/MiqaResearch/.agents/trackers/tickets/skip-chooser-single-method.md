# Redirect nav Sign-In straight to the IdP when SSO is the sole configured auth mode

Part of: wayfinder-sso-auto-provisioning-map

## Question

Today, clicking the nav "Sign In" button always HTMX-loads `templates/account/login.partial.html` (the "Choose your preferred login method" chooser), via the custom `LoginView` at `MiqaResearch/interfaces/http/views/accounts/login.py`, which subclasses allauth's `LoginView` and overrides `get_template_names()` for HTMX vs. full-page rendering. When `MIRES_AUTHENTICATION_FRAMEWORK` (see `MiqaResearch/settings.py` ~L209-213, `MiqaResearch/context_processors.py`'s `auth_framework`) configures SSO (`oidc` or `adfs`) as the **only** enabled auth mode, there's nothing to choose — the destination wants this case to redirect straight to the IdP (`reverse("openid_connect_login", kwargs={"provider_id": settings.OIDC_PROVIDER_ID})`) instead of rendering the chooser, for both the HTMX partial path and a plain full-page GET to `/accounts/login/`.

Decide:

- Where to compute "SSO is the only enabled mode" — reuse/extend the `_AUTH_MODES` set logic already in `settings.py`, exposed as a new boolean (e.g. `OIDC_ONLY_AUTH_MODE` alongside `OIDC_LOGIN_ENABLED`), vs. computing it in the view itself.
- How the custom `LoginView` should short-circuit to a redirect. Likely by overriding `get()` (before `get_template_names()`/`render_to_response()` are reached) to return an `HttpResponseRedirect` to the OIDC login URL when the mode-only flag is set — but for an HTMX request, a redirect response needs an `HX-Redirect` header (not a normal 30x) for the client-side `hx-get`-swap to actually navigate the browser instead of swapping the redirect's body into `#mires-main`. Confirm how `django_htmx` (already installed) expects this to be signaled, and whether `django_htmx.http.HttpResponseClientRedirect` (or equivalent) is the right tool.
- Confirm this doesn't break the multi-method case (e.g. `oidc` + `yubikey` both enabled) — chooser must still render normally then.
- Confirm interaction with a direct/bookmarked GET to `/accounts/login/?process=...` or with `next=` redirect params — the short-circuit shouldn't drop them.

Record: the exact code change to `MiqaResearch/interfaces/http/views/accounts/login.py` (and any new settings/context-processor flag), including how the HTMX case is handled correctly.

## Type
research

## Status
resolved

## Findings

**Verification note:** the research pass that produced this drafted several claims `[UNVERIFIED]` due to no network access in that session. All of them have since been confirmed directly against the actual installed packages in `.venv/` (not against docs) — see inline confirmations below. Nothing here is speculative.

### 1. Why a plain redirect doesn't work for HTMX, and the fix

htmx issues its requests via `fetch()`/`XHR`. A 3xx response to a fetch/XHR call is followed **transparently by the browser** before any JavaScript — including htmx — ever sees it; the calling code only observes the final response body. So a normal Django `redirect()`/`HttpResponseRedirect` returned from `LoginView.get()` to an `hx-get` request would have its redirect chain silently followed by the browser, and whatever HTML comes back at the end gets swapped into the DOM target — the address bar / top-level document never navigates, so the user is not actually sent to the IdP.

`django_htmx.http.HttpResponseClientRedirect` (confirmed directly, `.venv/lib/python3.14/site-packages/django_htmx/http.py:35-45`) is exactly the tool: it's an `HttpResponseRedirectBase` subclass, constructed as `HttpResponseClientRedirect(redirect_to)`, that returns a **200** status and sets `self["HX-Redirect"] = self["Location"]` (then deletes `Location`). htmx's client JS reads `HX-Redirect` on any response and performs a real `window.location = ...` top-level navigation — required here since the destination is an external IdP endpoint, not an in-app fragment. (There's also `HttpResponseLocation`/`HX-Location` for in-app client-side navigation via htmx's own AJAX boosting — not appropriate here since we need a real navigation off-site.)

`request.htmx` is confirmed available: `django_htmx/middleware.py:38/42` sets `request.htmx = HtmxDetails(request)` in `HtmxMiddleware`, which is already installed. For a plain non-HTMX GET, an ordinary `HttpResponseRedirect`/`redirect(...)` is correct and sufficient — the browser's top-level navigation follows a 302 natively.

### 2. Where to put the short-circuit on the custom `LoginView`

Confirmed directly (`.venv/lib/python3.14/site-packages/allauth/account/views.py:89-94`): allauth's `LoginView` is composed as `LoginView(NextRedirectMixin, RedirectAuthenticatedUserMixin, AjaxCapableProcessFormViewMixin, FormView)` — the already-authenticated-user redirect is implemented by one of these mixins short-circuiting early in `dispatch()`/`get()`, before the form-rendering path runs, rather than through `get_context_data()` or the template layer (which only run after rendering has already started).

This project's `LoginView` currently only overrides `get_template_names()` — that hook only affects *which template* is rendered, it cannot prevent the chooser from rendering and has no way to return a redirect. The SSO-only short-circuit must live in a `get()` override that runs first and either returns early (redirect) or delegates to `super().get(...)` (render the chooser as before, unchanged).

### 3. Settings constant vs. per-request computation — decision

Compute a new module-level constant in `settings.py`, next to the existing `OIDC_LOGIN_ENABLED` line:

```python
OIDC_LOGIN_ENABLED = bool({"oidc", "adfs"} & _AUTH_MODES)
SSO_ONLY_LOGIN_ENABLED = OIDC_LOGIN_ENABLED and _AUTH_MODES <= {"oidc", "adfs"}
```

`_AUTH_MODES` is derived once from an env var at process start and never changes at runtime, so recomputing the subset check per request buys nothing and creates a second place where "which auth modes are enabled" logic could drift from `OIDC_LOGIN_ENABLED`. It's a deployment-configuration fact (like `DEBUG`), not per-request business logic — `settings.SSO_ONLY_LOGIN_ENABLED` reads consistently with the existing pattern and is trivially overridable via `settings` fixtures, matching how `tests/test_login_view.py` (confirmed to exist) already does `settings.MIRES_AUTHENTICATION_FRAMEWORK = "yubikey"` in its tests.

### 4. Multi-method case — must not regress

`SSO_ONLY_LOGIN_ENABLED` is only `True` when `_AUTH_MODES` is a non-empty subset of `{"oidc", "adfs"}`. For `MIRES_AUTHENTICATION_FRAMEWORK=oidc,yubikey` (or any combination with more than one mode), `_AUTH_MODES <= {"oidc", "adfs"}` is `False`, so `SSO_ONLY_LOGIN_ENABLED` is `False` and `get()` falls straight through to `super().get(...)`, rendering the chooser exactly as today. The short-circuit is additive and only fires in the single-mode SSO case — existing tests in `tests/test_login_view.py` (which use `yubikey` and `siths,bankid` configs) are unaffected since none of those configurations are subsets of `{"oidc", "adfs"}`.

### 5. `next=`/`process=` handling

`reverse("openid_connect_login", kwargs={"provider_id": ...})` only builds the path — it doesn't carry over the original request's query string, so a naive `redirect(reverse(...))` would silently drop `?next=/some/page` (or `?process=...`) present on `/accounts/login/?next=...`. Forward it explicitly via `request.GET.urlencode()`:

```python
target = reverse("openid_connect_login", kwargs={"provider_id": settings.OIDC_PROVIDER_ID})
query = request.GET.urlencode()
if query:
    target = f"{target}?{query}"
```

**Side note (pre-existing, out of this ticket's scope but worth a follow-up ticket):** `context_processors.py`'s `oidc_login_url` — used for the manual "Sign in with SSO" card link in the chooser today — has this same gap; it never forwards `next`/`process` either. Both paths (manual click and auto-redirect) should eventually behave consistently.

### 6. Code sketch for `LoginView`

```python
# interfaces/http/views/accounts/login.py
from allauth.account.views import LoginView as AllauthLoginView
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django_htmx.http import HttpResponseClientRedirect


class LoginView(AllauthLoginView):
    def get(self, request, *args, **kwargs):
        if settings.SSO_ONLY_LOGIN_ENABLED:
            return self._redirect_to_sso(request)
        return super().get(request, *args, **kwargs)

    def _redirect_to_sso(self, request):
        target = reverse(
            "openid_connect_login",
            kwargs={"provider_id": settings.OIDC_PROVIDER_ID},
        )
        query = request.GET.urlencode()
        if query:
            target = f"{target}?{query}"

        if request.htmx:
            return HttpResponseClientRedirect(target)
        return HttpResponseRedirect(target)

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return ["account/login.partial.html"]
        return super().get_template_names()
```

`get_template_names()` is left untouched; it's now only reached in the non-short-circuited (multi-method or non-SSO) case, which is its existing behavior.

### Suggested test coverage (not yet written)

- `SSO_ONLY_LOGIN_ENABLED=True` (`MIRES_AUTHENTICATION_FRAMEWORK="oidc"` or `"adfs"`) + plain GET → 302 to the `openid_connect_login` URL.
- Same config + `HTTP_HX_REQUEST="true"` → 200 with `HX-Redirect` header set to the `openid_connect_login` URL (not a rendered chooser body).
- Same config + `?next=/foo` → redirect target includes `?next=%2Ffoo`.
- `MIRES_AUTHENTICATION_FRAMEWORK="oidc,yubikey"` → chooser still renders (existing behavior unchanged, both templates still reachable).
