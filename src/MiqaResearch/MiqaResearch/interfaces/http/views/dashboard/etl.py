"""Endpoints for the ETL Pipelines tab beyond its section listings: the manage actions (#158) --
create/edit/archive a custom Script, add a Version, create a Binding, edit the project's ETL
settings overrides, manage Source Locations and location grants (#268) -- and a Job's detail view
(#164). The Sources section's endpoints 404 for a viewer who may not see that section. Every view
resolves the project through `get_user_etl_project_or_404` first, which 404s a user who can't even
view the tab; a view whose action needs more than that (manage, or admin-only manage) then checks
`etl_permissions` itself and responds 403 -- the page exists for them, the action doesn't.
"""
from uuid import UUID

from django.http import Http404, HttpResponseForbidden
from django.shortcuts import aget_object_or_404, render

from MiqaResearch.actions.etl.bindings import create_pipeline_binding, update_pipeline_binding
from MiqaResearch.actions.etl.exceptions import EtlActionError
from MiqaResearch.actions.etl.jobs import retry_failed_job
from MiqaResearch.actions.etl.scripts import (
    archive_custom_script,
    create_custom_script,
    create_script_version,
    customize_native_script,
    update_custom_script,
)
from MiqaResearch.actions.etl.settings import update_etl_project_settings
from MiqaResearch.actions.etl.sources import (
    create_location_grant,
    create_source_location,
    delete_location_grant,
    delete_source_location,
    rename_source_location,
)
from MiqaResearch.data.models import EtlLocationGrant, EtlScript, EtlSourceLocation, PipelineBinding
from MiqaResearch.interfaces.http.forms.etl import (
    EtlBindingCreateForm,
    EtlBindingEditForm,
    EtlLocationGrantForm,
    EtlProjectSettingsForm,
    EtlScriptCreateForm,
    EtlScriptEditForm,
    EtlScriptVersionCreateForm,
    EtlSourceLocationForm,
    EtlSourceLocationRenameForm,
)
from MiqaResearch.readers.etl_reader import (
    get_project_job,
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
    ETL_SECTION_SOURCES,
    _htmx_tab_response,
    binding_create_form_kwargs,
    binding_edit_auto_id,
    binding_form_kwargs,
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


def _form_errors(form) -> str:
    return " ".join(message for messages in form.errors.values() for message in messages)


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
            datatype_name=form.cleaned_data['datatype'], source=form.cleaned_data['source'],
            config_schema=form.cleaned_data['config_schema'],
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
            datatype_name=form.cleaned_data['datatype'],
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
            source=form.cleaned_data['source'], config_schema=form.cleaned_data['config_schema'],
        ))
    else:
        error = _form_errors(form)

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
async def etl_script_customize(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    native_script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    error = await _attempt(customize_native_script(
        project=research_project, user=user, request=request, native_script=native_script))

    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error)


@htmx_login_required
async def etl_bindings_create(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    user = await request.auser()
    form_kwargs = await binding_create_form_kwargs(research_project, permissions)

    form = EtlBindingCreateForm(request.POST, **form_kwargs)
    if form.is_valid():
        try:
            await create_pipeline_binding(
                project=research_project, user=user, request=request,
                source_location=form.cleaned_data['source_location'],
                script_version_id=form.cleaned_data['script_version'],
                raw_retention=form.cleaned_data['raw_retention'],
                raw_bucket=form.cleaned_data['raw_bucket'],
                raw_prefix=form.cleaned_data['raw_prefix'],
                grouping_mode=form.cleaned_data['grouping_mode'],
                quiescence_seconds=form.cleaned_data['quiescence_seconds'],
                config=form.cleaned_data['config'],
                timeout_seconds_override=form.cleaned_data['timeout_seconds_override'],
                memory_mb_override=form.cleaned_data['memory_mb_override'],
                cpu_millicores_override=form.cleaned_data['cpu_millicores_override'],
            )
            form = EtlBindingCreateForm(**form_kwargs)
        except EtlActionError as error:
            form.add_error(None, str(error))

    section_context = await etl_section_context(research_project, permissions, ETL_SECTION_BINDINGS)
    section_context['binding_create_form'] = form
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_BINDINGS], research_project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_BINDINGS} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_binding_edit(request, project_id, binding_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    binding = await aget_object_or_404(PipelineBinding, id=binding_id, project=research_project)
    user = await request.auser()
    form = EtlBindingEditForm(
        request.POST, **await binding_form_kwargs(research_project, permissions),
        current_raw_retention=binding.raw_retention, auto_id=binding_edit_auto_id(binding))
    if form.is_valid():
        error = await _attempt(update_pipeline_binding(
            project=research_project, user=user, request=request, binding=binding,
            script_version_id=form.cleaned_data['script_version'],
            raw_retention=form.cleaned_data['raw_retention'],
            raw_bucket=form.cleaned_data['raw_bucket'],
            raw_prefix=form.cleaned_data['raw_prefix'],
            grouping_mode=form.cleaned_data['grouping_mode'],
            quiescence_seconds=form.cleaned_data['quiescence_seconds'],
            config=form.cleaned_data['config'],
            timeout_seconds_override=form.cleaned_data['timeout_seconds_override'],
            memory_mb_override=form.cleaned_data['memory_mb_override'],
            cpu_millicores_override=form.cleaned_data['cpu_millicores_override'],
        ))
        if error is None:
            return await _rerender_section(request, research_project, permissions, ETL_SECTION_BINDINGS)
        form.add_error(None, error)

    # Rejected: re-open this Binding's Edit form with what was entered and each error beside its field.
    section_context = await etl_section_context(research_project, permissions, ETL_SECTION_BINDINGS)
    for listed in section_context['bindings']:
        if listed.id == binding.id:
            listed.edit_form, listed.edit_open = form, True
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_BINDINGS], research_project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_BINDINGS} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_binding_config_fields(request, project_id):
    """#238: the Binding wizard's/Edit form's config fields for the Script Version just chosen --
    generated from its config schema, or the free-form JSON box -- filled in with whatever config
    the form held: the request carries the whole form, its config fields as rendered for the
    Version named by `config_fields_for`."""
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    auto_id = 'id_%s'
    if binding_id := request.GET.get('binding'):
        binding = await aget_object_or_404(PipelineBinding, id=_uuid_or_404(binding_id), project=research_project)
        auto_id = binding_edit_auto_id(binding)
    form_kwargs = await binding_form_kwargs(research_project, permissions)
    entered = EtlBindingEditForm(
        request.GET, **form_kwargs, config_version_id=request.GET.get('config_fields_for')).entered_config()
    form = EtlBindingEditForm(
        **form_kwargs, initial={'script_version': request.GET.get('script_version'), 'config': entered},
        auto_id=auto_id)
    return render(request, '01_dashboard/_etl_binding_config_fields.html', {'form': form})


