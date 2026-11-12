"""`dicom_instance` ETL Datatype (#418, spec #411): thin loader over `actions/dicom_ingest`.

Binding config (the Config Schema sidecar of the native Script validates it): `identifiers`
(`tags`, `match_person_source_value`) and `duplicate_handling` (`inherit | skip | update`).
Raw Retention defaults to "delete": the originals are verified in storage before the Job succeeds.
"""
from contract.constants.etl import PIPELINE_BINDING_RAW_RETENTION_DELETE
from MiqaResearch.data.models import ResearchProject
from mires_etl.schemas.dicom_instance import DicomInstanceRowSchema

from .registry import LoadResult, register_loader


@register_loader("dicom_instance", default_raw_retention=PIPELINE_BINDING_RAW_RETENTION_DELETE)
def load_dicom_instance_rows(
        *, project: ResearchProject, etl_job, rows: list[DicomInstanceRowSchema], inputs) -> LoadResult:
    # deferred: actions.dicom_ingest.load imports this package's exceptions and registry
    from MiqaResearch.actions.dicom_ingest.load import load_dicom_instances

    return load_dicom_instances(project=project, etl_job=etl_job, rows=rows, inputs=inputs)
