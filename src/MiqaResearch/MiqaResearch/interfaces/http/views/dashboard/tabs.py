from gettext import gettext

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from MiqaResearch.readers.participant_consent_reader import get_project_consent_count, \
    get_project_consent_participant_count
from MiqaResearch.readers.research_project_reader import get_project_connected_clinics
from .htmx_auth import htmx_login_required
from .project import get_user_project_or_404


def _htmx_tab_response(request, panel_template, project, active_tab, active_subtab = None, extra_context: dict = {}):
    panel_html = render_to_string(panel_template, {'project': project} | extra_context, request=request)
    tablist_html = render_to_string(
        '01_dashboard/_tablist.html',
        {'project': project, 'active_tab': active_tab, 'active_subtab': active_subtab, 'oob': True} | extra_context,
        request=request
    )
    return HttpResponse(panel_html + tablist_html)


@htmx_login_required
async def consent_statistics(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    sites = [
        {"value": clinic["clinic_id"], "label": clinic["clinic_name"]}
        for clinic in await get_project_connected_clinics(project_id=research_project.id)
    ]

    site_options = {
        "consent_counts": await get_project_consent_count(project=research_project),
        "site_count": len(sites),
        "site_options": [{"value": 0, "label": gettext("All sites")}] + sites
    }

    active_subtab = "consent-statistics-table" if request.GET.get("table") else "consent-statistics-plots"

    if request.htmx:
        return _htmx_tab_response(
            request, '01_dashboard/_panel_consent_statistics.html', research_project, 'consent-statistics',
            active_subtab, extra_context=site_options
        )

    site_options["participant_count"] = await get_project_consent_participant_count(project=research_project)

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'consent-statistics', 'active_subtab': active_subtab} | site_options,
    )

@htmx_login_required
async def consent_statistics_content(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        template, active_subtab = (
            ('01_dashboard/_panel_consent_statistics_table.html', 'consent-statistics-table')
            if request.GET.get("table") else
            ('01_dashboard/_panel_consent_statistics_plots.html', 'consent-statistics-plots')
        )
        return _htmx_tab_response(
            request, template, research_project, 'consent-statistics',
            active_subtab
        )

    return await consent_statistics(request, project_id)



@htmx_login_required
async def consent_statistics_table(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return _htmx_tab_response(
            request, '01_dashboard/_panel_consent_statistics_table.html', research_project, 'consent-statistics',
            'consent-statistics-table'
        )

    return await consent_statistics(request, project_id)


@htmx_login_required
async def goals(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if request.htmx:
        return _htmx_tab_response(request, '01_dashboard/_panel_goals.html', research_project, 'goals')

    sites = [
        {"value": clinic["clinic_id"], "label": clinic["clinic_name"]}
        for clinic in await get_project_connected_clinics(project_id=research_project.id)
    ]

    site_options = {
        "consent_counts": await get_project_consent_count(project=research_project),
        "participant_count": await get_project_consent_participant_count(project=research_project),
        "site_count": len(sites),
        "site_options": [{"value": 0, "label": gettext("All sites")}] + sites,
    }

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'goals'} | site_options,
    )
