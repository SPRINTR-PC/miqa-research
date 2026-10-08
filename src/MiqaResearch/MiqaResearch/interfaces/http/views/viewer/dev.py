"""Temporary viewer host page (#278) until the viewer entry contract (#184/#279) lands.

DEBUG-only: checked per request (not at URLconf import) so it is a 404 whenever DEBUG
is off. No visibility check here on purpose: the page holds no data, and every WADO
request the viewer makes is checked for Participant Visibility server-side (#276).

`can_annotate` (#280) only gates the viewer's annotate tools (Arrow, Calibrate, segment
tools, Save); saving is authorised again server-side (#287). `participant` (#292) is the
series' Study Participant id, given only when visible: the viewer lists the participant's
Annotations (bulk ANN on a slide) through the object API, which checks visibility again.
`related` (#284, repeated or comma-separated series UIDs of the same study) lists more series to
drag onto the view (fuse / replace), limited by Participant Visibility (#271); WADO checks it again.
`user` (#291, the user's pk, in the template) keys the viewer's IndexedDB drafts per user.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from MiqaResearch.data.models import DicomSeries
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.participant_visibility import can_see_participant, visible_participants_in_any_project


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
    project_id = participant.research_project_id
    visible = can_see_participant(user, project_id, participant)
    return (str(participant.pk) if visible else ""), ParticipantRights(user, project_id, participant).can_author


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
        "related_series": " ".join(_visible_related(request.user, request.GET.getlist("related"))),
    })


def _visible_related(user, values: list[str]) -> list[str]:
    """The `related` series UIDs, in order, limited by Participant Visibility (unknown ones dropped)."""
    uids = [uid.strip() for value in values for uid in value.split(",") if uid.strip()]
    if not uids:
        return []
    visible = set(
        DicomSeries.objects.filter(series_instance_uid__in=uids)
        .filter(Exists(visible_participants_in_any_project(user).filter(pk=OuterRef("study__study_participant"))))
        .values_list("series_instance_uid", flat=True)
    )
    return [uid for uid in dict.fromkeys(uids) if uid in visible]
