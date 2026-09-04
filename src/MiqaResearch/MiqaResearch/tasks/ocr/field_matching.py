"""Field-matching stage.

Locates each template field's region by fuzzy-matching its label against
OCR'd words, searched across all pages of the form (#16). Stubbed out until
#47 — see the prototype at `prototype/issue-16-field-matching` for the
algorithm to port (its label-anchor search only, not its box-discovery half).
"""

from dataclasses import dataclass

import pymupdf
from kpforms.form_schema import FormTemplateSchema


@dataclass
class FieldMatch:
    field_id: str
    field_type: str
    page_index: int | None = None
    region: tuple[int, int, int, int] | None = None
    label_match_score: float = 0.0
    text_value: str | None = None
    tesseract_word_confidence: float = 0.0


def match_fields(pages: list[pymupdf.Pixmap], template_schema: FormTemplateSchema) -> list[FieldMatch]:
    """Stub for #47: no field is located, so every field escalates by default."""
    return []
