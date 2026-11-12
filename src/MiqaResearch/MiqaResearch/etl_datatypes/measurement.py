"""`measurement` ETL Datatype (#159): natural-key upsert into Measurement, OMOP CDM v5.4.

Natural key: (person, measurement_concept, measurement_date, measurement_source_value). Neither
the model nor the DB enforces this combination as unique -- it's the loader's own contract with
Script authors, chosen as the one thing a source system reliably repeats across re-exports of the
same measurement (unlike the row's own DB id, which a Script never sees). Re-running the same
batch must upsert in place rather than duplicate (#159).
"""
from MiqaResearch.data.models import Measurement, ResearchProject
from mires_etl.schemas.measurement import MeasurementRowSchema

from .concepts import require_existing_concepts
from .participant_reference import resolve_participant
from .registry import LoadResult, register_loader


@register_loader("measurement")
def load_measurement_rows(*, project: ResearchProject, etl_job, rows: list[MeasurementRowSchema]) -> LoadResult:
    require_existing_concepts({
        concept_id
        for row in rows
        for concept_id in (
            row.measurement_concept_id, row.measurement_type_concept_id, row.operator_concept_id,
            row.value_as_concept_id, row.unit_concept_id,
        )
    })

    created = updated = 0
    for row in rows:
        participant = resolve_participant(project, row)
        _, was_created = Measurement.objects.update_or_create(
            person=participant,
            measurement_concept_id=row.measurement_concept_id,
            measurement_date=row.measurement_date,
            measurement_source_value=row.measurement_source_value,
            defaults={
                "measurement_type_concept_id": row.measurement_type_concept_id,
                "measurement_datetime": row.measurement_datetime,
                "operator_concept_id": row.operator_concept_id,
                "value_as_number": row.value_as_number,
                "value_as_concept_id": row.value_as_concept_id,
                "unit_concept_id": row.unit_concept_id,
                "unit_source_value": row.unit_source_value,
                "value_source_value": row.value_source_value,
                "range_low": row.range_low,
                "range_high": row.range_high,
                "etl_job": etl_job,
            },
        )
        created += was_created
        updated += not was_created
    return LoadResult(created=created, updated=updated)
