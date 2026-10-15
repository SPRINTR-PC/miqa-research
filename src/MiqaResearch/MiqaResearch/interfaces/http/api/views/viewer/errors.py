"""Viewer API error body and the status code of each viewer action refusal (actions/viewer_exceptions.py)."""
from ninja import Schema
from ninja.errors import HttpError

from MiqaResearch.actions.viewer_exceptions import NotAllowed, NotFound, ViewerActionError


class ErrorOut(Schema):
    detail: str


def http_error(error: ViewerActionError) -> HttpError:
    """404 (never says why), 403 with the reason, else 400 with the reason."""
    if isinstance(error, NotFound):
        return HttpError(404, "Not Found")
    if isinstance(error, NotAllowed):
        return HttpError(403, str(error))
    return HttpError(400, str(error))
