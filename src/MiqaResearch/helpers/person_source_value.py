from collections import defaultdict

from helpers.db_fields import get_deterministic_hash


def format_person_source_value(raw: str) -> str:
    """The one stored/hashed form of a person identifier (personnummer): trimmed, dashes removed.
    Consent loads and DICOM ingestion both use it, so either path matches a participant the other
    created (#241). The native consent script applies the same rule itself (it is stdlib-only)."""
    return raw.strip().replace("-", "")


class PersonSourceValueCollision(Exception):
    """Formatting would give two Study Participants of one project the same identifier."""


def reformat_stored_person_source_values(study_participant_model) -> int:
    """Rewrites every stored `person_source_value` (and its hash) into the shared format. Takes the
    model class so migration 0026 can pass its historical model. Checks every project for collisions
    before writing anything; on one, raises naming the participants by alias1 only, so they can be
    merged by hand first. Returns how many participants changed."""
    by_project_and_value = defaultdict(list)
    changed = []
    for participant in study_participant_model.objects.exclude(person_source_value__isnull=True).iterator():
        if not participant.person_source_value:
            continue
        formatted = format_person_source_value(participant.person_source_value)
        by_project_and_value[(participant.research_project_id, formatted)].append(participant.alias1)
        if formatted != participant.person_source_value:
            participant.person_source_value = formatted
            participant.person_source_value_hash = get_deterministic_hash(formatted)
            changed.append(participant)

    collisions = [sorted(aliases) for aliases in by_project_and_value.values() if len(aliases) > 1]
    if collisions:
        listed = "; ".join(", ".join(aliases) for aliases in sorted(collisions))
        raise PersonSourceValueCollision(
            f"Formatting person identifiers would merge these participants (alias1, per project): {listed}. "
            "Merge them by hand, then migrate again.")

    for participant in changed:
        participant.save(update_fields=["person_source_value", "person_source_value_hash"])
    return len(changed)
