"""Data-access audit entries for image reads over WADO (ADR 0024, ADR 0027, #271 story 21).

- client callers: one entry per client x series x access token, whatever the endpoint;
- session callers (the viewer): one entry per series opened per viewer open (Viewer Session id,
  else the login session), written by the series `/metadata` the viewer opens a series with;
  frames are never audited one by one.

Repeats are dropped by the entry's dedupe key within the same INSERT. `dicom_files` must have
`series__study__study_participant` loaded.
"""
from contract.constants.audit_log import EVENT_TYPE_VIEWER_SERIES_OPENED, EVENT_TYPE_WADO_CLIENT_ACCESS
from helpers.http import get_client_ip
from MiqaResearch.data.models import AuditLog
from MiqaResearch.readers.blinding import viewer_session_id


def _series_of(dicom_files) -> list:
    return list({dicom_file.series_id: dicom_file.series for dicom_file in dicom_files}.values())


def _series_metadata(series, request) -> dict:
    return {
        "study_instance_uid": series.study.study_instance_uid,
        "series_instance_uid": series.series_instance_uid,
        "path": request.path,
    }


def audit_client_access(request, application, dicom_files) -> None:
    token = request.access_token
    AuditLog.objects.bulk_create([
        AuditLog(
            event_type=EVENT_TYPE_WADO_CLIENT_ACCESS,
            ip_address=get_client_ip(request),
            project_id=series.study.study_participant.research_project_id,
            dedupe_key=f"wado-client:{token.pk}:{series.pk}",
            metadata={
                "client_id": application.client_id,
                "application_id": application.pk,
                "access_token_id": token.pk,
                **_series_metadata(series, request),
            },
        )
        for series in _series_of(dicom_files)
    ], ignore_conflicts=True)


def audit_viewer_series_open(request, user, dicom_files) -> None:
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    viewer = viewer_session_id(request)
    open_key = viewer or session_key
    AuditLog.objects.bulk_create([
        AuditLog(
            event_type=EVENT_TYPE_VIEWER_SERIES_OPENED,
            user=user,
            ip_address=get_client_ip(request),
            session_key=session_key,
            project_id=series.study.study_participant.research_project_id,
            dedupe_key=f"viewer-open:{user.pk}:{open_key}:{series.pk}" if open_key else None,
            metadata={"viewer_session": viewer, **_series_metadata(series, request)},
        )
        for series in _series_of(dicom_files)
    ], ignore_conflicts=True)
