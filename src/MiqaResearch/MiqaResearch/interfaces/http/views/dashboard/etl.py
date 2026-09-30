"""Endpoints for the ETL Pipelines tab beyond its section listings: the manage actions (#158) --
create/edit/archive a custom Script, add a Version, create a Binding, edit the project's ETL
settings overrides -- and a Job's detail view (#164). Every view
resolves the project through `get_user_etl_project_or_404` first, which 404s a user who can't even
view the tab; a view whose action needs more than that (manage, or admin-only manage) then checks
`etl_permissions` itself and responds 403 -- the page exists for them, the action doesn't.
"""
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import aget_object_or_404

from MiqaResearch.actions.etl.bindings import create_pipeline_binding
from MiqaResearch.actions.etl.exceptions import EtlActionError
from MiqaResearch.actions.etl.jobs import retry_failed_job
from MiqaResearch.actions.etl.scripts import (
    archive_custom_script,
    create_custom_script,
    create_script_version,
    update_custom_script,
)
from MiqaResearch.actions.etl.settings import update_etl_project_settings
from MiqaResearch.data.models import EtlScript
from MiqaResearch.interfaces.http.forms.etl import (
    EtlBindingCreateForm,
    EtlProjectSettingsForm,
    EtlScriptCreateForm,
    EtlScriptEditForm,
    EtlScriptVersionCreateForm,
)
from MiqaResearch.readers.etl_reader import (
    get_bindable_script_version_choices,
    get_project_job,
    get_project_location_grants,
    get_project_max_script_source_bytes,
)

from .htmx_auth import htmx_login_required
from .project import get_user_etl_project_or_404
from .tabs import (
    _ETL_SECTION_PANELS,
    ETL_SECTION_BINDINGS,
    ETL_SECTION_DEFAULTS,
    ETL_SECTION_JOBS,
    ETL_SECTION_SCRIPTS,
    _htmx_tab_response,
    etl_section_context,
)


async def _rerender_section(request, project, permissions, section, *, manage_error=None):
    section_context = await etl_section_context(project, permissions, section)
    if manage_error:
        section_context['manage_error'] = manage_error
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[section], project, 'etl-pipelines',
        extra_context={'etl_section': section} | section_context, with_sidebar=True,
    )


async def _attempt(action) -> str | None:
    """Awaits an Action coroutine, returning its message on an `EtlActionError` (e.g. the target
    Script is archived or not this project's own) so a caller can surface it, or None on success.
    """
    try:
        await action
        return None
    except EtlActionError as error:
        return str(error)


@htmx_login_required
async def etl_scripts_create(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    user = await request.auser()
    max_source_bytes = await get_project_max_script_source_bytes(research_project)
    form = EtlScriptCreateForm(request.POST, request.FILES, max_source_bytes=max_source_bytes)
    if form.is_valid():
        await create_custom_script(
            project=research_project, user=user, request=request,
            name=form.cleaned_data['name'], description=form.cleaned_data['description'],
            source=form.cleaned_data['source'],
        )
        form = EtlScriptCreateForm(max_source_bytes=max_source_bytes)

    section_context = await etl_section_context(research_project, permissions, ETL_SECTION_SCRIPTS)
    section_context['script_create_form'] = form
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_SCRIPTS], research_project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_SCRIPTS} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_script_edit(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    form = EtlScriptEditForm(request.POST)
    error = None
    if form.is_valid():
        error = await _attempt(update_custom_script(
            project=research_project, user=user, request=request, script=script,
            name=form.cleaned_data['name'], description=form.cleaned_data['description'],
        ))

    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error)


@htmx_login_required
async def etl_script_version_create(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    max_source_bytes = await get_project_max_script_source_bytes(research_project)
    form = EtlScriptVersionCreateForm(request.POST, request.FILES, max_source_bytes=max_source_bytes)
    error = None
    if form.is_valid():
        error = await _attempt(create_script_version(
            project=research_project, user=user, request=request, script=script,
            source=form.cleaned_data['source'],
        ))

    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error)


@htmx_login_required
async def etl_script_archive(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage_admin_only:
        return HttpResponseForbidden()

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    error = await _attempt(archive_custom_script(project=research_project, user=user, request=request, script=script))

    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error)


@htmx_login_required
async def etl_bindings_create(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    user = await request.auser()
    location_grants = await get_project_location_grants(research_project)
    choices = await get_bindable_script_version_choices(research_project)

    form = EtlBindingCreateForm(request.POST, location_grants=location_grants, script_version_choices=choices)
    if form.is_valid():
        try:
            await create_pipeline_binding(
                project=research_project, user=user, request=request,
                source_bucket=form.cleaned_data['source_bucket'],
                source_prefix=form.cleaned_data['source_prefix'],
                script_version_id=form.cleaned_data['script_version'],
                raw_bucket=form.cleaned_data['raw_bucket'],
                raw_prefix=form.cleaned_data['raw_prefix'],
                timeout_seconds_override=form.cleaned_data['timeout_seconds_override'],
                memory_mb_override=form.cleaned_data['memory_mb_override'],
                cpu_millicores_override=form.cleaned_data['cpu_millicores_override'],
            )
            form = EtlBindingCreateForm(location_grants=location_grants, script_version_choices=choices)
        except EtlActionError as error:
            form.add_error(None, str(error))

    section_context = await etl_section_context(research_project, permissions, ETL_SECTION_BINDINGS)
    section_context['binding_create_form'] = form
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_BINDINGS], research_project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_BINDINGS} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_defaults_update(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage_admin_only:
        return HttpResponseForbidden()

    user = await request.auser()
    form = EtlProjectSettingsForm(request.POST)
    if form.is_valid():
        await update_etl_project_settings(
            project=research_project, user=user, request=request,
            log_retention_days=form.cleaned_data['log_retention_days'],
            max_script_source_bytes=form.cleaned_data['max_script_source_bytes'],
        )

    section_context = await etl_section_context(research_project, permissions, ETL_SECTION_DEFAULTS)
    if not form.is_valid():
        section_context['settings_form'] = form
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_DEFAULTS], research_project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_DEFAULTS} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_job_detail(request, project_id, job_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    return await _render_job_detail(request, research_project, permissions, job_id)


@htmx_login_required
async def etl_job_retry(request, project_id, job_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    job = await get_project_job(research_project, job_id)
    if job is None:
        raise Http404
    user = await request.auser()
    try:
        retry_job = await retry_failed_job(project=research_project, user=user, request=request, job=job)
    except EtlActionError as error:
        return await _render_job_detail(request, research_project, permissions, job.id, manage_error=str(error))

    return await _render_job_detail(request, research_project, permissions, retry_job.id)


async def _render_job_detail(request, project, permissions, job_id, *, manage_error=None):
    job = await get_project_job(project, job_id)
    if job is None:
        raise Http404
    return _htmx_tab_response(
        request, '01_dashboard/_panel_etl_job_detail.html', project, 'etl-pipelines',
        extra_context={
            'etl_section': ETL_SECTION_JOBS, 'etl_permissions': permissions, 'job': job, 'manage_error': manage_error,
        },
        with_sidebar=True,
    )
