from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import aget_object_or_404, render
from django.utils.translation import gettext

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.readers.etl_permissions import EtlPermissions, get_etl_permissions
from MiqaResearch.readers.participant_consent_reader import (
    get_project_consent_count,
    get_project_consent_participant_count,
)
from MiqaResearch.readers.research_project_reader import get_project_connected_clinics


async def get_user_project_or_404(request, project_id):
    user = await request.auser()
    return await aget_object_or_404(
        ResearchProject.objects.filter(researchprojectuserrolemap__user=user).distinct(),
        id=project_id,
    )


async def get_user_etl_project_or_404(request, project_id) -> tuple[ResearchProject, EtlPermissions]:
    """Like `get_user_project_or_404`, narrowed to the ETL Pipelines tab: a user who is a project
    member but holds none of the ETL-visible roles gets the same 404 as a non-member -- the page
    doesn't exist for them, it isn't merely forbidden.
    """
    research_project = await get_user_project_or_404(request, project_id)
    permissions = await get_etl_permissions(request, research_project)
    if not permissions.can_view:
        raise Http404()
    return research_project, permissions


@login_required
async def project(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    return render(
        request,
        "01_dashboard/project.html",
        {
            "project": research_project,
            "active_tab": "consent-statistics",
            "active_subtab": "consent-statistics-plots",
            "consent_counts": await get_project_consent_count(project=research_project),
            "participant_count": await get_project_consent_participant_count(project=research_project),
            "site_options": [{"value": 0, "label": gettext("All sites")}]
            + [
                {"value": clinic["clinic_id"], "label": clinic["clinic_name"]}
                for clinic in await get_project_connected_clinics(project_id=research_project.id)
            ],
        },
    )
