"""Annotations and Segmentations (ADR 0026, #287)."""

KIND_ANNOTATION = "annotation"
KIND_SEGMENTATION = "segmentation"
KIND_CHOICES = [
    (KIND_ANNOTATION, "Annotation"),
    (KIND_SEGMENTATION, "Segmentation"),
]

# Data Kind split of Dicom Series by modality
ANNOTATION_MODALITIES = ("SR", "ANN")
SEGMENTATION_MODALITIES = ("SEG", "RTSTRUCT")
KIND_BY_MODALITY = {
    **dict.fromkeys(ANNOTATION_MODALITIES, KIND_ANNOTATION),
    **dict.fromkeys(SEGMENTATION_MODALITIES, KIND_SEGMENTATION),
}
DERIVED_MODALITIES = ANNOTATION_MODALITIES + SEGMENTATION_MODALITIES

# What the viewer may save; ANN is built on the server, RTSTRUCT is export-only
VIEWER_SAVE_MODALITIES = ("SR", "SEG")

SOURCE_VIEWER = "viewer"
SOURCE_INGESTED = "ingested"
SOURCE_CHOICES = [
    (SOURCE_VIEWER, "Viewer"),
    (SOURCE_INGESTED, "Ingested"),
]
