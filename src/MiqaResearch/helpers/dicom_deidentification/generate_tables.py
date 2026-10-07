"""Regenerate the committed PS3.15 tables from the DICOM DocBook source.

Usage (from src/MiqaResearch):

    curl -sSLo part15.xml \\
        https://dicom.nema.org/medical/dicom/current/source/docbook/part15/part15.xml
    uv run python -m helpers.dicom_deidentification.generate_tables part15.xml

Writes `data/table_E.1-1.json` (Application Level Confidentiality Profile
Attributes) and `data/table_E.3.10-1.json` (Safe Private Attributes) next to
this module. The tables are data, never hand-edited: the profile reads them
as-is (ADR 0028).
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_NS = {"d": "http://docbook.org/ns/docbook"}
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DATA_DIR = Path(__file__).parent / "data"

E1_1_COLUMNS = (
    "name",
    "tag",
    "retired",
    "in_std_comp_iod",
    "basic",
    "retain_safe_private",
    "retain_uids",
    "retain_device_identity",
    "retain_institution_identity",
    "retain_patient_characteristics",
    "retain_long_full_dates",
    "retain_long_modified_dates",
    "clean_descriptors",
    "clean_structured_content",
    "clean_graphics",
)
E3_10_1_COLUMNS = ("tag", "private_creator", "vr", "vm", "meaning")


def _text(element) -> str:
    return " ".join("".join(element.itertext()).split())


def _rows(root, table_id: str) -> list[list[str]]:
    table = root.find(f".//d:table[@{_XML_ID}='{table_id}']", _NS)
    if table is None:
        raise SystemExit(f"{table_id} not found")
    return [[_text(td) for td in tr.findall("d:td", _NS)] for tr in table.findall("./d:tbody/d:tr", _NS)]


def _release(root) -> str:
    subtitle = root.find(".//d:subtitle", _NS)
    match = re.search(r"PS3\.15 (\S+)", _text(subtitle) if subtitle is not None else "")
    return match.group(1) if match else "unknown"


def _write(name: str, release: str, columns: tuple, rows: list[list[str]]) -> None:
    lines = [json.dumps(dict(zip(columns, row, strict=True)), ensure_ascii=False) for row in rows]
    body = ",\n    ".join(lines)
    text = f'{{\n  "source": "DICOM PS3.15 {release} {name}",\n  "rows": [\n    {body}\n  ]\n}}\n'
    (DATA_DIR / f"{name}.json").write_text(text, encoding="utf-8")


def main(xml_path: str) -> None:
    root = ET.parse(xml_path).getroot()
    release = _release(root)
    DATA_DIR.mkdir(exist_ok=True)
    _write("table_E.1-1", release, E1_1_COLUMNS, _rows(root, "table_E.1-1"))
    _write("table_E.3.10-1", release, E3_10_1_COLUMNS, _rows(root, "table_E.3.10-1"))


if __name__ == "__main__":
    main(sys.argv[1])
