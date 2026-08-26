from uuid import uuid7
from django.db import models


class Concept(models.Model):
    """
    Represents a medical procedure concept from the OMOP Standardized Vocabularies.
    This typically maps to entries in the OMOP 'CONCEPT' table where domain_id = 'Procedure'.
    """
    concept_id = models.UUIDField(primary_key=True, default=uuid7, editable=False,
                                  help_text="Unique identifier for the concept (OMOP concept_id)")
    concept_name = models.CharField(max_length=255, help_text="The descriptive name of the procedure (e.g., 'CT Head')")
    domain_id = models.CharField(max_length=20, default="Procedure", help_text="The domain this concept belongs to")
    vocabulary_id = models.CharField(max_length=20, help_text="The source vocabulary (e.g., 'SNOMED', 'LOINC', 'CPT4')")
    concept_class_id = models.CharField(max_length=20, help_text="The category of the concept (e.g., 'Procedure')")
    standard_concept = models.CharField(max_length=1, null=True, blank=True,
                                        help_text="'S' for standard, 'C' for classification")
    concept_code = models.CharField(max_length=50, help_text="The code from the source vocabulary")
    valid_start_date = models.DateField()
    valid_end_date = models.DateField()
    invalid_reason = models.CharField(max_length=1, null=True, blank=True)

    class Meta:
        db_table = "mires_concept"
        verbose_name = "Concept"

    def __str__(self):
        return f"{self.concept_name} ({self.vocabulary_id}: {self.concept_code})"
