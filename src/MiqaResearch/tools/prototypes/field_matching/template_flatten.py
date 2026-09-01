"""
PROTOTYPE -- throwaway code for issue #16.

Flattens the semantic-only kpforms template (sections -> inputGroups -> fields)
into a single document-order list of fields, each with its options (if any).
Document order is the "section/group ordering as a prior" the issue asks for --
it's literally just the order fields appear in the template JSON, which mirrors
the printed form's order (the template was authored *from* this form, #12).
"""

import json
from dataclasses import dataclass, field


@dataclass
class FieldSpec:
    id: str
    label: str
    type: str
    order: int
    options: list = field(default_factory=list)  # list of (value, option_label)


BOX_MARK_TYPES = {"checkbox", "radio", "ranged-radio"}


def load_template(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flatten(template):
    fields = []
    order = 0
    for section in template["sections"]:
        for group in section.get("inputGroups", []):
            for f in group.get("fields", []):
                options = []
                if f["type"] in ("checkbox", "radio"):
                    options = [(o["value"], o["label"]) for o in f.get("options", [])]
                elif f["type"] == "ranged-radio":
                    opts = f.get("optionLabelsAndIndices", [])
                    options = sorted(((o["value"], o["label"]) for o in opts), key=lambda t: int(t[0]))
                fields.append(FieldSpec(id=f["id"], label=f["label"], type=f["type"], order=order, options=options))
                order += 1
    return fields
