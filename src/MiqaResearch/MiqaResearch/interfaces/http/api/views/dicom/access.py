"""Who is calling WADO, and which DicomFiles they may read (#276).

The WADO router authenticates two caller types (interfaces/http/api/urls.py):

- **Session caller**: a logged-in user, i.e. the browser viewer. Gets `/metadata`
  and `/frames` only; the raw-bytes endpoints answer 403. Participant
  Visibility is checked on every request, inside the query that loads the
  DicomFile (no memo); an invisible participant's files look like missing ones (404).
- **Client caller**: an OAuth2 client-credentials token. Today it reads every
  file; the Client Binding (#277) scopes it to its Research Project / Site and
  gates the raw endpoints on `dicom:raw`. Both branch points below are the seams.
"""
from dataclasses import dataclass
from functools import wraps

from django.db.models import Exists, OuterRef, QuerySet
from django.http import HttpResponse

from MiqaResearch.data.models.dicom_file import DicomFile
from MiqaResearch.readers.participant_visibility import visible_participants_in_any_project


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
    """`files` narrowed to what the caller may read; adds no query of its own."""
    match caller_of(request):
        case SessionCaller(user):
            visible = visible_participants_in_any_project(user).filter(
                pk=OuterRef("series__study__study_participant")
            )
            return files.filter(Exists(visible))
        case ClientCaller():
            # #277: filter by the Client Binding's Research Project (+ Site) here.
            return files


def machine_only(view):
    """Raw-bytes endpoints: 403 for session callers (the viewer never needs the stored file)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        match caller_of(request):
            case SessionCaller():
                return HttpResponse("Raw DICOM retrieval is not available to browser sessions", status=403)
            case ClientCaller():
                # #277: require the `dicom:raw` scope here.
                return view(request, *args, **kwargs)

    return wrapper
