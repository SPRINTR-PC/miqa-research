"""Concept-reference validation shared by ETL Datatype loaders (#159).

A row's Concept references are `Concept.concept_id` UUIDs a Script names directly -- mapping a
source system's own code to a Concept is the Script's job, not this loader's. A UUID that
matches no Concept is exactly as "unresolvable" as a Participant Reference with no match: it
fails the whole batch with a clear error up front, rather than writing a dangling FK and hoping
the database notices.
"""
from uuid import UUID

from MiqaResearch.data.models import Concept

from .exceptions import EtlRowError


def require_existing_concepts(concept_ids: set[UUID | None]) -> None:
    wanted = {concept_id for concept_id in concept_ids if concept_id is not None}
    if not wanted:
        return
    existing = set(Concept.objects.filter(concept_id__in=wanted).values_list("concept_id", flat=True))
    missing = wanted - existing
    if missing:
        raise EtlRowError(f"Unknown Concept id(s): {sorted(str(concept_id) for concept_id in missing)}")
