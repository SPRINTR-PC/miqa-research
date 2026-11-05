from gettext import gettext

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from MiqaResearch.interfaces.http.forms.etl import (
    EtlBindingCreateForm,
    EtlBindingEditForm,
    EtlLocationGrantForm,
    EtlProjectSettingsForm,
    EtlSourceLocationForm,
)
from MiqaResearch.readers.etl_reader import (
    get_bindable_script_versions,
    get_native_scripts,
    get_project_bindings,
    get_project_jobs,
    get_project_location_grants,
    get_project_settings,
    get_project_source_locations,
    script_version_choices,
    script_version_config_schemas,
)
from MiqaResearch.readers.participant_consent_reader import (
    get_project_consent_count,
    get_project_consent_participant_count,
    user_can_view_consent_pid,
)
from MiqaResearch.readers.research_project_reader import get_project_connected_clinics

from .htmx_auth import htmx_login_required
from .project import get_user_etl_project_or_404, get_user_project_or_404

SUBTAB_PLOTS = "consent-statistics-plots"
SUBTAB_TABLE = "consent-statistics-table"
_SUBTAB_PANELS = {
    SUBTAB_PLOTS: "01_dashboard/_panel_consent_statistics_plots.html",
    SUBTAB_TABLE: "01_dashboard/_panel_consent_statistics_table.html",
}

ETL_SECTION_BINDINGS = "bindings"
ETL_SECTION_SCRIPTS = "scripts"
ETL_SECTION_JOBS = "jobs"
ETL_SECTION_DEFAULTS = "defaults"
ETL_SECTION_SOURCES = "sources"
_ETL_SECTIONS = [ETL_SECTION_BINDINGS, ETL_SECTION_SCRIPTS, ETL_SECTION_JOBS, ETL_SECTION_DEFAULTS, ETL_SECTION_SOURCES]
_ETL_SECTION_PANELS = {
    ETL_SECTION_BINDINGS: "01_dashboard/_panel_etl_bindings.html",
    ETL_SECTION_SCRIPTS: "01_dashboard/_panel_etl_scripts.html",
    ETL_SECTION_JOBS: "01_dashboard/_panel_etl_jobs.html",
    ETL_SECTION_DEFAULTS: "01_dashboard/_panel_etl_defaults.html",
    ETL_SECTION_SOURCES: "01_dashboard/_panel_etl_sources.html",
}


