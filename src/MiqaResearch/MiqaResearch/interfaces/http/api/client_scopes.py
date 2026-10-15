"""Which OAuth2 scopes a client may obtain (ADR 0027), as django-oauth-toolkit's scopes backend.

`dicom:raw` is only for a client whose Client Binding was granted it; every other scope stays as
before (the other `read` endpoints aren't bound yet, #216). A token that already carries
`dicom:raw` is still re-checked against the binding on each raw request (views/dicom/access.py),
so a revoked grant takes effect at once.
"""
from oauth2_provider.scopes import SettingsScopes

from contract.constants.scopes import SCOPE_DICOM_RAW
from MiqaResearch.data.models import ClientBinding


class ClientBindingScopes(SettingsScopes):
    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        scopes = [scope for scope in super().get_available_scopes(application, request) if scope != SCOPE_DICOM_RAW]
        if application is not None and ClientBinding.objects.filter(application=application, dicom_raw=True).exists():
            scopes.append(SCOPE_DICOM_RAW)
        return scopes
