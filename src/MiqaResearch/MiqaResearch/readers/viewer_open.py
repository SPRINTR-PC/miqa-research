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
from MiqaResearch.data.models import DicomSeries, StudyParticipant
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants_in_any_project


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
    rows = _rows(DicomSeries.objects.filter(study__study_participant=participant))
    if not requested or any(uid not in rows for uid in requested):
        raise ViewerOpenNotFound()
    return _open(user, participant, rows, requested, list(rows))


def dev_viewer_open(user, open_uids: list[str], related_uids: list[str]) -> ViewerOpen:
    """The dev page's open: `open_uids`, then `related_uids`, each in order; any the user can't see, in
    whatever project, is left out (the dev page names series of any participant). The participant is the
    first opened series'."""
    visible = DicomSeries.objects.filter(
        Exists(visible_participants_in_any_project(user).filter(pk=OuterRef("study__study_participant")))
    )
    rows = _rows(visible.filter(series_instance_uid__in=[*open_uids, *related_uids]))
    opened = list(dict.fromkeys(uid for uid in open_uids if uid in rows))
    if not opened:
        return ViewerOpen(participant=None, series=[], can_annotate=False)
    participant = StudyParticipant.objects.get(dicomstudy__dicomseries__series_instance_uid=opened[0])
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
