"""DEBUG-only viewer host page for the browser harness (#278), on the viewer page's input since #279.

`/viewer/dev/?series=<uid>&related=<uid>,…` names series of any participant by raw (pseudonymized) UID,
so the Playwright harness can drive arbitrary seeded series. It builds the same JSON series list as the
viewer page, through `dev_viewer_series`: the opened series, then `related` (repeated or comma-separated),
left out when outside Participant Visibility. Checked per request (not at URLconf import), so it is a 404
whenever DEBUG is off. It writes no `viewer_open` audit entry; every WADO request is still checked and
audited server-side.

`participant` is the first opened series' Study Participant, given only when visible; `can_annotate` only
gates the viewer's annotate tools (saving is authorised again server-side).
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from MiqaResearch.data.models import DicomSeries
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.viewer_launch import dev_viewer_series


def _uids(values: list[str]) -> list[str]:
    return [uid.strip() for value in values for uid in value.split(",") if uid.strip()]


# The viewer's POSTs (first-render beacon, saves) send the csrftoken cookie as X-CSRFToken.
@login_required
@ensure_csrf_cookie
def dev(request):
    if not settings.DEBUG:
        raise Http404
    opened, related = _uids(request.GET.getlist("series")), _uids(request.GET.getlist("related"))
    series = dev_viewer_series(request.user, opened, related)
    participant, can_annotate = None, False
    if series:
        participant = DicomSeries.objects.select_related("study__study_participant").get(
            series_instance_uid=series[0]["series"]
        ).study.study_participant
        can_annotate = ParticipantRights(request.user, participant.research_project_id, participant).can_author
    return render(request, "05_viewer/dev.html", {
        "series": series,
        "participant": participant,
        "can_annotate": can_annotate,
    })
