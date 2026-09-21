from gettext import gettext

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from MiqaResearch.readers.participant_consent_reader import get_project_consent_count, \
    get_project_consent_participant_count, user_can_view_consent_pid
from MiqaResearch.readers.research_project_reader import get_project_connected_clinics
from .htmx_auth import htmx_login_required
from .project import get_user_project_or_404


SUBTAB_PLOTS = "consent-statistics-plots"
SUBTAB_TABLE = "consent-statistics-table"
_SUBTAB_PANELS = {
    SUBTAB_PLOTS: "01_dashboard/_panel_consent_statistics_plots.html",
    SUBTAB_TABLE: "01_dashboard/_panel_consent_statistics_table.html",
}


def _consent_subtab(request) -> str:
    return SUBTAB_TABLE if request.GET.get("table", "").lower() == "true" else SUBTAB_PLOTS


async def _table_context(request, project, active_subtab) -> dict:
    """
    Context for the consent table panel: whether the PID checkbox is offered. Only computed for the table sub tab.
    """
    if active_subtab != SUBTAB_TABLE:
        return {}
    return {'can_view_pid': await user_can_view_consent_pid(await request.auser(), project)}


def _is_partial_request(request) -> bool:
    """
    An htmx swap wants a fragment. A history restore after a cache miss is also sent by htmx, but its response replaces
    the whole body, so it needs the full page.
    """
    return bool(request.htmx) and not request.htmx.history_restore_request


def _htmx_tab_response(
        request, panel_template, project, active_tab, active_subtab=None, extra_context: dict | None = None,
        with_subtablist: bool = False):
    """
    The panel for the swap target plus out-of-band tab lists, so the highlighted tab and sub tab always match the panel.
    `with_subtablist` is for swaps that replace only the sub tab's content, where the sub tab list is not in the target.
    """
    context = {
        'project': project, 'active_tab': active_tab, 'active_subtab': active_subtab, 'oob': True,
    } | (extra_context or {})
    panel_html = render_to_string(panel_template, context | {'oob': False}, request=request)
    tablist_html = render_to_string('01_dashboard/_tablist.html', context, request=request)
    subtablist_html = (
        render_to_string('01_dashboard/_panel_consent_statistics_tablist.html', context, request=request)
        if with_subtablist else ""
    )
    return HttpResponse(panel_html + tablist_html + subtablist_html)


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

    active_subtab = _consent_subtab(request)
    site_options |= await _table_context(request, research_project, active_subtab)

    if _is_partial_request(request):
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

    if _is_partial_request(request):
        active_subtab = _consent_subtab(request)
        return _htmx_tab_response(
            request, _SUBTAB_PANELS[active_subtab], research_project, 'consent-statistics', active_subtab,
            extra_context=await _table_context(request, research_project, active_subtab), with_subtablist=True
        )

    return await consent_statistics(request, project_id)


@htmx_login_required
async def consent_statistics_table(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if _is_partial_request(request):
        return _htmx_tab_response(
            request, _SUBTAB_PANELS[SUBTAB_TABLE], research_project, 'consent-statistics', SUBTAB_TABLE,
            extra_context=await _table_context(request, research_project, SUBTAB_TABLE), with_subtablist=True
        )

    return await consent_statistics(request, project_id)


@htmx_login_required
async def goals(request, project_id):
    research_project = await get_user_project_or_404(request, project_id)

    if _is_partial_request(request):
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
