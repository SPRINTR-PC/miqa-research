"""Native "DICOM files -> dicom_instance" ETL Script (#417).

Self-contained (stdlib + pydicom): runs in the sandbox as `script.py`. Headers only, never decodes
pixels; emits raw UIDs (pseudonymization is the loader's job). One row per input file.

Skips (recorded, never fail): non-DICOM files, DICOMDIR, the media-storage directory SOP class.
Fails: a DICOM file lacking Study/Series/SOP Instance UID, or a DICM-preamble file that won't parse.
"""
import collections.abc
from datetime import UTC, datetime
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset
from pydicom.tag import Tag

DIRECTORY_SOP_CLASS = "1.2.840.10008.1.3.10"
_PREAMBLE_LENGTH = 128
_MAX_SEQUENCE_DEPTH = 8
_SKIPPED_KEYWORDS = frozenset({"PixelData"})

_STANDARD_IMAGE_SOP_CLASSES = frozenset({
    "1.2.840.10008.5.1.4.1.1.1.1", "1.2.840.10008.5.1.4.1.1.1.1.1", "1.2.840.10008.5.1.4.1.1.2",
    "1.2.840.10008.5.1.4.1.1.2.1", "1.2.840.10008.5.1.4.1.1.2.2", "1.2.840.10008.5.1.4.1.1.4",
    "1.2.840.10008.5.1.4.1.1.4.1", "1.2.840.10008.5.1.4.1.1.4.4", "1.2.840.10008.5.1.4.1.1.6.1",
    "1.2.840.10008.5.1.4.1.1.7", "1.2.840.10008.5.1.4.1.1.7.1", "1.2.840.10008.5.1.4.1.1.7.2",
    "1.2.840.10008.5.1.4.1.1.7.3", "1.2.840.10008.5.1.4.1.1.7.4", "1.2.840.10008.5.1.4.1.1.9",
    "1.2.840.10008.5.1.4.1.1.12.1", "1.2.840.10008.5.1.4.1.1.12.2", "1.2.840.10008.5.1.4.1.1.20",
    "1.2.840.10008.5.1.4.1.1.128",
})
_RDSR = "1.2.840.10008.5.1.4.1.1.88.67"
_RTSTRUCT = "1.2.840.10008.5.1.4.1.1.481.3"
_RTPLAN = "1.2.840.10008.5.1.4.1.1.481.5"
_RTDOSE = "1.2.840.10008.5.1.4.1.1.481.2"
_RTIMAGE = "1.2.840.10008.5.1.4.1.1.481.1"
_WSI = "1.2.840.10008.5.1.4.1.1.77.1.6"

_IRRADIATION_EVENT_CODE = "113706"
_TOTAL_CODES = {"113722": "dose_area_product_total", "113725": "dose_rp_total"}
_EVENT_CODES = {
    "122130": "dose_area_product", "111636": "entrance_exposure_at_rp", "113738": "dose_rp",
    "113733": "kvp", "113824": "exposure_time", "113734": "tube_current",
}
_MAX_DEPTH = 16


def main(ctx):
    tag_names = list(((ctx.config or {}).get("identifiers") or {}).get("tags") or [])
    tags = [(name, _parse_tag(name)) for name in tag_names]  # unknown tag name raises -> script error
    input_dir = Path(ctx.input_dir)
    for path in sorted(p for p in input_dir.rglob("*") if p.is_file() and not p.is_symlink()):
        yield _row(path, path.relative_to(input_dir).as_posix(), tags)


def _parse_tag(name: str) -> Tag:
    """A keyword ("PatientID") or a "GGGG,EEEE" / "GGGGEEEE" hex code."""
    code = name.replace(",", "").replace("(", "").replace(")", "").strip()
    if len(code) == 8:
        try:
            return Tag(int(code, 16))
        except ValueError:
            pass
    return Tag(name)


def _skipped(source_path: str, reason: str) -> dict:
    return {"source_path": source_path, "status": "skipped", "skip_reason": reason}


