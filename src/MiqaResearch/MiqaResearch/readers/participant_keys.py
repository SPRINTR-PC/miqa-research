"""Reads on Participant Keys (ADR 0035)."""
from MiqaResearch.data.models import ParticipantKey


def participant_alias_of(key: ParticipantKey) -> str:
    """The pseudonym shown in de-identified output for the key's data: the Study Participant's `alias1`
    when linked, else a stable one from the key's id (nothing else is pseudonymous yet)."""
    participant = key.study_participant
    return participant.alias1 if participant is not None else f"UNLINKED-{key.pk.hex[:12]}"
