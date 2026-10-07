"""Radiotherapy extractors (#121): RTSTRUCT, RTPLAN, RTDOSE, RTIMAGE.

Each handler adds a structured summary under `metadata["rt_summary"]` holding
the object's key cross-references. Every referenced UID is pseudonymized the
same way as stored UIDs, so a reference equals the referenced record's stored
UID. RTSTRUCT/RTPLAN carry no pixel data and leave geometry columns empty;
RTDOSE/RTIMAGE pick up geometry from any standard image-plane tags present.
"""
from pydicom.dataset import Dataset

from helpers.dicom_uid import pseudonymize_uid

from .common import image_geometry
from .generic import extract as generic_extract


def extract_rtstruct(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    frame_uids, series_uids, image_uids = [], [], []
    for frame in ds.get("ReferencedFrameOfReferenceSequence") or []:
        _append_uid(frame_uids, frame.get("FrameOfReferenceUID"), research_project)
        for rt_study in frame.get("RTReferencedStudySequence") or []:
            for series in rt_study.get("RTReferencedSeriesSequence") or []:
                _append_uid(series_uids, series.get("SeriesInstanceUID"), research_project)
                for image in series.get("ContourImageSequence") or []:
                    _append_uid(image_uids, image.get("ReferencedSOPInstanceUID"), research_project)
    interpreted = {
        obs.get("ReferencedROINumber"): _text(obs.get("RTROIInterpretedType"))
        for obs in ds.get("RTROIObservationsSequence") or []
    }
    rois = [
        {
            "number": _int(roi.get("ROINumber")),
            "name": _text(roi.get("ROIName")),
            "interpreted_type": interpreted.get(roi.get("ROINumber")),
        }
        for roi in ds.get("StructureSetROISequence") or []
    ]
    _set_summary(result, "RTSTRUCT", {
        "referenced_frame_of_reference_uids": frame_uids,
        "referenced_series_instance_uids": series_uids,
        "referenced_image_sop_instance_uids": image_uids,
        "roi_count": len(rois),
        "rois": rois,
    })
    return result


def extract_rtplan(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    _set_summary(result, "RTPLAN", {
        "referenced_structure_set_sop_instance_uids": _referenced_uids(
            ds, "ReferencedStructureSetSequence", research_project),
        "plan_label": _text(ds.get("RTPlanLabel")),
        "plan_intent": _text(ds.get("PlanIntent")),
        "approval_status": _text(ds.get("ApprovalStatus")),
        "beam_count": len(ds.get("BeamSequence") or []),
        "fraction_group_count": len(ds.get("FractionGroupSequence") or []),
    })
    return result


def extract_rtdose(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    result.update(image_geometry(ds, research_project))
    _set_summary(result, "RTDOSE", {
        "referenced_rt_plan_sop_instance_uids": _referenced_uids(ds, "ReferencedRTPlanSequence", research_project),
        "referenced_structure_set_sop_instance_uids": _referenced_uids(
            ds, "ReferencedStructureSetSequence", research_project),
        "dose_grid_scaling": _float(ds.get("DoseGridScaling")),
        "dose_units": _text(ds.get("DoseUnits")),
        "dose_type": _text(ds.get("DoseType")),
        "dose_summation_type": _text(ds.get("DoseSummationType")),
    })
    return result


def extract_rtimage(ds: Dataset, research_project, participant_alias: str) -> dict:
    result = generic_extract(ds, research_project, participant_alias)
    result.update(image_geometry(ds, research_project))
    _set_summary(result, "RTIMAGE", {
        "referenced_rt_plan_sop_instance_uids": _referenced_uids(ds, "ReferencedRTPlanSequence", research_project),
        "referenced_beam_number": _int(ds.get("ReferencedBeamNumber")),
        "referenced_fraction_group_number": _int(ds.get("ReferencedFractionGroupNumber")),
        "rt_image_label": _text(ds.get("RTImageLabel")),
        "rt_image_plane": _text(ds.get("RTImagePlane")),
        "rt_image_sid": _float(ds.get("RTImageSID")),
    })
    return result


def _set_summary(result: dict, rt_type: str, summary: dict) -> None:
    result["metadata"]["rt_summary"] = {"type": rt_type, **summary}


def _referenced_uids(ds: Dataset, sequence_keyword: str, research_project) -> list[str]:
    uids: list[str] = []
    for item in ds.get(sequence_keyword) or []:
        _append_uid(uids, item.get("ReferencedSOPInstanceUID"), research_project)
    return uids


def _append_uid(target: list[str], value, research_project) -> None:
    text = str(value or "").strip()
    if text:
        target.append(pseudonymize_uid(text, research_project))


def _text(value) -> str | None:
    text = str(value).strip() if value is not None else ""
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
