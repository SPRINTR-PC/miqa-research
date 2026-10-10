"""What a viewer open shows (#279, entry contract decided in #184).

The page names the series to open; the viewer also offers the participant's Related Series (every other
image series of the Study Participant, from any of its studies). Both are limited by Participant
Visibility. Annotation and Segmentation series (SR/ANN, SEG/RTSTRUCT) are never in the list: they are
results, shown on their source series by the viewer's results tree. A requested series the user can't see,
that isn't this participant's, or that isn't an image series, makes the whole open fail as not found:
unseen looks like nonexistent.

The DEBUG dev page builds the same list from raw UIDs (`dev_viewer_series`), so both pages hand the viewer
one shape.
"""
from django.db.models import Count, Exists, OuterRef, QuerySet

from contract.constants.annotation import DERIVED_MODALITIES
from MiqaResearch.data.models import DicomSeries, StudyParticipant
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants_in_any_project


class ViewerOpenNotFound(Exception):
    """Unknown or invisible participant, or a requested series the user can't see on it."""


def viewer_participant(user, project_id, participant_id) -> StudyParticipant:
    """The Study Participant of `project_id` the viewer opens on, if `user` may see it."""
    participant = StudyParticipant.objects.filter(pk=participant_id, research_project_id=project_id).first()
    if participant is None or not can_see_participant(user, project_id, participant):
        raise ViewerOpenNotFound()
    return participant


def viewer_series(participant: StudyParticipant, requested_uids: list[str]) -> list[dict]:
    """The viewer's series list: the requested series (`open`, in request order), then the Related Series."""
    requested = list(dict.fromkeys(uid for uid in requested_uids if uid))
    if not requested:
        raise ViewerOpenNotFound()
    rows = _rows(DicomSeries.objects.filter(study__study_participant=participant))
    if any(uid not in rows for uid in requested):
        raise ViewerOpenNotFound()
    opened = [{**rows.pop(uid), "open": True} for uid in requested]
    return opened + [{**row, "open": False} for row in rows.values()]


def dev_viewer_series(user, open_uids: list[str], related_uids: list[str]) -> list[dict]:
    """The dev page's series list: `open_uids`, then `related_uids`, each in order; any the user can't see,
    in whatever project, is left out (the dev page names series of any participant)."""
    visible = DicomSeries.objects.filter(
        Exists(visible_participants_in_any_project(user).filter(pk=OuterRef("study__study_participant")))
    )
    rows = _rows(visible.filter(series_instance_uid__in=[*open_uids, *related_uids]))
    opened = list(dict.fromkeys(uid for uid in open_uids if uid in rows))
    related = [uid for uid in dict.fromkeys(related_uids) if uid in rows and uid not in opened]
    return [{**rows[uid], "open": True} for uid in opened] + [{**rows[uid], "open": False} for uid in related]


def _rows(series: QuerySet[DicomSeries]) -> dict[str, dict]:
    """Image series UID → its series list entry."""
    return {
        row.series_instance_uid: _entry(row)
        for row in series.exclude(modality__in=DERIVED_MODALITIES)
        .select_related("study")
        .annotate(instances=Count("dicomfile"))
        .order_by("-study__study_datetime", "series_description", "series_instance_uid")
    }


def _entry(series: DicomSeries) -> dict:
    return {
        "study": series.study.study_instance_uid,
        "series": series.series_instance_uid,
        "modality": series.modality or "",
        "description": series.series_description or "",
        "instances": series.instances,
        "frame_of_reference": series.frame_of_reference_uid,
    }
