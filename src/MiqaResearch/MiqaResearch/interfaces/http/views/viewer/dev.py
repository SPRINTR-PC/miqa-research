"""Temporary viewer host page (#278) until the viewer entry contract (#184/#279) lands.

DEBUG-only: checked per request (not at URLconf import) so it is a 404 whenever DEBUG
is off. No visibility check here on purpose: the page holds no data, and every WADO
request the viewer makes is checked for Participant Visibility server-side (#276).
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render


@login_required
def dev(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "05_viewer/dev.html", {
        "study_uid": request.GET.get("study", ""),
        "series_uid": request.GET.get("series", ""),
    })