def _row(path: Path, source_path: str, identifier_tags) -> dict:
    if path.name.upper() == "DICOMDIR":
        return _skipped(source_path, "dicomdir")
    ds, has_preamble = _read(path, source_path)
    if ds is None:
        return _skipped(source_path, "not_dicom")
    sop_class = _sop_class_uid(ds)
    if sop_class == DIRECTORY_SOP_CLASS:
        return _skipped(source_path, "directory_sop_class")
    uids = {
        "study_instance_uid": _text(ds.get("StudyInstanceUID")),
        "series_instance_uid": _text(ds.get("SeriesInstanceUID")),
        "sop_instance_uid": _sop_instance_uid(ds),
    }
    if not uids["sop_instance_uid"] and not has_preamble:
        return _skipped(source_path, "not_dicom")
    missing = [key for key, value in uids.items() if not value]
    if missing:
        raise ValueError(f"{source_path}: DICOM file is missing {', '.join(missing)}")

    payload, geometry = _payload_and_geometry(ds, sop_class)
    return {
        "source_path": source_path,
        "status": "ok",
        **uids,
        "sop_class_uid": sop_class,
        "modality": _text(ds.get("Modality")),
        "study_datetime": _study_datetime(ds),
        "study_description": _text(ds.get("StudyDescription")),
        "series_description": _text(ds.get("SeriesDescription")),
        "contains_burned_in_annotations": _burned_in(ds.get("BurnedInAnnotation")),
        "rows": _int(ds.get("Rows")),
        "columns": _int(ds.get("Columns")),
        "number_of_frames": _int(ds.get("NumberOfFrames")),
        **geometry,
        "identifiers": _identifiers(ds, identifier_tags),
        "tags": _header_dump(ds),
        "payload": payload,
    }


def _read(path: Path, source_path: str):
    """(dataset or None, had DICM preamble). None means not DICOM."""
    with path.open("rb") as handle:
        head = handle.read(_PREAMBLE_LENGTH + 4)
    has_preamble = head[_PREAMBLE_LENGTH:] == b"DICM"
    try:
        ds = pydicom.dcmread(str(path), force=not has_preamble, stop_before_pixels=True)
    except Exception as exc:
        if has_preamble:
            raise ValueError(f"{source_path}: DICOM preamble present but the file does not parse") from exc
        return None, False
    return ds, has_preamble


def _meta(ds: Dataset, keyword: str):
    file_meta = getattr(ds, "file_meta", None)
    return file_meta.get(keyword) if file_meta else None


def _sop_class_uid(ds: Dataset) -> str | None:
    return _text(ds.get("SOPClassUID")) or _text(_meta(ds, "MediaStorageSOPClassUID"))


def _sop_instance_uid(ds: Dataset) -> str | None:
    return _text(ds.get("SOPInstanceUID")) or _text(_meta(ds, "MediaStorageSOPInstanceUID"))


def _payload_and_geometry(ds: Dataset, sop_class: str | None):
    geometry = {"image_orientation_patient": None, "image_position_patient": None,
                "pixel_spacing": None, "frame_of_reference_uid": None}
    if sop_class in _STANDARD_IMAGE_SOP_CLASSES:
        return {"kind": "image"}, _image_geometry(ds)
    if sop_class == _RDSR:
        return _rdsr(ds), geometry
    if sop_class == _RTSTRUCT:
        return _rtstruct(ds), geometry
    if sop_class == _RTPLAN:
        return _rtplan(ds), geometry
    if sop_class == _RTDOSE:
        return _rtdose(ds), _image_geometry(ds)
    if sop_class == _RTIMAGE:
        return _rtimage(ds), _image_geometry(ds)
    if sop_class == _WSI:
        geometry = _image_geometry(ds)
        geometry["pixel_spacing"] = _functional_group_pixel_spacing(ds)
        return _wsi(ds), geometry
    return {"kind": "generic"}, geometry


def _image_geometry(ds: Dataset) -> dict:
    return {
        "image_orientation_patient": _decimal_list(ds.get("ImageOrientationPatient"), 3),
        "image_position_patient": _decimal_list(ds.get("ImagePositionPatient"), 3),
        "pixel_spacing": _decimal_list(ds.get("PixelSpacing"), 2),
        "frame_of_reference_uid": _text(ds.get("FrameOfReferenceUID")),
    }


# --- common helpers -------------------------------------------------------------------------

def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _burned_in(value) -> bool | None:
    text = str(value).strip().upper() if value is not None else ""
    if text in ("M", "Y"):
        return True
    if text == "N":
        return False
    return None