def _etl_section(request, permissions) -> str:
    """The requested section; the Sources section 404s for a viewer who may not see it (#268)."""
    section = request.GET.get("section", ETL_SECTION_BINDINGS)
    if section == ETL_SECTION_SOURCES and not permissions.can_manage_source_locations:
        raise Http404()
    return section if section in _ETL_SECTIONS else ETL_SECTION_BINDINGS


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
        with_subtablist: bool = False, with_sidebar: bool = False):
    """
    The panel for the swap target plus out-of-band tab lists, so the highlighted tab and sub tab always match the panel.
    `with_subtablist` is for swaps that replace only the sub tab's content, where the sub tab list is not in the target.
    `with_sidebar` is the ETL Pipelines tab's equivalent, for swaps that replace only a section's content.
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
    sidebar_html = (
        render_to_string('01_dashboard/_etl_sidebar.html', context, request=request)
        if with_sidebar else ""
    )
    return HttpResponse(panel_html + tablist_html + subtablist_html + sidebar_html)


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


def _binding_edit_initial(binding) -> dict:
    return {
        'script_version': str(binding.script_version_id), 'raw_retention': binding.raw_retention,
        'raw_bucket': binding.raw_bucket, 'raw_prefix': binding.raw_prefix,
        'grouping_mode': binding.grouping_mode, 'quiescence_seconds': binding.quiescence_seconds,
        'config': binding.config,
        'timeout_seconds_override': binding.timeout_seconds_override,
        'memory_mb_override': binding.memory_mb_override,
        'cpu_millicores_override': binding.cpu_millicores_override,
    }


def binding_edit_auto_id(binding) -> str:
    """Field ids for one Binding's Edit form -- unique per Binding, since every Edit form shares the
    page. The config-fields swap (#238) must render with the same ids its form already uses."""
    return f"id_binding_{binding.id}_%s"


async def binding_form_kwargs(project, permissions) -> dict:
    """What every Binding wizard/Edit form is built with: the project's location grants and bindable
    Script Versions with their config schemas (pre-fetched -- a form can't query the DB inside an
    async view), and whether this user may choose "delete" Raw Retention (Admin only, #246)."""
    versions = await get_bindable_script_versions(project)
    return {
        'location_grants': await get_project_location_grants(project),
        'script_version_choices': script_version_choices(versions),
        'config_schemas': script_version_config_schemas(versions),
        'can_choose_delete': permissions.can_manage_admin_only,
    }


async def etl_section_context(project, permissions, section) -> dict:
    """Section-specific read data and unbound manage forms for the ETL Pipelines tab. Forms are
    only built for a section's manage-capable viewers -- a read-only viewer gets the listings but
    no form, so a template can key rendering of manage controls off the form's presence alone.
    """
    context = {'etl_permissions': permissions}

    if section == ETL_SECTION_SCRIPTS:
        context['native_scripts'] = await get_native_scripts()

    elif section == ETL_SECTION_BINDINGS:
        context['bindings'] = await get_project_bindings(project)
        if permissions.can_manage:
            form_kwargs = await binding_form_kwargs(project, permissions)
            context['source_locations'] = await get_project_source_locations(project)
            context['binding_create_form'] = EtlBindingCreateForm(
                **form_kwargs, source_locations=context['source_locations'])
            for binding in context['bindings']:
                binding.edit_form = EtlBindingEditForm(
                    **form_kwargs, current_raw_retention=binding.raw_retention,
                    initial=_binding_edit_initial(binding), auto_id=binding_edit_auto_id(binding),
                )

    elif section == ETL_SECTION_JOBS:
        context['jobs'] = await get_project_jobs(project)

    elif section == ETL_SECTION_DEFAULTS:
        context['native_scripts'] = await get_native_scripts()
        if permissions.can_manage_admin_only:
            settings_obj = await get_project_settings(project)
            initial = {
                'log_retention_days': settings_obj.log_retention_days,
                'max_script_source_bytes': settings_obj.max_script_source_bytes,
            } if settings_obj else {}
            context['settings_form'] = EtlProjectSettingsForm(initial=initial)

    elif section == ETL_SECTION_SOURCES:
        context['location_grants'] = await get_project_location_grants(project)
        context['source_locations'] = await get_project_source_locations(project)
        if permissions.can_manage_source_locations:
            context['source_location_form'] = EtlSourceLocationForm()
        if permissions.can_manage_location_grants:
            context['location_grant_form'] = EtlLocationGrantForm()

    return context


@htmx_login_required
async def etl_pipelines(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    etl_section = _etl_section(request, permissions)
    section_context = await etl_section_context(research_project, permissions, etl_section)

    if _is_partial_request(request):
        return _htmx_tab_response(
            request, '01_dashboard/_panel_etl_pipelines.html', research_project, 'etl-pipelines',
            extra_context={'etl_section': etl_section} | section_context,
        )

    return render(
        request,
        '01_dashboard/project.html',
        {'project': research_project, 'active_tab': 'etl-pipelines', 'etl_section': etl_section} | section_context,
    )


@htmx_login_required
async def etl_pipelines_content(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)

    if _is_partial_request(request):
        etl_section = _etl_section(request, permissions)
        section_context = await etl_section_context(research_project, permissions, etl_section)
        return _htmx_tab_response(
            request, _ETL_SECTION_PANELS[etl_section], research_project, 'etl-pipelines',
            extra_context={'etl_section': etl_section} | section_context, with_sidebar=True,
        )

    return await etl_pipelines(request, project_id)
