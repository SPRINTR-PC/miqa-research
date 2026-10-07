"""Temporary viewer host page (#278) until the viewer entry contract (#184/#279) lands.

DEBUG-only: checked per request (not at URLconf import) so it is a 404 whenever DEBUG
is off. No visibility check here on purpose: the page holds no data, and every WADO
request the viewer makes is checked for Participant Visibility server-side (#276).

`can_annotate` (#280) only gates the viewer's annotate tools (Arrow, Calibrate, segment
tools, Save); saving is authorised again server-side (#287).
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from MiqaResearch.data.models import DicomSeries
from MiqaResearch.readers.annotation_permissions import ParticipantRights


def _can_annotate(user, series_uid: str) -> bool:
    series = (
        DicomSeries.objects.select_related("study__study_participant")
        .filter(series_instance_uid=series_uid)
        .first()
    )
    if series is None:
        return False
    participant = series.study.study_participant
    return ParticipantRights(user, participant.research_project_id, participant).can_author


@login_required
def dev(request):
    if not settings.DEBUG:
        raise Http404
    series_uid = request.GET.get("series", "")
    return render(request, "05_viewer/dev.html", {
        "study_uid": request.GET.get("study", ""),
        "series_uid": series_uid,
        "can_annotate": bool(series_uid) and _can_annotate(request.user, series_uid),
    })
