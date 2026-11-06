from uuid import uuid7

from django.db import models

from .concept import Concept
from .etl_job import EtlJob
from .study_participant import StudyParticipant


class VisitOccurrence(models.Model):
    """
    Represents a visit or encounter in the OMOP Common Data Model v5.4.
    The VISIT_OCCURRENCE table contains the spans of time a Person continuously receives medical services.
    """
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    # Linked to PERSON table (StudyParticipant)
    person = models.ForeignKey(
        StudyParticipant,
        on_delete=models.CASCADE,
        related_name="visits",
        help_text="The person for whom the visit is recorded."
    )
    # The type of visit (Inpatient, Outpatient, etc.)
    visit_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_occurrences",
        help_text="A foreign key that refers to a visit Concept identifier in the Standardized Vocabularies."
    )
    visit_start_date = models.DateField(help_text="The start date of the visit.")
    visit_start_datetime = models.DateTimeField(null=True, blank=True, help_text="The date and time of the visit started.")
    visit_end_date = models.DateField(help_text="The end date of the visit.")
    visit_end_datetime = models.DateTimeField(null=True, blank=True, help_text="The date and time of the visit ended.")
    # The source data from which the visit record is derived
    visit_type_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_type_occurrences",
        help_text="The type of source data from which the visit record is derived."
    )
    # provider_id and care_site_id are omitted as they might require additional models
    visit_source_value = models.CharField(max_length=50, blank=True, null=True, help_text="The source code for the visit as it appears in the source data.")
    visit_source_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_source_concepts",
        help_text="A foreign key to a Concept that refers to the code used in the source data."
    )
    # v5.4 additions/renames
    admitted_from_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admitted_from_visits",
        help_text="A foreign key that refers to the admitted from Concept identifier."
    )
    admitted_from_source_value = models.CharField(max_length=50, blank=True, null=True, help_text="The source code for the admitted from as it appears in the source data.")
    discharged_to_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discharged_to_visits",
        help_text="A foreign key that refers to the discharged to Concept identifier."
    )
    discharged_to_source_value = models.CharField(max_length=50, blank=True, null=True, help_text="The source code for the discharged to as it appears in the source data.")
    preceding_visit_occurrence = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_visits",
        help_text="A foreign key to the VISIT_OCCURRENCE table of the visit immediately preceding this visit."
    )

    # Extension: ETL provenance (#144). Nulled, never cascaded, on EtlJob
    # deletion -- a Job is disposable history; the row it produced is not.
    etl_job = models.ForeignKey(
        EtlJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_occurrences",
        help_text="The EtlJob that loaded this row, if it was loaded by the ETL framework."
    )

    class Meta:
        db_table = "mires_visit_occurrence"
        verbose_name = "Visit Occurrence"
        verbose_name_plural = "Visit Occurrences"

    def __str__(self):
        return f"Visit {self.id} for {self.person} ({self.visit_start_date})"
