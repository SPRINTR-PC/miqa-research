"""Refusals raised by the viewer's actions (annotations.py, blinding.py); the viewer API maps them to
status codes in one place (interfaces/http/api/views/viewer/errors.py)."""


class ViewerActionError(Exception):
    """Base for a refusal; anything not more specific below is a 400 with the message."""


class NotFound(ViewerActionError):
    """Unknown, or not within the caller's Participant Visibility (never distinguished)."""


class NotAllowed(ViewerActionError):
    """Visible, but the caller's roles don't allow it."""
