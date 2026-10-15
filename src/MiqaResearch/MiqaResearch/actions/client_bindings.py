"""Machine clients with a Client Binding (ADR 0027): issue, change, rotate and revoke.

Callers check who may act (`readers.client_binding_permissions`); these enforce the data rules:
a client belongs to one project for good (no project argument after issue), its Site must be one of
the project's Sites, and its secret exists in plain text only in the return value of `issue_client`
and `rotate_client_secret` (django-oauth-toolkit stores it hashed). Every change is audit-logged with
the acting user and identifiers only; `dicom:raw` grants and revocations are separate data-access
events (ADR 0024). A client is an `Application` with no user: it outlives its issuer's role.
"""
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.db import transaction
from oauth2_provider.generators import generate_client_secret
from oauth2_provider.models import AccessToken, Application

from contract.constants.audit_log import (
    EVENT_TYPE_API_CLIENT_ISSUED,
    EVENT_TYPE_API_CLIENT_REVOKED,
    EVENT_TYPE_API_CLIENT_SECRET_ROTATED,
    EVENT_TYPE_API_CLIENT_UPDATED,
    EVENT_TYPE_DICOM_RAW_GRANTED,
    EVENT_TYPE_DICOM_RAW_REVOKED,
)
from MiqaResearch.data.models import AuditLog, ClientBinding
from MiqaResearch.data.models.research_project import ResearchProjectClinicMap


class ClientBindingError(Exception):
    """A change the data rules refuse; the message is shown to the user."""


@dataclass(frozen=True)
class IssuedSecret:
    binding: ClientBinding
    client_secret: str


async def issue_client(*, project, user, request, name, site=None, dicom_raw=False) -> IssuedSecret:
    return await sync_to_async(_issue_client)(project, user, request, name, site, dicom_raw)


async def update_client(*, binding, user, request, site, dicom_raw) -> ClientBinding:
    return await sync_to_async(_update_client)(binding, user, request, site, dicom_raw)


async def rotate_client_secret(*, binding, user, request) -> IssuedSecret:
    return await sync_to_async(_rotate_client_secret)(binding, user, request)


async def revoke_client(*, binding, user, request) -> None:
    await sync_to_async(_revoke_client)(binding, user, request)


def _issue_client(project, user, request, name, site, dicom_raw) -> IssuedSecret:
    _require_project_site(project, site)
    secret = generate_client_secret()
    with transaction.atomic():
        application = Application.objects.create(
            name=name, user=None, client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS, client_secret=secret,
        )
        binding = ClientBinding.objects.create(
            application=application, research_project=project, clinic=site, dicom_raw=dicom_raw, issued_by=user)
        _record(EVENT_TYPE_API_CLIENT_ISSUED, binding, user, request, clinic_id=_pk_text(site))
        if dicom_raw:
            _record(EVENT_TYPE_DICOM_RAW_GRANTED, binding, user, request)
    return IssuedSecret(binding, secret)


def _update_client(binding, user, request, site, dicom_raw) -> ClientBinding:
    _require_project_site(binding.research_project, site)
    with transaction.atomic():
        binding = ClientBinding.objects.select_for_update().select_related("application").get(pk=binding.pk)
        site_changed = binding.clinic_id != _pk(site)
        raw_changed = binding.dicom_raw != dicom_raw
        binding.clinic, binding.dicom_raw = site, dicom_raw
        binding.save(update_fields=["clinic", "dicom_raw"])
        if site_changed:
            _record(EVENT_TYPE_API_CLIENT_UPDATED, binding, user, request, clinic_id=_pk_text(site))
        if raw_changed:
            _record(EVENT_TYPE_DICOM_RAW_GRANTED if dicom_raw else EVENT_TYPE_DICOM_RAW_REVOKED, binding, user, request)
    return binding


def _rotate_client_secret(binding, user, request) -> IssuedSecret:
    secret = generate_client_secret()
    with transaction.atomic():
        application = binding.application
        application.client_secret = secret
        application.save(update_fields=["client_secret", "updated"])
        AccessToken.objects.filter(application=application).delete()
        _record(EVENT_TYPE_API_CLIENT_SECRET_ROTATED, binding, user, request)
    return IssuedSecret(binding, secret)


def _revoke_client(binding, user, request) -> None:
    with transaction.atomic():
        _record(EVENT_TYPE_API_CLIENT_REVOKED, binding, user, request)
        if binding.dicom_raw:
            _record(EVENT_TYPE_DICOM_RAW_REVOKED, binding, user, request)
        # Tokens and the binding cascade with the Application.
        binding.application.delete()


def _require_project_site(project, site) -> None:
    if site is not None and not ResearchProjectClinicMap.objects.filter(project=project, clinic=site).exists():
        raise ClientBindingError("That Site is not one of this project's Sites.")


def _pk(site):
    """The Site's primary key; None for all Sites."""
    return site.pk if site is not None else None


def _pk_text(site) -> str | None:
    """`_pk` as text, for audit metadata (JSON)."""
    return str(site.pk) if site is not None else None


def _record(event_type, binding, user, request, **extra) -> None:
    AuditLog.objects.record(
        event_type, user=user, request=request, project=binding.research_project,
        metadata={
            "client_binding_id": str(binding.pk),
            "client_id": binding.application.client_id,
            "application_id": binding.application.pk,
            **extra,
        },
    )
