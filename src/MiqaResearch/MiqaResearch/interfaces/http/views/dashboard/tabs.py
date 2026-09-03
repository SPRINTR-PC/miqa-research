from django.shortcuts import render

from .htmx_auth import htmx_login_required
from .project import get_user_project_or_404


@htmx_login_required
async def consent_statistics(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return render(request, '01_dashboard/_panel_consent_statistics.html', {'project': research_project})

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'consent-statistics'},
    )


@htmx_login_required
async def goals(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return render(request, '01_dashboard/_panel_goals.html', {'project': research_project})

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'goals'},
    )
