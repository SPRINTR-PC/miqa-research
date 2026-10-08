"""Temporary viewer host page (#278) until the viewer entry contract (#184/#279) lands.

DEBUG-only: checked per request (not at URLconf import) so it is a 404 whenever DEBUG
is off. No visibility check here on purpose: the page holds no data, and every WADO
request the viewer makes is checked for Participant Visibility server-side (#276).

`can_annotate` (#280) only gates the viewer's annotate tools (Arrow, Calibrate, segment
tools, Save); saving is authorised again server-side (#287). `participant` (#292) is the
series' Study Participant id, given only when visible: the viewer lists the participant's
Annotations (bulk ANN on a slide) through the object API, which checks visibility again.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from MiqaResearch.data.models import DicomSeries
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.participant_visibility import can_see_participant


def _participant_rights(user, series_uid: str) -> tuple[str, bool]:
    """(participant id if visible, else ""; can annotate) for the series' participant."""
    series = (
        DicomSeries.objects.select_related("study__study_participant")
        .filter(series_instance_uid=series_uid)
        .first()
    )
    if series is None:
        return "", False
    participant = series.study.study_participant
    project = participant.research_project_id
    visible = can_see_participant(user, project, participant)
    return (str(participant.pk) if visible else ""), ParticipantRights(user, project, participant).can_author


# The viewer's POSTs (first-render beacon, saves) send the csrftoken cookie as X-CSRFToken.
@login_required
@ensure_csrf_cookie
def dev(request):
    if not settings.DEBUG:
        raise Http404
    series_uid = request.GET.get("series", "")
    participant, can_annotate = _participant_rights(request.user, series_uid) if series_uid else ("", False)
    return render(request, "05_viewer/dev.html", {
        "study_uid": request.GET.get("study", ""),
        "series_uid": series_uid,
        "can_annotate": can_annotate,
        "participant": participant,
    })
