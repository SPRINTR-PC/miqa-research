"""X-Ray Radiation Dose SR extractor (#121): dose values from the SR content tree.

The RDSR content tree (PS3.16 TID 10001) is walked generically; NUM items are
matched on their DCM concept code, never on position. Accumulated totals
(TID 10007) land in `totals`; each Irradiation Event container (TID 10003)
yields one entry in `irradiation_events`. Result goes under
`metadata["dose_report"]`; each value keeps its measurement unit, because
units vary by producer (e.g. exposure time in ms vs s).
"""
from pydicom.dataset import Dataset

from .generic import extract as generic_extract

IRRADIATION_EVENT_CODE = "113706"  # TID 10003 root container

# DCM concept code -> key, for values outside any irradiation event (TID 10007)
_TOTAL_CODES = {
    "113722": "dose_area_product_total",
    "113725": "dose_rp_total",
}
# DCM concept code -> key, for values inside an irradiation event (TID 10003 / 10003B)
_EVENT_CODES = {
    "122130": "dose_area_product",
    "111636": "entrance_exposure_at_rp",
    "113738": "dose_rp",
    "113733": "kvp",
    "113824": "exposure_time",
    "113734": "tube_current",
}

# Sanity bound on tree depth; TID 10001 nests only a handful of levels.
_MAX_DEPTH = 16


def extract(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    report = {"totals": {}, "irradiation_events": []}
    _walk(ds, report, event=None, depth=0)
    result["metadata"]["dose_report"] = report
    return result


def _walk(item: Dataset, report: dict, event: dict | None, depth: int) -> None:
    if depth > _MAX_DEPTH:
        return
    for child in item.get("ContentSequence") or []:
        code = _concept_code(child)
        if code == IRRADIATION_EVENT_CODE and event is None:
            new_event: dict = {}
            report["irradiation_events"].append(new_event)
            _walk(child, report, new_event, depth + 1)
            continue
        if child.get("ValueType") == "NUM":
            _record_num(child, code, report, event)
        _walk(child, report, event, depth + 1)


def _record_num(item: Dataset, code: str, report: dict, event: dict | None) -> None:
    target, codes = (report["totals"], _TOTAL_CODES) if event is None else (event, _EVENT_CODES)
    key = codes.get(code)
    if key is None:
        return
    measurement = _measurement(item)
    if measurement is not None:
        target[key] = measurement


def _concept_code(item: Dataset) -> str:
    sequence = item.get("ConceptNameCodeSequence")
    if not sequence:
        return ""
    concept = sequence[0]
    # only DCM-scheme codes are matched; another scheme could reuse the same value
    if str(concept.get("CodingSchemeDesignator") or "").strip() != "DCM":
        return ""
    return str(concept.get("CodeValue") or "").strip()


def _measurement(item: Dataset) -> dict | None:
    measured = item.get("MeasuredValueSequence")
    if not measured:
        return None
    entry = measured[0]
    try:
        value = float(entry.NumericValue)
    except (AttributeError, TypeError, ValueError):
        return None
    units = entry.get("MeasurementUnitsCodeSequence")
    unit = str(units[0].get("CodeValue") or "").strip() if units else ""
    return {"value": value, "unit": unit or None}
