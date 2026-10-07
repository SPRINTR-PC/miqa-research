"""Read Annotations and Segmentations of a participant as version chains (ADR 0026, #287)."""
from collections import defaultdict

from MiqaResearch.data.models import DerivedObjectProvenance, StudyParticipant
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.blinding import ParticipantBlinding
from MiqaResearch.readers.participant_visibility import visible_participants


class ParticipantNotVisible(Exception):
    """Unknown participant, or outside the caller's Participant Visibility."""


def version_item(provenance: DerivedObjectProvenance) -> dict:
    """One version as the API shows it."""
    return {
        "id": provenance.pk,
        "chain_id": provenance.chain_id,
        "kind": provenance.kind,
        "source": provenance.source,
        "version": provenance.version,
        "series_instance_uid": provenance.series.series_instance_uid,
        "series_description": provenance.series.series_description,
        "author": provenance.author.username if provenance.author_id else None,
        "created_at": provenance.created_at,
        "retired": provenance.retired,
        "source_series_uids": sorted(series.series_instance_uid for series in provenance.source_series.all()),
    }


def chain_item(head: DerivedObjectProvenance, history: list[DerivedObjectProvenance], can_change: bool) -> dict:
    """A chain: its head's fields, the full version history (oldest first) and the caller's right to change it."""
    return {**version_item(head), "can_change": can_change, "history": [version_item(item) for item in history]}


def list_participant_objects(user, participant_id, series_instance_uid: str | None = None,
                             include_retired: bool = False, session=None) -> list[dict]:
    """Chains of the participant's Annotations and Segmentations, newest chain first.

    `series_instance_uid` keeps only chains whose head was made on that source series. Retired
    chains are listed only with `include_retired`, and only those the caller may retire. Under
    Blinded Annotation (#288) a chain is listed only if its head is the caller's, with only the
    caller's versions in its history, unless `session` holds a Blinding Reveal for the participant.
    """
    participant, project = visible_participant(user, participant_id)
    rights = ParticipantRights(user, project, participant)
    blinding = ParticipantBlinding(user, project, participant, session)

    result = []
    for history in _chains(participant):
        head = history[-1]
        if blinding.hides(head.author_id):
            continue
        can_change = rights.can_change(head.author_id)
        if head.retired and not (include_retired and can_change):
            continue
        if series_instance_uid and series_instance_uid not in {s.series_instance_uid for s in head.source_series.all()}:
            continue
        shown = [item for item in history if not blinding.hides(item.author_id)]
        result.append(chain_item(head, shown, can_change))
    result.sort(key=lambda item: item["created_at"], reverse=True)
    return result


def participant_blinding_status(user, participant_id, session=None) -> dict:
    """Blinded Annotation state of one participant for the caller: on/off, whether this session revealed
    it, whether the caller may reveal, and how many current (not retired) chains are hidden."""
    participant, project = visible_participant(user, participant_id)
    blinding = ParticipantBlinding(user, project, participant, session)
    hidden = sum(
        1 for history in _chains(participant) if not history[-1].retired and blinding.hides(history[-1].author_id)
    )
    return {
        "blinded": blinding.blinded,
        "revealed": blinding.revealed,
        "can_reveal": blinding.can_reveal,
        "hidden": hidden,
    }


def visible_participant(user, participant_id):
    participant = (
        StudyParticipant.objects.select_related("research_project").filter(pk=participant_id).first()
    )
    if participant is None or participant.research_project is None:
        raise ParticipantNotVisible()
    project = participant.research_project
    if not visible_participants(user, project).filter(pk=participant.pk).exists():
        raise ParticipantNotVisible()
    return participant, project


def _chains(participant) -> list[list[DerivedObjectProvenance]]:
    """The participant's version chains, each oldest version first."""
    versions = (
        DerivedObjectProvenance.objects.filter(series__study__study_participant=participant)
        .select_related("series", "author")
        .prefetch_related("source_series")
        .order_by("chain_id", "version")
    )
    chains: dict = defaultdict(list)
    for provenance in versions:
        chains[provenance.chain_id].append(provenance)
    return list(chains.values())
