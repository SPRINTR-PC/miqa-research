"""Test helper: a client-credentials Application with a Client Binding (#277) and a ready access token."""
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from oauth2_provider.models import AccessToken, Application

from MiqaResearch.data.models import ClientBinding


def bound_client(project, *, clinic=None, dicom_raw=False, scope="read", token=None, bound=True) -> dict:
    """Creates the client (bound to `project`/`clinic` unless `bound=False`) and a token; returns request kwargs."""
    application = Application.objects.create(
        name=f"client-{uuid4().hex[:8]}", user=None, client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )
    if bound:
        ClientBinding.objects.create(
            application=application, research_project=project, clinic=clinic, dicom_raw=dicom_raw)
    token = token or f"token-{uuid4().hex}"
    AccessToken.objects.create(
        token=token, application=application, user=None, scope=scope, expires=timezone.now() + timedelta(hours=1))
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
