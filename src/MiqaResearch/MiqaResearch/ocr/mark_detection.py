"""Mark-detection stage.

Ink-density thresholding on choice-type fields (checkbox / radio /
ranged-radio grid / circle-scale), given the regions field_matching locates
(#15). Stubbed out until #48 — see the prototype at
`prototype/issue-15-checkbox-detection` for the measured per-field-type-class
thresholds to port.
"""

from dataclasses import dataclass

import pymupdf

from .field_matching import FieldMatch


@dataclass
class MarkResult:
    field_id: str
    value: str | list[str] | None = None
    option_localization: float = 0.0
    mark_margin_ratio: float = 0.0


def detect_marks(pages: list[pymupdf.Pixmap], field_matches: list[FieldMatch]) -> dict[str, MarkResult]:
    """Stub for #48: no classic-path value is produced for any choice field."""
    return {}
