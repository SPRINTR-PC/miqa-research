## Resolution: Authentication Context in Login Template

**Decision**: Extend the existing `auth_framework` context processor to provide granular authentication method flags to the login template.

### Approach

Add the following to the context processor in `MiqaResearch/context_processors.py`:

```python
def auth_framework(request):
    auth_modes = set(settings.MIRES_AUTHENTICATION_FRAMEWORK.split(","))
    
    context = {
        "oidc_login_enabled": settings.OIDC_LOGIN_ENABLED,
        "oidc_provider_display_name": settings.OIDC_PROVIDER_DISPLAY_NAME,
        # New additions for granular login options
        "passkey_login_enabled": "yubikey" in auth_modes,
        "eid_login_enabled": bool({"siths", "bankid"} & auth_modes),
        "siths_login_enabled": "siths" in auth_modes,
        "bankid_login_enabled": "bankid" in auth_modes,
    }
    # ... rest of function
```

### Template Changes

Update `account/login.partial.html` to conditionally render login options:

```django
{% if passkey_login_enabled %}
<div>...YubiKey/Passkey section...</div>
{% endif %}

{% if eid_login_enabled %}
<div>...SITHS/BankID section...</div>
{% endif %}
```

### Rationale

1. **Consistent with existing patterns**: The project already uses context processors for authentication-related template data
2. **Granular control**: Separates OIDC, Passkey, and E-ID options so they can be enabled/disabled independently
3. **Minimal changes**: Extends existing context processor rather than creating a new one
4. **Clear semantics**: Boolean flags make template logic straightforward
5. **Future-proof**: Easy to add new authentication methods

### Related

- Current `MIRES_AUTHENTICATION_FRAMEWORK` setting defaults to "yubikey" but supports comma-separated values
- Existing context processor already provides OIDC info
- MFA and SITHS/BankID are currently always shown in the template regardless of configuration