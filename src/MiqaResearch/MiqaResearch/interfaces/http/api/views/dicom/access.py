"""Who is calling WADO, and which DicomFiles they may read (#276, #277).

The WADO router authenticates two caller types (interfaces/http/api/urls.py):

- **Session caller**: a logged-in user, i.e. the browser viewer. Gets `/metadata`
  and `/frames` only; the raw-bytes endpoints answer 403. Participant
  Visibility is checked on every request, inside the query that loads the
  DicomFile (no memo); an invisible participant's files look like missing ones (404).
- **Client caller**: an OAuth2 client-credentials token (ADR 0027). Its Client
  Binding scopes it to one Research Project (and optionally one Site), checked
  the same way: every request, inside the same query. An unbound client gets
  404 everywhere. The raw-bytes endpoints also need `dicom:raw` both carried by
  the token and currently granted on the binding (403 otherwise). Each client
  access is audited once per client, series and access token; a session's once per series and
  viewer open, on the series `/metadata` (`audit_access`, actions/image_access_audit.py).

Blinded Annotation (#288, `readers/blinding.py`) narrows both in the same query: sessions see only
their own Annotation/Segmentation series (plus revealed participants), clients none (404 alike).
"""
from dataclasses import dataclass
from functools import wraps

from django.db.models import Exists, OuterRef, QuerySet
from django.http import HttpResponse

from contract.constants.scopes import SCOPE_DICOM_RAW
from MiqaResearch.actions.image_access_audit import audit_client_access, audit_viewer_series_open
from MiqaResearch.data.models import ClientBinding
from MiqaResearch.data.models.dicom_file import DicomFile
from MiqaResearch.readers.blinding import unblinded_files_for_client, unblinded_files_for_user, viewer_reveals
from MiqaResearch.readers.participant_visibility import (
    participants_visible_to_client,
    visible_participants_in_any_project,
)

# Raw files carry full PHI: never kept by any cache.
RAW_CACHE_CONTROL = "private, no-store"


@dataclass(frozen=True)
class SessionCaller:
    user: object


@dataclass(frozen=True)
class ClientCaller:
    application: object


def caller_of(request) -> SessionCaller | ClientCaller:
    """The authenticated caller; `ClientCredentialsAuth` sets `request.application`, `SessionAuth` doesn't."""
    application = getattr(request, "application", None)
    if application is not None:
        return ClientCaller(application)
    return SessionCaller(request.auth)


def readable_files(request, files: QuerySet[DicomFile]) -> QuerySet[DicomFile]:
    """`files` narrowed to what the caller may read (visibility and blinding); adds no query of its own."""
    match caller_of(request):
        case SessionCaller(user):
            visible = visible_participants_in_any_project(user)
            files = unblinded_files_for_user(user, viewer_reveals(request), files)
        case ClientCaller(application):
            visible = participants_visible_to_client(application)
            files = unblinded_files_for_client(files)
    return files.filter(Exists(visible.filter(pk=OuterRef("series__study__study_participant"))))


def not_for_sessions(view):
    """Endpoints outside the viewer surface (series `/metadata` and `/frames`, #271): 403 for session callers."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if isinstance(caller_of(request), SessionCaller):
            return HttpResponse("Not available to browser sessions", status=403)
        return view(request, *args, **kwargs)

    return wrapper


def machine_only(view):
    """Raw-bytes endpoints: 403 for session callers (the viewer never needs the stored file). Clients
    need a binding (404 without) and `dicom:raw` on both the token and the binding (403 otherwise)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        match caller_of(request):
            case SessionCaller():
                return HttpResponse("Raw DICOM retrieval is not available to browser sessions", status=403)
            case ClientCaller(application):
                binding = ClientBinding.objects.filter(application=application).only("dicom_raw").first()
                if binding is None:
                    return HttpResponse(status=404)
                if not (binding.dicom_raw and SCOPE_DICOM_RAW in request.access_token.scope.split()):
                    return HttpResponse("Raw DICOM retrieval needs the dicom:raw scope", status=403)
                response = view(request, *args, **kwargs)
                response["Cache-Control"] = RAW_CACHE_CONTROL
                return response

    return wrapper


def audit_access(request, dicom_files, *, series_open: bool = False) -> None:
    """Audit a successful read (actions/image_access_audit.py): every client read; a session caller's
    only when it opens a series (`series_open`: the series `/metadata`), never per frame."""
    match caller_of(request):
        case ClientCaller(application):
            audit_client_access(request, application, dicom_files)
        case SessionCaller(user) if series_open:
            audit_viewer_series_open(request, user, dicom_files)
