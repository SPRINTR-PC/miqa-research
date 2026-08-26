from uuid import uuid7
from django.db import models
from .study_participant import StudyParticipant
from .concept import Concept
from .visit_occurrence import VisitOccurrence
from .dicom_series import DicomSeries


class Measurement(models.Model):
    """
    Represents the MEASUREMENT table in the OMOP Common Data Model v5.4.
    The MEASUREMENT table contains records of Measurements, i.e. structured values
    (numerical or categorical) obtained through systematic and standardized examination
    or testing of a Person.
    """
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    person = models.ForeignKey(
        StudyParticipant,
        on_delete=models.CASCADE,
        related_name="measurements",
        help_text="A foreign key identifier to the Person about whom the measurement was recorded."
    )
    measurement_concept = models.ForeignKey(
        Concept,
        on_delete=models.CASCADE,
        related_name="measurements",
        help_text="A foreign key to the standard measurement concept identifier."
    )
    measurement_date = models.DateField(help_text="The date of the Measurement.")
    measurement_datetime = models.DateTimeField(null=True, blank=True, help_text="The date and time of the Measurement.")
    measurement_type_concept = models.ForeignKey(
        Concept,
        on_delete=models.CASCADE,
        related_name="measurement_types",
        help_text="The provenance from where the Measurement record was recorded."
    )
    operator_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurement_operators",
        help_text="The mathematical operator applied to the value_as_number (e.g., <, =, >)."
    )
    value_as_number = models.FloatField(null=True, blank=True, help_text="The numerical value of the Measurement result.")
    value_as_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurement_value_concepts",
        help_text="The Concept representing the categorical result of the Measurement."
    )
    unit_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurement_units",
        help_text="The Concept representing the unit of the Measurement."
    )
    range_low = models.FloatField(null=True, blank=True, help_text="The lower limit of the normal range.")
    range_high = models.FloatField(null=True, blank=True, help_text="The upper limit of the normal range.")
    # provider_id omitted as per previous model patterns
    visit_occurrence = models.ForeignKey(
        VisitOccurrence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurements",
        help_text="The Visit during which the Measurement was recorded."
    )
    # visit_detail_id omitted
    measurement_source_value = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="The Measurement name as it appears in the source data."
    )
    measurement_source_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurement_source_concepts",
        help_text="The Concept used in the source data."
    )
    unit_source_value = models.CharField(max_length=50, blank=True, null=True, help_text="The source value for the unit.")
    unit_source_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unit_source_concepts",
        help_text="The Concept representing the unit in the source data."
    )
    value_source_value = models.CharField(max_length=50, blank=True, null=True, help_text="The source value for the measurement result.")
    measurement_event_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="The identifier of the event (e.g. DicomSeries) that this measurement is related to."
    )
    meas_event_field_concept = models.ForeignKey(
        Concept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meas_event_fields",
        help_text="The Concept representing the field in the event table (e.g. Image_Occurrence) that this measurement is related to."
    )

    # Extension: Linking to DicomSeries (Image_Occurrence)
    dicom_series = models.ForeignKey(
        DicomSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurements",
        help_text="Link to the DicomSeries (Image Occurrence) this measurement was derived from."
    )

    class Meta:
        db_table = "mires_measurement"
        verbose_name = "Measurement"
        verbose_name_plural = "Measurements"

    def __str__(self):
        return f"Measurement {self.measurement_concept} for {self.person}: {self.value_as_number or self.value_as_concept}"
