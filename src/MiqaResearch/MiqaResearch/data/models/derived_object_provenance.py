from uuid import uuid7

from django.conf import settings
from django.db import models

from contract.constants.annotation import KIND_CHOICES, SOURCE_CHOICES

from .dicom_series import DicomSeries


class DerivedObjectProvenance(models.Model):
    """Provenance of one Annotation or Segmentation version (ADR 0026, #287).

    Each version is its own Dicom Series. Versions form one linear chain
    through `predecessor` (one-to-one, so a version has at most one successor);
    the version without a successor is the chain's head. Objects never change:
    Supersede adds a version, Retire marks the head retired.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    series = models.OneToOneField(DicomSeries, on_delete=models.CASCADE, related_name="provenance")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Who saved it in the viewer; null for ingested objects")
    source_series = models.ManyToManyField(DicomSeries, related_name="derived_objects", blank=True)
    base_series = models.ForeignKey(
        DicomSeries, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="The source series whose grid it is on (the Fusion base, #290); null for ingested objects")
    predecessor = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="successor")
    chain_id = models.UUIDField(db_index=True, help_text="The id of the chain's first version")
    version = models.PositiveIntegerField(default=1)
    retired = models.BooleanField(default=False)
    retired_at = models.DateTimeField(null=True, blank=True)
    retired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mires_derived_object_provenance"
        ordering = ["chain_id", "version"]

    def __str__(self):
        return f"{self.kind} v{self.version} ({self.series_id})"

    def save(self, *args, **kwargs):
        if self.chain_id is None:
            self.chain_id = self.predecessor.chain_id if self.predecessor_id else self.id
        super().save(*args, **kwargs)
