"""Blinded Annotation and Blinding Reveal (ADR 0026, #288): which Annotations and Segmentations a caller sees.

While a Research Project's `blinded_annotation` flag is on:
- every user (PI and Admin included) sees only Annotation/Segmentation series they authored; ingested
  ones (no author) and others' are hidden, in the viewer API and on WADO;
- a PI, Site PI (its Sites) or Admin may make a Blinding Reveal for one participant. It lives in the
  login session (`request.session`, gone on logout) and counts only while the revealer still holds
  such a role for that participant (checked on every request, like Participant Visibility);
- bound machine clients get no Annotation/Segmentation series at all.

What counts as an Annotation/Segmentation series is the Data Kind split by modality (SR/ANN, SEG/RTSTRUCT).
Aggregate counts (Data Kind totals) are not filtered.
"""
from django.db.models import Exists, OuterRef, QuerySet

from contract.constants.annotation import DERIVED_MODALITIES
from MiqaResearch.data.models import DicomFile, DicomSeries
from MiqaResearch.readers.annotation_permissions import OVERSEER_ROLES
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants_in_any_project

REVEAL_SESSION_KEY = "blinding_reveals"


def revealed_participant_ids(session) -> list[str]:
    """Participant ids this login session made a Blinding Reveal for (unchecked against roles)."""
    if session is None:
        return []
    return list(session.get(REVEAL_SESSION_KEY, []))


def remember_reveal(session, participant_id) -> None:
    revealed = revealed_participant_ids(session)
    if str(participant_id) not in revealed:
        session[REVEAL_SESSION_KEY] = [*revealed, str(participant_id)]


def can_reveal(user, project, participant) -> bool:
    """PI, Site PI (its Sites) and Admin may reveal; so may a superuser. Annotators never."""
    return can_see_participant(user, project, participant, OVERSEER_ROLES)


class ParticipantBlinding:
    """What Blinded Annotation hides from one user on one participant (a few queries, then pure)."""

    def __init__(self, user, project, participant, session):
        self.user_id = user.pk
        self.blinded = bool(project.blinded_annotation)
        self.can_reveal = self.blinded and can_reveal(user, project, participant)
        self.revealed = self.can_reveal and str(participant.pk) in revealed_participant_ids(session)

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


def unblinded_files_for_user(user, session, files: QuerySet[DicomFile]) -> QuerySet[DicomFile]:
    """`files` without others' (and ingested) Annotation/Segmentation series of blinded projects,
    except for participants this session revealed while the user may still reveal them. No query of its own."""
    hidden = _hidden_series().exclude(provenance__author=user.pk)
    revealed_ids = revealed_participant_ids(session)
    if revealed_ids:
        revealed = visible_participants_in_any_project(user, OVERSEER_ROLES).filter(pk__in=revealed_ids)
        hidden = hidden.exclude(study__study_participant__in=revealed)
    return files.filter(~Exists(hidden))


def unblinded_files_for_client(files: QuerySet[DicomFile]) -> QuerySet[DicomFile]:
    """`files` without any Annotation/Segmentation series of blinded projects (machine clients)."""
    return files.filter(~Exists(_hidden_series()))
