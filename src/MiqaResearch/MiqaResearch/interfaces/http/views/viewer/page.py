"""The viewer page (#279) on the entry contract decided in #184.

`/projects/<project>/participants/<participant>/viewer/?series=<uid>&series=…` opens the listed series
(first = base, the rest fused onto it) in a standalone page hosting `<mires-viewer>`. Series are the
pseudonymized UIDs, so no PHI is in the URL. Anything the user can't see is a 404 for the whole page.

Each page load is one Viewer Session: the page makes its id, audits the open under it (`viewer_open`) and
hands it to the viewer, which sends it with every request (Blinding Reveals, per-series audit).
"""
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.csrf import ensure_csrf_cookie

from MiqaResearch.actions.image_access_audit import audit_viewer_open
from MiqaResearch.readers.annotation_permissions import ParticipantRights
from MiqaResearch.readers.viewer_launch import ViewerOpenNotFound, viewer_participant, viewer_series


def viewer_url(project_id, participant_id, series_uids: list[str]) -> str:
    """The page URL opening `series_uids` (first = base) for a participant: what launch links point at."""
    path = reverse("viewer_page", kwargs={"project_id": project_id, "participant_id": participant_id})
    return f"{path}?{urlencode({'series': series_uids}, doseq=True)}"


# The viewer's POSTs (first-render beacon, saves) send the csrftoken cookie as X-CSRFToken.
@login_required
@ensure_csrf_cookie
def viewer_page(request, project_id, participant_id):
    try:
        participant = viewer_participant(request.user, project_id, participant_id)
        series = viewer_series(participant, request.GET.getlist("series"))
    except ViewerOpenNotFound:
        raise Http404 from None
    viewer_session = str(uuid4())
    audit_viewer_open(request, participant, [row["series"] for row in series if row["open"]], viewer_session)
    return render(request, "05_viewer/page.html", {
        "participant": participant,
        "series": series,
        "viewer_session": viewer_session,
        "can_annotate": ParticipantRights(request.user, project_id, participant).can_author,
    })