def _decimal_list(value, expected_length: int) -> list[float] | None:
    if value is None:
        return None
    try:
        parts = value.split("\\") if isinstance(value, str) else list(value)
        numbers = [float(part) for part in parts]
    except (TypeError, ValueError, AttributeError):
        return None
    return numbers if len(numbers) == expected_length else None


def _parse_datetime(date_value, time_value) -> datetime | None:
    date = str(date_value or "").strip()
    time = str(time_value or "").strip()
    if not (date.isdigit() and len(date) == 8):
        return None
    try:
        result = datetime.strptime(date, "%Y%m%d")
        if time:
            base, _, fraction = time.partition(".")
            result = result.replace(
                hour=int(base[0:2]), minute=int(base[2:4]), second=int(base[4:6]),
                microsecond=int(f"{fraction}000000"[:6]) if fraction else 0)
        return result.replace(tzinfo=UTC)
    except (ValueError, IndexError):
        return None


def _study_datetime(ds: Dataset) -> datetime | None:
    """Study, else Series, Acquisition, Content date/time (UTC-assumed); None when none is usable."""
    for prefix in ("Study", "Series", "Acquisition", "Content"):
        result = _parse_datetime(ds.get(f"{prefix}Date"), ds.get(f"{prefix}Time"))
        if result is not None:
            return result
    return None


def _identifiers(ds: Dataset, identifier_tags) -> dict[str, str]:
    result = {}
    for name, tag in identifier_tags:
        element = ds.get(tag)
        if element is None or element.VR == "SQ" or isinstance(element.value, bytes):
            continue
        value = element.value
        if isinstance(value, collections.abc.Sequence) and not isinstance(value, str):
            text = "\\".join(str(v) for v in value)
        else:
            text = str(value)
        text = text.strip()
        if text:
            result[name] = text
    return result


def _header_dump(ds: Dataset) -> dict:
    dump = {}
    file_meta = getattr(ds, "file_meta", None)
    for element in [*(file_meta or []), *ds]:
        key = _element_key(element)
        if key not in _SKIPPED_KEYWORDS:
            dump[key] = _json_safe(element.value, 0)
    return dump


def _element_key(element) -> str:
    return element.keyword or f"{element.tag.group:04X},{element.tag.element:04X}"


def _json_safe(value, depth: int):
    if depth >= _MAX_SEQUENCE_DEPTH:
        return str(value)
    if isinstance(value, Dataset):
        return {_element_key(e): _json_safe(e.value, depth + 1) for e in value}
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, collections.abc.Sequence):
        return [_json_safe(item, depth + 1) for item in value]
    return str(value)


# --- RDSR -----------------------------------------------------------------------------------

def _rdsr(ds: Dataset) -> dict:
    report = {"kind": "rdsr", "totals": {}, "irradiation_events": []}
    _walk(ds, report, None, 0)
    return report


def _walk(item: Dataset, report: dict, event: dict | None, depth: int) -> None:
    if depth > _MAX_DEPTH:
        return
    for child in item.get("ContentSequence") or []:
        code = _concept_code(child)
        if code == _IRRADIATION_EVENT_CODE and event is None:
            new_event: dict = {}
            report["irradiation_events"].append(new_event)
            _walk(child, report, new_event, depth + 1)
            continue
        if child.get("ValueType") == "NUM":
            target, codes = (report["totals"], _TOTAL_CODES) if event is None else (event, _EVENT_CODES)
            key = codes.get(code)
            measurement = _measurement(child) if key else None
            if measurement is not None:
                target[key] = measurement
        _walk(child, report, event, depth + 1)


def _concept_code(item: Dataset) -> str:
    sequence = item.get("ConceptNameCodeSequence")
    if not sequence:
        return ""
    concept = sequence[0]
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


# --- radiotherapy ---------------------------------------------------------------------------

def _uids(items, keyword: str) -> list[str]:
    return [text for item in items for text in [_text(item.get(keyword))] if text]


