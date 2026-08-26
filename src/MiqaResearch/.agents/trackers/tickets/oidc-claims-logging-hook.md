# Hook point and format for dev-mode OIDC claims logging

Part of: wayfinder-sso-auto-provisioning-map

## Question

Destination decision (already settled with the user): a new setting `MIRES_OIDC_LOG_CLAIMS` (bool, default = `MIRES_DEBUG`'s current value, but independent of it thereafter) should, when true, log the full merged OIDC claims dict (userinfo + decoded id_token — the same shape `CustomSocialAccountAdapter._pick_claims()` in `helpers/authentication/custom_oidc_backend.py` already assembles) at Python `DEBUG` log level, for every SSO login. Also decided: roles present in claims but not mapped to any `Group` (see `update_user_roles()` in the same file) should be logged similarly, so admins can spot a stale role mapping — without blocking login when zero roles match.

Decide:

- Where in `CustomSocialAccountAdapter`'s pipeline to log the claims: inside `_pick_claims()` itself (single choke point, called from both `pre_social_login` and `save_user`), vs. a dedicated method called from both. Prefer the choke point that fires exactly once per login attempt, not once per adapter method invocation (check whether both `pre_social_login` and `save_user` can fire in the same request for a new signup, which would double-log if hooked naively).
- Logger name/module convention to use — check whether this project already has a `LOGGING` config in `MiqaResearch/settings.py` with named loggers/handlers to match (grep for `LOGGING = ` / `getLogger`), or whether a new logger name needs to be introduced.
- Where to add the new setting in `MiqaResearch/settings.py`: env var `MIRES_OIDC_LOG_CLAIMS=(bool, default=<value of MIRES_DEBUG>)` in the `env.Env(...)` schema block (~L65-72 alongside the other `MIRES_OIDC_*` entries), and the derived internal setting name (e.g. `OIDC_LOG_CLAIMS`, matching the `OIDC_ROLES_CLAIM` naming convention) — confirm `django-environ`'s `Env` schema supports a default that references another env var's resolved value, or whether it needs to be computed manually after both are read.
- Format: single structured log line (e.g. `logger.debug("OIDC claims received: %s", claims)`) vs. pretty-printed multi-line — pick whichever fits how this project's existing logging is configured/consumed (check `MiqaResearch/settings.py` `LOGGING` block and any existing `logger.debug(...)` calls in `helpers/` for house style).

Record: the exact code to add to `custom_oidc_backend.py` and `settings.py`, including the unmatched-roles logging.

## Type
research

## Status
resolved

## Findings

### (a) Hook point: `update_user_roles()`, not `_pick_claims()`

Traced the two call sites in the current adapter:

```python
def pre_social_login(self, request, sociallogin):
    if sociallogin.is_existing:
        self.update_user_roles(sociallogin.user, self._pick_claims(sociallogin))

def save_user(self, request, sociallogin, form=None):
    user = super().save_user(request, sociallogin, form)
    self.update_user_roles(user, self._pick_claims(sociallogin))
    return user
```

`_pick_claims(sociallogin)` is only ever evaluated inside one of these two call expressions — no third call site. Because the `pre_social_login` call is wrapped in `if sociallogin.is_existing:`, for a **new signup** (`is_existing=False`) that whole line never executes; only `save_user`'s call runs. For an **existing** user, only `pre_social_login`'s call runs (`save_user` isn't invoked by allauth for an existing account). So `_pick_claims()`/`update_user_roles()` is already guaranteed to run **exactly once per login/signup completion**.

Either method is technically safe to log from today, but `update_user_roles()` is the more robust hook point: it's the single point both flows already converge on by design (immune to a future refactor of `pre_social_login` accidentally introducing double-logging), it already receives the resolved `claims` dict as a plain parameter, and it's the method `tests/test_oidc_adapter.py` already exercises directly, so the new logging is covered by existing unit tests without needing a full allauth request cycle.

**Recommendation:** add both the claims-dump log and the unmatched-roles log as statements inside `update_user_roles()`. Do not add logging inside `_pick_claims()` or add a new unconditional call in `pre_social_login()`.

### (b) Logger name

House style in this repo (checked via `grep -rn "logging.getLogger("`) is overwhelmingly `logger = logging.getLogger(__name__)` at module scope (`helpers/vault.py`, `helpers/db_fields.py`, `helpers/study_participant_alias.py`, `MiqaResearch/actions/consents/participant_consents.py`, `MiqaResearch/interfaces/http/api/views/upload_data/upload_consent.py`, `MiqaResearch/tasks/ocr.py`, plus a data migration). One outlier (`MiqaResearch/tasks/participant_consent.py`) hardcodes `logging.getLogger("mires")`. `custom_oidc_backend.py` currently has no logger.

**Recommendation:** follow the dominant convention — `logger = logging.getLogger(__name__)`, resolving to `helpers.authentication.custom_oidc_backend`. `settings.LOGGING` (confirmed, `MiqaResearch/settings.py:298-326`) only configures a `root` logger with `console`/`file` handlers — no per-app loggers — so this propagates automatically; no `LOGGING` block changes needed.

**Important double-gating caveat (confirmed against real settings.py):** the root logger's level is `env("MIRES_LOGGING_LEVEL")`, defaulting to `"INFO"` — a bare `logger.debug()` call will **not** be emitted unless `MIRES_LOGGING_LEVEL=DEBUG` is *also* set, on top of `OIDC_LOG_CLAIMS` being true. This is intentional per the destination-grilling decision (Q7): the flag protects against leaking claims-PII just because someone bumped the log level for unrelated reasons, and the log level protects against verbose output in normal dev use — but it means local dev setup docs / `.env.example` need to call out that **both** `MIRES_OIDC_LOG_CLAIMS=True` and `MIRES_LOGGING_LEVEL=DEBUG` are required to actually see claims in the console/file output. Keeping `logger.debug` (not bumping to `INFO`) is the right call — it matches the settled decision and costs only this one documentation note.

### (c) `MIRES_OIDC_LOG_CLAIMS` → `OIDC_LOG_CLAIMS`, defaulting to `MIRES_DEBUG`

`django-environ`'s `Env(**scheme)` schema is evaluated once, at the `environ.Env(...)` call site — it has no mechanism for one schema entry's default to reference another entry's *resolved* value. Confirmed directly against `environ/environ.py:get_value()` (line ~510): `if default is self.NOTSET: default = var_info[1]` — i.e. the scheme's own default is only used when the call-site `default=` kwarg is left at the `NOTSET` sentinel; passing an explicit `default=` at the call site (a plain Python value, resolved after `DEBUG` is already read) always wins. This is exactly the pattern already used elsewhere in `settings.py` (e.g. `EID_CLIENT_ID = env("MIRES_EID_CLIENT_ID", default=None)`, `CELERY_BROKER_URL = env(..., default="amqp://...")`).

**Schema addition** (alphabetically slotted among the existing `MIRES_OIDC_*` entries — `CLIENT_ID, CLIENT_SECRET, DISCOVERY_URL, PROVIDER_DISPLAY_NAME, ROLES_CLAIM` are already alpha-sorted, so `LOG_CLAIMS` goes between `DISCOVERY_URL` and `PROVIDER_DISPLAY_NAME`):

```python
env = environ.Env(
    ...
    MIRES_OIDC_DISCOVERY_URL=(str, None),
    MIRES_OIDC_LOG_CLAIMS=(bool, False),
    MIRES_OIDC_PROVIDER_DISPLAY_NAME=(str, "SSO"),
    ...
)
```

**Derived setting** (next to the other `OIDC_*` derived settings, after `DEBUG` has already been resolved earlier in the file):

```python
OIDC_PROVIDER_ID = "mires-oidc"
OIDC_LOGIN_ENABLED = bool({"oidc", "adfs"} & _AUTH_MODES)
OIDC_PROVIDER_DISPLAY_NAME = env("MIRES_OIDC_PROVIDER_DISPLAY_NAME")
OIDC_ROLES_CLAIM = env("MIRES_OIDC_ROLES_CLAIM")
OIDC_LOG_CLAIMS = env("MIRES_OIDC_LOG_CLAIMS", default=DEBUG)
```

If `MIRES_OIDC_LOG_CLAIMS` is unset, it defaults to whatever `MIRES_DEBUG` resolved to; if explicitly set in `.env`, it overrides that regardless of `MIRES_DEBUG`. No plain `if/else` needed.

### (d) Logging unmatched roles inside `update_user_roles()`

`OIDCRoleMapping.oidc_role` is `unique=True` (`MiqaResearch/data/models/oidc_role_mapping.py`, confirmed), so the matched subset of incoming roles can be fetched directly and diffed against the incoming list, rather than working backwards from `target_groups` (which only tells you which `Group`s matched, not which raw incoming role strings did):

```python
def update_user_roles(self, user, claims):
    if settings.OIDC_LOG_CLAIMS:
        logger.debug("Merged OIDC claims for user %s: %s", user, claims)

    oidc_roles = claims.get(settings.OIDC_ROLES_CLAIM, [])

    if isinstance(oidc_roles, str):
        oidc_roles = [oidc_roles]

    matched_roles = set(
        OIDCRoleMapping.objects.filter(oidc_role__in=oidc_roles).values_list("oidc_role", flat=True)
    )
    unmatched_roles = set(oidc_roles) - matched_roles
    if unmatched_roles:
        logger.warning(
            "User %s presented OIDC role(s) %s with no configured OIDCRoleMapping; "
            "no group will be granted for these roles.",
            user, sorted(unmatched_roles),
        )

    target_groups = Group.objects.filter(oidc_role_mappings__oidc_role__in=oidc_roles)
    user.groups.set(target_groups)
```

Recommend `logger.warning`, **unconditional** (not gated behind `OIDC_LOG_CLAIMS`) — role strings alone aren't sensitive PII the way the full claims dict can be, and an unmapped role is an actionable misconfiguration signal (missing `OIDCRoleMapping` row) that's just as relevant in production as in dev. Gating it behind the dev-only flag would hide a real ops signal from production logs.

### Full code sketch — `helpers/authentication/custom_oidc_backend.py`

```python
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import Group

from MiqaResearch.data.models import OIDCRoleMapping

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            self.update_user_roles(sociallogin.user, self._pick_claims(sociallogin))

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        self.update_user_roles(user, self._pick_claims(sociallogin))
        return user

    @staticmethod
    def _pick_claims(sociallogin):
        extra_data = sociallogin.account.extra_data
        return extra_data.get("userinfo") or extra_data.get("id_token") or extra_data

    def update_user_roles(self, user, claims):
        if settings.OIDC_LOG_CLAIMS:
            logger.debug("Merged OIDC claims for user %s: %s", user, claims)

        oidc_roles = claims.get(settings.OIDC_ROLES_CLAIM, [])

        if isinstance(oidc_roles, str):
            oidc_roles = [oidc_roles]

        matched_roles = set(
            OIDCRoleMapping.objects.filter(oidc_role__in=oidc_roles).values_list("oidc_role", flat=True)
        )
        unmatched_roles = set(oidc_roles) - matched_roles
        if unmatched_roles:
            logger.warning(
                "User %s presented OIDC role(s) %s with no configured OIDCRoleMapping; "
                "no group will be granted for these roles.",
                user, sorted(unmatched_roles),
            )

        target_groups = Group.objects.filter(oidc_role_mappings__oidc_role__in=oidc_roles)
        user.groups.set(target_groups)
```

### Full code sketch — `MiqaResearch/settings.py` (diff-style)

```diff
 env = environ.Env(
     ...
     MIRES_OIDC_DISCOVERY_URL=(str, None),
+    MIRES_OIDC_LOG_CLAIMS=(bool, False),
     MIRES_OIDC_PROVIDER_DISPLAY_NAME=(str, "SSO"),
     MIRES_OIDC_ROLES_CLAIM=(str, "role"),
     ...
 )
 ...
 OIDC_PROVIDER_ID = "mires-oidc"
 OIDC_LOGIN_ENABLED = bool({"oidc", "adfs"} & _AUTH_MODES)
 OIDC_PROVIDER_DISPLAY_NAME = env("MIRES_OIDC_PROVIDER_DISPLAY_NAME")
 OIDC_ROLES_CLAIM = env("MIRES_OIDC_ROLES_CLAIM")
+OIDC_LOG_CLAIMS = env("MIRES_OIDC_LOG_CLAIMS", default=DEBUG)
```

All open items from the initial research pass (the `environ.py` call-site-default confirmation, and the `logger.debug` vs. `logger.warning`-for-unmatched-roles level choice) are now resolved above.
