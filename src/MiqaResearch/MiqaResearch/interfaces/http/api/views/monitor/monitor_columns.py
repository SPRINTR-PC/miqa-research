from django.utils.translation import gettext as _
from ninja import Router, Schema

router = Router()


class MonitorColumnSchema(Schema):
    id: str
    title: str
    dataType: str


@router.get("", response=list[MonitorColumnSchema])
def monitor_column_list_v1(request):
    return _get_monitor_column_list()


def _get_monitor_column_list():
    return [
        MonitorColumnSchema(
            id="dicomfile.image_orientation_patient", title=_("Image Orientation Patient"), dataType="number[]"),
        MonitorColumnSchema(
            id="dicomfile.frame_of_reference_uid", title=_("Frame of Reference UID"), dataType="string"),
        MonitorColumnSchema(id="dicomseries.series_instance_uid", title=_("Series Instance UID"), dataType="string"),
        MonitorColumnSchema(id="dicomseries.series_description", title=_("Series Description"), dataType="string"),
        MonitorColumnSchema(id="dicomseries.modality", title=_("Modality"), dataType="string"),
        MonitorColumnSchema(id="dicomstudy.study_instance_uid", title=_("Study Instance UID"), dataType="string"),
        MonitorColumnSchema(id="dicomstudy.study_description", title=_("Study Description"), dataType="string"),
        MonitorColumnSchema(id="patient.patient_id", title=_("Patient ID"), dataType="string"),
        MonitorColumnSchema(id="patient.first_name", title=_("Patient First Name"), dataType="string"),
        MonitorColumnSchema(id="patient.last_name", title=_("Patient Last Name"), dataType="string"),
        MonitorColumnSchema(id="patient.patient_name", title=_("Patient Name"), dataType="string"),
        MonitorColumnSchema(id="patient.date_of_birth", title=_("Patient DOB"), dataType="string"),
        MonitorColumnSchema(id="patient.gender", title=_("Gender"), dataType="string"),
        MonitorColumnSchema(id="researchproject.name", title=_("Project Name"), dataType="string"),
        MonitorColumnSchema(id="researchproject.id", title=_("Project ID"), dataType="string"),
        MonitorColumnSchema(id="researchproject.description", title=_("Project Description"), dataType="string"),
        MonitorColumnSchema(id="researchproject.primary_investigator", title=_("Project PI"), dataType="string"),
        MonitorColumnSchema(id="promdata.prom_form_template.name", title=_("PROM Template Name"), dataType="string"),
        MonitorColumnSchema(
            id="promdata.prom_form_template.version", title=_("PROM Template Version"), dataType="string"),
        MonitorColumnSchema(id="parsedpromform.data", title=_("Parsed PROM Form Data"), dataType="object"),
        MonitorColumnSchema(
            id="parsedpromform.prom_file", title=_("Parsed PROM Form File"), dataType="object"),
        MonitorColumnSchema(id="parsedpromform.validated_by", title=_("PROM Validated By"), dataType="string"),
        MonitorColumnSchema(id="parsedpromform.validated_at", title=_("PROM Validated At"), dataType="string"),
    ]