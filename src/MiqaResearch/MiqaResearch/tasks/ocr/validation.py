"""Thin wrapper around kpforms' private submission validator.

Deliberately bypasses kpforms.helpers.submit_form_data: it raises on any
empty required=True field and takes an int template_id against this
project's UUID pk (see #11). PROM_1_PRO_GI_GU_SWE's fields are all
required=False specifically so OCR's partial output is never an error here.
"""

from kpforms.form_schema import FormSubmissionSchema, FormTemplateSchema
from kpforms.helpers import _validate_form_submission_against_template


def validate_submission(data: list[dict], template_schema: FormTemplateSchema) -> tuple[list[dict], list[str]]:
    """Validates OCR output against the template, computing tolerance violations.

    Returns (validated data entries, fieldIds out of tolerance).
    """
    submission = FormSubmissionSchema(data=data)
    validated, _is_valid = _validate_form_submission_against_template(submission, template_schema)
    return [entry.model_dump(mode="json") for entry in validated.data], list(validated.fieldsOutOfTolerance or [])
