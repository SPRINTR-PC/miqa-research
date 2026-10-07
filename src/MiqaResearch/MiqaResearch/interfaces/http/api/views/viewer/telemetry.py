"""First-render beacon (spec #271 "First render", #293). Session auth (CSRF on POST).

POST /first-render: the viewer's performance-mark timings (ms since open), series size and
transfer syntax. Logged as one record on `MiqaResearch.telemetry.viewer`, which the OTLP
handler exports (MiqaResearch/telemetry.py). The schema forbids any other field, so UIDs,
URLs and participant data can't reach telemetry; 422 otherwise.
"""
import logging

from ninja import Field, Router, Schema, Status
from ninja.security import SessionAuth
from pydantic import ConfigDict

router = Router(auth=SessionAuth(), tags=["viewer"])

logger = logging.getLogger("MiqaResearch.telemetry.viewer")

# Transfer syntax UIDs are all under the DICOM root 1.2.840.10008.1.2 (PS3.6 Annex A); a study,
# series, SOP or SOP Class UID never matches, so the field can't carry an identifier.
_TRANSFER_SYNTAX_UID = r"^1\.2\.840\.10008\.1\.2(\.[0-9]+){0,4}$"


class FirstRenderIn(Schema):
    model_config = ConfigDict(extra="forbid")

    first_image_ms: float | None = Field(None, ge=0)
    interleaved_ms: float | None = Field(None, ge=0)
    volume_loaded_ms: float | None = Field(None, ge=0)
    slices: int | None = Field(None, ge=0)
    bytes: int | None = Field(None, ge=0)
    transfer_syntax: str | None = Field(None, pattern=_TRANSFER_SYNTAX_UID)


@router.post("/first-render", response={204: None}, url_name="viewer_first_render")
def first_render(request, beacon: FirstRenderIn):
    attributes = {f"viewer.{k}": v for k, v in beacon.model_dump(exclude_none=True).items()}
    logger.info("viewer first render", extra=attributes)
    return Status(204, None)
