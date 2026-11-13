"""`dicom_instance` Datatype row schema (#417, spec #401): one row per input file.

Raw UIDs, headers only. Fields typed `DicomUid` (including inside payload lists) are the ones the
loader pseudonymizes; the SOP Class UID is a public standard value and stays raw. There is no raw header
dump: the loader rebuilds the stored metadata from the file's own bytes, and the schema forbids extras.
"""
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .participant_reference import DicomUid
from .registry import register_schema


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Measurement(_Strict):
    value: float
    unit: str | None = None


class ImagePayload(_Strict):
    kind: Literal["image"] = "image"


class RdsrPayload(_Strict):
    kind: Literal["rdsr"] = "rdsr"
    totals: dict[str, Measurement] = Field(default_factory=dict)
    irradiation_events: list[dict[str, Measurement]] = Field(default_factory=list)


class Roi(_Strict):
    number: int | None = None
    name: str | None = None
    interpreted_type: str | None = None


class RtstructPayload(_Strict):
    kind: Literal["rtstruct"] = "rtstruct"
    referenced_frame_of_reference_uids: list[DicomUid] = Field(default_factory=list)
    referenced_series_instance_uids: list[DicomUid] = Field(default_factory=list)
    referenced_image_sop_instance_uids: list[DicomUid] = Field(default_factory=list)
    roi_count: int = 0
    rois: list[Roi] = Field(default_factory=list)


class RtplanPayload(_Strict):
    kind: Literal["rtplan"] = "rtplan"
    referenced_structure_set_sop_instance_uids: list[DicomUid] = Field(default_factory=list)
    plan_label: str | None = None
    plan_intent: str | None = None
    approval_status: str | None = None
    beam_count: int = 0
    fraction_group_count: int = 0


class RtdosePayload(_Strict):
    kind: Literal["rtdose"] = "rtdose"
    referenced_rt_plan_sop_instance_uids: list[DicomUid] = Field(default_factory=list)
    referenced_structure_set_sop_instance_uids: list[DicomUid] = Field(default_factory=list)
    dose_grid_scaling: float | None = None
    dose_units: str | None = None
    dose_type: str | None = None
    dose_summation_type: str | None = None


class RtimagePayload(_Strict):
    kind: Literal["rtimage"] = "rtimage"
    referenced_rt_plan_sop_instance_uids: list[DicomUid] = Field(default_factory=list)
    referenced_beam_number: int | None = None
    referenced_fraction_group_number: int | None = None
    rt_image_label: str | None = None
    rt_image_plane: str | None = None
    rt_image_sid: float | None = None


class WsiPayload(_Strict):
    kind: Literal["wsi"] = "wsi"
    frame_count: int | None = None
    tile_rows: int | None = None
    tile_columns: int | None = None
    total_pixel_matrix_rows: int | None = None
    total_pixel_matrix_columns: int | None = None
    image_type: str | None = None
    optical_path_count: int = 0
    objective_lens_power: float | None = None


class GenericPayload(_Strict):
    kind: Literal["generic"] = "generic"


Payload = Annotated[
    ImagePayload | RdsrPayload | RtstructPayload | RtplanPayload | RtdosePayload | RtimagePayload
    | WsiPayload | GenericPayload,
    Field(discriminator="kind"),
]


@register_schema("dicom_instance")
class DicomInstanceRowSchema(_Strict):
    source_path: str
    status: Literal["ok", "skipped"]
    skip_reason: Literal["not_dicom", "dicomdir", "directory_sop_class"] | None = None
    study_instance_uid: DicomUid | None = None
    series_instance_uid: DicomUid | None = None
    sop_instance_uid: DicomUid | None = None
    sop_class_uid: str | None = None
    modality: str | None = None
    study_datetime: datetime | None = None
    study_description: str | None = None
    series_description: str | None = None
    contains_burned_in_annotations: bool | None = None
    rows: int | None = None
    columns: int | None = None
    number_of_frames: int | None = None
    image_orientation_patient: list[float] | None = None
    image_position_patient: list[float] | None = None
    pixel_spacing: list[float] | None = None
    frame_of_reference_uid: DicomUid | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    payload: Payload | None = None

    @model_validator(mode="after")
    def _status_decides_the_rest(self) -> Self:
        if self.status == "skipped":
            if self.skip_reason is None:
                raise ValueError("a skipped row needs skip_reason")
            return self
        if self.skip_reason is not None:
            raise ValueError("skip_reason is only for skipped rows")
        if not (self.study_instance_uid and self.series_instance_uid and self.sop_instance_uid):
            raise ValueError("an ok row needs study, series and SOP instance UIDs")
        if self.payload is None:
            raise ValueError("an ok row needs a payload")
        return self
