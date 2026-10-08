"""Blinded Annotation and Blinding Reveal (ADR 0026, #288): which Annotations and Segmentations a caller sees.

While a Research Project's `blinded_annotation` flag is on:
- every user (PI and Admin included) sees only Annotation/Segmentation series they authored; ingested
  ones (no author) and others' are hidden, in the viewer API and on WADO;
- a PI, Site PI (its Sites) or Admin may make a Blinding Reveal for one participant. It is scoped to one
  viewer open: the viewer sends a per-open Viewer Session id (`X-Mires-Viewer-Session`) on its requests
  and the reveal is kept in the login session under that id (gone on logout, on reload, in other tabs and
  on requests without the header). It counts only in the blinding epoch it was made in (turning the flag
  off and on again ends it) and only while the revealer still holds such a role for that participant
  (checked on every request, like Participant Visibility);
- bound machine clients get no Annotation/Segmentation series at all.

What counts as an Annotation/Segmentation series is the Data Kind split by modality (SR/ANN, SEG/RTSTRUCT).
Aggregate counts (Data Kind totals) are not filtered.
"""
from django.db.models import Exists, OuterRef, Q, QuerySet

from contract.constants.annotation import DERIVED_MODALITIES
from MiqaResearch.data.models import DicomFile, DicomSeries
from MiqaResearch.readers.annotation_permissions import OVERSEER_ROLES
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants_in_any_project

VIEWER_SESSION_HEADER = "X-Mires-Viewer-Session"
REVEAL_SESSION_KEY = "blinding_reveals"
MAX_VIEWER_SESSIONS = 20


def viewer_session_id(request) -> str | None:
    """The per-open Viewer Session id the viewer sends with its requests; None without one."""
    headers = getattr(request, "headers", None)
    value = (headers.get(VIEWER_SESSION_HEADER) or "").strip() if headers is not None else ""
    return value[:64] or None


def viewer_reveals(request) -> dict[str, int]:
    """participant id → blinding epoch of the Blinding Reveals made in this request's Viewer Session
    (unchecked against roles and the projects' current epochs)."""
    session = getattr(request, "session", None)
    viewer = viewer_session_id(request)
    if session is None or viewer is None:
        return {}
    return dict(session.get(REVEAL_SESSION_KEY, {}).get(viewer, {}))


def can_reveal(user, project, participant) -> bool:
    """PI, Site PI (its Sites) and Admin may reveal; so may a superuser. Annotators never."""
    return can_see_participant(user, project, participant, OVERSEER_ROLES)


class ParticipantBlinding:
    """What Blinded Annotation hides from one user on one participant (a few queries, then pure)."""

    def __init__(self, user, project, participant, reveals: dict[str, int]):
        self.user_id = user.pk
        self.blinded = bool(project.blinded_annotation)
        self.can_reveal = self.blinded and can_reveal(user, project, participant)
        self.revealed = self.can_reveal and reveals.get(str(participant.pk)) == project.blinding_epoch

    def hides(self, author_id) -> bool:
        """Whether work authored by `author_id` (None: ingested) is hidden from the user."""
        return self.blinded and not self.revealed and author_id != self.user_id


def _hidden_series() -> QuerySet[DicomSeries]:
    """The outer file's series, if it is an Annotation/Segmentation series of a blinded project."""
    return DicomSeries.objects.filter(
        pk=OuterRef("series"),
        modality__in=DERIVED_MODALITIES,
        study__study_participant__research_project__blinded_annotation=True,
    )


def unblinded_files_for_user(user, reveals: dict[str, int], files: QuerySet[DicomFile]) -> QuerySet[DicomFile]:
    """`files` without others' (and ingested) Annotation/Segmentation series of blinded projects, except for
    participants in `reveals` (current epoch) while the user may still reveal them. No query of its own."""
    hidden = _hidden_series().exclude(provenance__author=user.pk)
    if reveals:
        current = Q()
        for participant_id, epoch in reveals.items():
            current |= Q(pk=participant_id, research_project__blinding_epoch=epoch)
        revealed = visible_participants_in_any_project(user, OVERSEER_ROLES).filter(current)
        hidden = hidden.exclude(study__study_participant__in=revealed)
    return files.filter(~Exists(hidden))


def unblinded_files_for_client(files: QuerySet[DicomFile]) -> QuerySet[DicomFile]:
    """`files` without any Annotation/Segmentation series of blinded projects (machine clients)."""
    return files.filter(~Exists(_hidden_series()))
