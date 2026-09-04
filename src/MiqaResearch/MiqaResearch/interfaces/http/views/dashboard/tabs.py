from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from .htmx_auth import htmx_login_required
from .project import get_user_project_or_404


def _htmx_tab_response(request, panel_template, project, active_tab):
    panel_html = render_to_string(panel_template, {'project': project}, request=request)
    tablist_html = render_to_string(
        '01_dashboard/_tablist.html', {'project': project, 'active_tab': active_tab, 'oob': True}, request=request
    )
    return HttpResponse(panel_html + tablist_html)


@htmx_login_required
async def consent_statistics(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return _htmx_tab_response(
            request, '01_dashboard/_panel_consent_statistics.html', research_project, 'consent-statistics'
        )

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'consent-statistics'},
    )


@htmx_login_required
async def goals(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return _htmx_tab_response(request, '01_dashboard/_panel_goals.html', research_project, 'goals')

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'goals'},
    )
