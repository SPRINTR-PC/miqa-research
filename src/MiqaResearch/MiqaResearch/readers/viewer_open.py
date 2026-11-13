"""What a viewer open shows (#279, entry contract decided in #184).

The page names the series to open; the viewer also offers the participant's Related Series (every other
image series of the Study Participant, from any of its studies). Both are limited by Participant
Visibility. Annotation and Segmentation series (SR/ANN, SEG/RTSTRUCT) are never in the list: they are
results, shown on their source series by the viewer's results tree. A requested series the user can't see,
that isn't this participant's, or that isn't an image series, makes the whole open fail as not found:
unseen looks like nonexistent.

The DEBUG dev page builds the same open from raw UIDs (`dev_viewer_open`), so both pages hand the viewer
one shape.
"""
from dataclasses import dataclass
from typing import TypedDict

from django.db.models import Count, Exists, OuterRef, QuerySet

from contract.constants.annotation import DERIVED_MODALITIES
from MiqaResearch.data.models import DicomSeries, ParticipantKey, StudyParticipant
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.participant_keys import participant_alias_of
from MiqaResearch.readers.participant_visibility import (
    can_open_unlinked,
    can_see_participant,
    visible_participants_in_any_project,
)


class SeriesEntry(TypedDict):
    """One series of the viewer's series list, as the page hands it over (JSON)."""

    study: str
    series: str
    modality: str
    description: str
    instances: int
    frame_of_reference: str | None
    open: bool


@dataclass(frozen=True)
class ViewerOpen:
    """One viewer open: on whose data, the series list, and whether the user may annotate."""

    participant: StudyParticipant | None
    series: list[SeriesEntry]
    can_annotate: bool
    participant_key: ParticipantKey | None = None  # set on an unlinked open (#416), where participant is None

    @property
    def project_id(self):
        return self.participant.research_project_id if self.participant else self.participant_key.project_id

    @property
    def alias(self) -> str:
        return self.participant.alias1 if self.participant else participant_alias_of(self.participant_key)

    @property
    def opened_uids(self) -> list[str]:
        return [entry["series"] for entry in self.series if entry["open"]]


class ViewerOpenNotFound(Exception):
    """Unknown or invisible participant, or a requested series the user can't see on it."""


def viewer_open(user, project_id, participant_id, requested_uids: list[str]) -> ViewerOpen:
    """The open of `requested_uids` (first = base) on a participant of `project_id`, if `user` may see all of it:
    the requested series (`open`, in request order), then the Related Series."""
    participant = StudyParticipant.objects.filter(pk=participant_id, research_project_id=project_id).first()
    if participant is None or not can_see_participant(user, project_id, participant):
        raise ViewerOpenNotFound()
    requested = list(dict.fromkeys(uid for uid in requested_uids if uid))
    rows = _rows(DicomSeries.objects.filter(study__participant_key__study_participant=participant))
    if not requested or any(uid not in rows for uid in requested):
        raise ViewerOpenNotFound()
    return _open(user, participant, rows, requested, list(rows))


def unlinked_viewer_open(user, project_id, key_id, requested_uids: list[str]) -> ViewerOpen:
    """The open of `requested_uids` on the still unlinked Participant Key `key_id` (ADR 0035, #416): only for
    who may open unlinked Studies of the project. Related Series are the key's own; nothing is annotatable."""
    key = ParticipantKey.objects.filter(pk=key_id, project_id=project_id, study_participant__isnull=True).first()
    if key is None or not can_open_unlinked(user, project_id):
        raise ViewerOpenNotFound()
    requested = list(dict.fromkeys(uid for uid in requested_uids if uid))
    rows = _rows(DicomSeries.objects.filter(study__participant_key=key))
    if not requested or any(uid not in rows for uid in requested):
        raise ViewerOpenNotFound()
    order = [*requested, *(uid for uid in rows if uid not in requested)]
    listed = [{**rows[uid], "open": uid in requested} for uid in order]
    return ViewerOpen(participant=None, series=listed, can_annotate=False, participant_key=key)


def dev_viewer_open(user, open_uids: list[str], related_uids: list[str]) -> ViewerOpen:
    """The dev page's open: `open_uids`, then `related_uids`, each in order; any the user can't see, in
    whatever project, is left out (the dev page names series of any participant). The participant is the
    first opened series'."""
    visible = DicomSeries.objects.filter(
        Exists(visible_participants_in_any_project(user).filter(pk=OuterRef("study__participant_key__study_participant")))
    )
    rows = _rows(visible.filter(series_instance_uid__in=[*open_uids, *related_uids]))
    opened = list(dict.fromkeys(uid for uid in open_uids if uid in rows))
    if not opened:
        return ViewerOpen(participant=None, series=[], can_annotate=False)
    participant = StudyParticipant.objects.get(
        participant_keys__dicomstudy__dicomseries__series_instance_uid=opened[0]
    )
    return _open(user, participant, rows, opened, [uid for uid in related_uids if uid in rows])


def _open(user, participant, rows: dict[str, SeriesEntry], opened: list[str], related: list[str]) -> ViewerOpen:
    listed = [{**rows[uid], "open": True} for uid in opened]
    listed += [{**rows[uid], "open": False} for uid in dict.fromkeys(related) if uid not in opened]
    can_annotate = ParticipantRights(user, participant.research_project_id, participant).can_author
    return ViewerOpen(participant=participant, series=listed, can_annotate=can_annotate)


def _rows(series: QuerySet[DicomSeries]) -> dict[str, SeriesEntry]:
    """Image series UID → its series list entry (not yet marked open)."""
    return {
        row.series_instance_uid: _entry(row)
        for row in series.exclude(modality__in=DERIVED_MODALITIES)
        .select_related("study")
        .annotate(instances=Count("dicomfile"))
        .order_by("-study__study_datetime", "series_description", "series_instance_uid")
    }


def _entry(series: DicomSeries) -> SeriesEntry:
    return SeriesEntry(
        study=series.study.study_instance_uid,
        series=series.series_instance_uid,
        modality=series.modality or "",
        description=series.series_description or "",
        instances=series.instances,
        frame_of_reference=series.frame_of_reference_uid,
        open=False,
    )
