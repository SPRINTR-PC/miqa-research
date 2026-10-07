from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from ninja import Router
from MiqaResearch.data.models.dicom_file import DicomFile

from .access import audit_client_access, machine_only, readable_files
from .frames import router as frames_router
from .metadata import router as metadata_router

router = Router()
# Retrieve Frames (#274) and Retrieve Metadata (#275) live in their own modules; same URL prefix.
router.add_router("", frames_router)
router.add_router("", metadata_router)


def _readable(request):
    """Stored files within the caller's Client Binding (raw endpoints are machine-only), series loaded for the audit."""
    return readable_files(request, DicomFile.objects.select_related("series__study__study_participant"))


# Helper for multipart/related response
def multipart_related_response(items, boundary="boundary", content_type_item="application/dicom"):
    """
    items: a list of either Django File objects or bytes.
    """
    content_type = f'multipart/related; type="{content_type_item}"; boundary={boundary}'

    def file_iterator():
        for item in items:
            yield f"--{boundary}\r\n".encode()
            yield f"Content-Type: {content_type_item}\r\n\r\n".encode()
            if hasattr(item, 'open'):
                with item.open('rb') as fd:
                    while chunk := fd.read(8192):
                        yield chunk
            elif isinstance(item, bytes):
                yield item
            yield b"\r\n"
        yield f"--{boundary}--\r\n".encode()

    return HttpResponse(file_iterator(), content_type=content_type)

# WADO-URI
@router.get("/wado")
@machine_only
def wado_uri(request, requestType: str, studyUID: str, seriesUID: str, objectUID: str, contentType: str = "application/dicom"):
    if requestType != "WADO":
        return HttpResponse("Invalid requestType", status=400)

    dicom_file = get_object_or_404(
        _readable(request),
        sop_instance_uid=objectUID,
        series__series_instance_uid=seriesUID,
        series__study__study_instance_uid=studyUID
    )
    audit_client_access(request, [dicom_file])
    return FileResponse(dicom_file.file.open('rb'), content_type="application/dicom")

# WADO-RS Retrieve Study
@router.get("/studies/{study_instance_uid}")
@machine_only
def retrieve_study(request, study_instance_uid: str):
    dicom_files = list(_readable(request).filter(series__study__study_instance_uid=study_instance_uid))
    if not dicom_files:
        return HttpResponse(status=404)
    audit_client_access(request, dicom_files)
    return multipart_related_response([df.file for df in dicom_files])

# WADO-RS Retrieve Series
@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}")
@machine_only
def retrieve_series(request, study_instance_uid: str, series_instance_uid: str):
    dicom_files = list(_readable(request).filter(
        series__series_instance_uid=series_instance_uid,
        series__study__study_instance_uid=study_instance_uid
    ))
    if not dicom_files:
        return HttpResponse(status=404)
    audit_client_access(request, dicom_files)
    return multipart_related_response([df.file for df in dicom_files])

# WADO-RS Retrieve Instance
@router.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances/{sop_instance_uid}")
@machine_only
def retrieve_instance(request, study_instance_uid: str, series_instance_uid: str, sop_instance_uid: str):
    dicom_file = get_object_or_404(
        _readable(request),
        sop_instance_uid=sop_instance_uid,
        series__series_instance_uid=series_instance_uid,
        series__study__study_instance_uid=study_instance_uid
    )
    audit_client_access(request, [dicom_file])
    return multipart_related_response([dicom_file.file])
