from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from MiqaResearch.data.models import ParticipantConsent


@login_required()
def list_consents(request, *args, **kwargs):
    consent_list = ParticipantConsent.objects.filter_by_user_permissions(request.user)
    context = {}
    render(request, "consent/list_consent.html", context=context)