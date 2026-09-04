from django.contrib.auth.decorators import login_required
from django.shortcuts import aget_object_or_404, render

from MiqaResearch.data.models import ResearchProject


async def get_user_project_or_404(request, project_id):
    user = await request.auser()
    return await aget_object_or_404(
        ResearchProject.objects.filter(researchprojectuserrolemap__user=user).distinct(),
        id=project_id,
    )


@login_required
async def project(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)
    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'consent-statistics'},
    )