def _uuid_or_404(value) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise Http404


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


async def _get_sources_project_or_404(request, project_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_view_sources:
        raise Http404()
    return research_project, permissions


async def _sources_response(request, project, permissions, *, manage_error=None, **forms):
    section_context = await etl_section_context(project, permissions, ETL_SECTION_SOURCES)
    section_context |= {name: form for name, form in forms.items() if form is not None}
    if manage_error:
        section_context['manage_error'] = manage_error
    return _htmx_tab_response(
        request, _ETL_SECTION_PANELS[ETL_SECTION_SOURCES], project, 'etl-pipelines',
        extra_context={'etl_section': ETL_SECTION_SOURCES} | section_context, with_sidebar=True,
    )


@htmx_login_required
async def etl_source_locations_create(request, project_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    form = EtlSourceLocationForm(request.POST)
    if not form.is_valid():
        return await _sources_response(request, research_project, permissions, source_location_form=form)
    error = await _attempt(create_source_location(
        project=research_project, user=await request.auser(), request=request, name=form.cleaned_data['name'],
        bucket=form.cleaned_data['bucket'], prefix=form.cleaned_data['prefix']))
    return await _sources_response(
        request, research_project, permissions, manage_error=error, source_location_form=form if error else None)


@htmx_login_required
async def etl_source_location_rename(request, project_id, location_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(EtlSourceLocation, project=research_project, id=location_id)
    form = EtlSourceLocationRenameForm(request.POST)
    error = _form_errors(form) if not form.is_valid() else await _attempt(rename_source_location(
        project=research_project, user=await request.auser(), request=request, location_id=location.id,
        name=form.cleaned_data['name']))
    return await _sources_response(request, research_project, permissions, manage_error=error)


@htmx_login_required
async def etl_source_location_delete(request, project_id, location_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(EtlSourceLocation, project=research_project, id=location_id)
    error = await _attempt(delete_source_location(
        project=research_project, user=await request.auser(), request=request, location_id=location.id))
    return await _sources_response(request, research_project, permissions, manage_error=error)


@htmx_login_required
async def etl_location_grants_create(request, project_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    form = EtlLocationGrantForm(request.POST)
    if not form.is_valid():
        return await _sources_response(request, research_project, permissions, location_grant_form=form)
    error = await _attempt(create_location_grant(
        project=research_project, user=await request.auser(), request=request,
        bucket=form.cleaned_data['bucket'], prefix=form.cleaned_data['prefix']))
    return await _sources_response(
        request, research_project, permissions, manage_error=error, location_grant_form=form if error else None)


@htmx_login_required
async def etl_location_grant_delete(request, project_id, grant_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    grant = await aget_object_or_404(EtlLocationGrant, project=research_project, id=grant_id)
    error = await _attempt(delete_location_grant(
        project=research_project, user=await request.auser(), request=request, grant_id=grant.id))
    return await _sources_response(request, research_project, permissions, manage_error=error)
