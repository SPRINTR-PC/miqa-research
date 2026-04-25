from django.utils.translation import gettext as _
from ninja import Schema, Router

router = Router()

class MonitorFilterCategoryOptionsSchema(Schema):
    id: str
    title: str
    wildcard: bool = False
    icon: str | None = None
    selected: bool = False

class MonitorFilterRangeSchema(Schema):
    min: float
    max: float
    selected_min: float
    selected_max: float
    include_null: bool = False

class MonitorFilterSchema(Schema):
    gender: list[str]
    category: str
    options: list[MonitorFilterCategoryOptionsSchema] | MonitorFilterRangeSchema

@router.get("/options", response=list[MonitorFilterSchema])
def monitor_filter_options_v1(request):
    return [
        MonitorFilterSchema(
            category="Modality",
            options=[
                MonitorFilterCategoryOptionsSchema(id="CT", title=_("CT")),
                MonitorFilterCategoryOptionsSchema(id="MR", title=_("MRI")),
                MonitorFilterCategoryOptionsSchema(id="PT", title=_("PET")),
                MonitorFilterCategoryOptionsSchema(id="US", title=_("Ultrasound")),
                MonitorFilterCategoryOptionsSchema(id="XA", title=_("Fluoroscopy")),
                MonitorFilterCategoryOptionsSchema(id="DX", title=_("Conventional X-ray")),
                MonitorFilterCategoryOptionsSchema(id="RTDOSE", title=_("RTDOSE")),
                MonitorFilterCategoryOptionsSchema(id="MG", title=_("Mammography")),
                MonitorFilterCategoryOptionsSchema(id="RTSTRUCT", title=_("RTSTRUCT")),
                MonitorFilterCategoryOptionsSchema(id="RTPLAN", title=_("RTPLAN")),
                MonitorFilterCategoryOptionsSchema(id="RTIMAGE", title=_("RTIMAGE")),
            ]
        ),
        MonitorFilterSchema(
            category="Gender",
            options=[
                MonitorFilterCategoryOptionsSchema(id="M", title=_("Male")),
                MonitorFilterCategoryOptionsSchema(id="F", title=_("Female")),
                MonitorFilterCategoryOptionsSchema(id="O", title=_("Other")),
            ]
        ),
        MonitorFilterSchema(
            category="Patient Age",
            options=MonitorFilterRangeSchema(
                min=0, max=120, selected_min=0, selected_max=120, include_null=True
            )
        ),
    ]