def _rtstruct(ds: Dataset) -> dict:
    frame_uids, series_uids, image_uids = [], [], []
    for frame in ds.get("ReferencedFrameOfReferenceSequence") or []:
        frame_uids += _uids([frame], "FrameOfReferenceUID")
        for rt_study in frame.get("RTReferencedStudySequence") or []:
            for series in rt_study.get("RTReferencedSeriesSequence") or []:
                series_uids += _uids([series], "SeriesInstanceUID")
                image_uids += _uids(series.get("ContourImageSequence") or [], "ReferencedSOPInstanceUID")
    interpreted = {
        obs.get("ReferencedROINumber"): _text(obs.get("RTROIInterpretedType"))
        for obs in ds.get("RTROIObservationsSequence") or []
    }
    rois = [
        {"number": _int(roi.get("ROINumber")), "name": _text(roi.get("ROIName")),
         "interpreted_type": interpreted.get(roi.get("ROINumber"))}
        for roi in ds.get("StructureSetROISequence") or []
    ]
    return {
        "kind": "rtstruct",
        "referenced_frame_of_reference_uids": frame_uids,
        "referenced_series_instance_uids": series_uids,
        "referenced_image_sop_instance_uids": image_uids,
        "roi_count": len(rois),
        "rois": rois,
    }


def _rtplan(ds: Dataset) -> dict:
    return {
        "kind": "rtplan",
        "referenced_structure_set_sop_instance_uids": _uids(
            ds.get("ReferencedStructureSetSequence") or [], "ReferencedSOPInstanceUID"),
        "plan_label": _text(ds.get("RTPlanLabel")),
        "plan_intent": _text(ds.get("PlanIntent")),
        "approval_status": _text(ds.get("ApprovalStatus")),
        "beam_count": len(ds.get("BeamSequence") or []),
        "fraction_group_count": len(ds.get("FractionGroupSequence") or []),
    }


def _rtdose(ds: Dataset) -> dict:
    return {
        "kind": "rtdose",
        "referenced_rt_plan_sop_instance_uids": _uids(
            ds.get("ReferencedRTPlanSequence") or [], "ReferencedSOPInstanceUID"),
        "referenced_structure_set_sop_instance_uids": _uids(
            ds.get("ReferencedStructureSetSequence") or [], "ReferencedSOPInstanceUID"),
        "dose_grid_scaling": _float(ds.get("DoseGridScaling")),
        "dose_units": _text(ds.get("DoseUnits")),
        "dose_type": _text(ds.get("DoseType")),
        "dose_summation_type": _text(ds.get("DoseSummationType")),
    }


def _rtimage(ds: Dataset) -> dict:
    return {
        "kind": "rtimage",
        "referenced_rt_plan_sop_instance_uids": _uids(
            ds.get("ReferencedRTPlanSequence") or [], "ReferencedSOPInstanceUID"),
        "referenced_beam_number": _int(ds.get("ReferencedBeamNumber")),
        "referenced_fraction_group_number": _int(ds.get("ReferencedFractionGroupNumber")),
        "rt_image_label": _text(ds.get("RTImageLabel")),
        "rt_image_plane": _text(ds.get("RTImagePlane")),
        "rt_image_sid": _float(ds.get("RTImageSID")),
    }


# --- pathology WSI --------------------------------------------------------------------------

def _functional_group_pixel_spacing(ds: Dataset) -> list[float] | None:
    for sequence_keyword in ("SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence"):
        groups = ds.get(sequence_keyword) or []
        if not groups:
            continue
        measures = groups[0].get("PixelMeasuresSequence") or []
        if not measures:
            continue
        spacing = _decimal_list(measures[0].get("PixelSpacing"), 2)
        if spacing is not None:
            return spacing
    return None


def _wsi(ds: Dataset) -> dict:
    image_type = list(ds.get("ImageType") or [])
    optical_paths = ds.get("OpticalPathSequence") or []
    return {
        "kind": "wsi",
        "frame_count": _int(ds.get("NumberOfFrames")),
        "tile_rows": _int(ds.get("Rows")),
        "tile_columns": _int(ds.get("Columns")),
        "total_pixel_matrix_rows": _int(ds.get("TotalPixelMatrixRows")),
        "total_pixel_matrix_columns": _int(ds.get("TotalPixelMatrixColumns")),
        "image_type": image_type[2] if len(image_type) > 2 else None,
        "optical_path_count": len(optical_paths),
        "objective_lens_power": _float(optical_paths[0].get("ObjectiveLensPower")) if optical_paths else None,
    }
