"""Endpoints for the ETL Pipelines tab beyond its section listings: the manage actions (#158) --
create/edit/archive a custom Script, add a Version, create a Binding, edit the project's ETL
settings overrides, manage Source Locations and location grants (#268) -- and a Job's detail view
(#164). The Sources section's endpoints 404 for a viewer who may not see that section. Every view
resolves the project through `get_user_etl_project_or_404` first, which 404s a user who can't even
view the tab; a view whose action needs more than that (manage, or admin-only manage) then checks
`etl_permissions` itself and responds 403 -- the page exists for them, the action doesn't.
"""
import json
from uuid import UUID

from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import aget_object_or_404, render
from django.template.loader import render_to_string

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
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
from MiqaResearch.etl_datatypes import DatatypeNotRegistered
from MiqaResearch.etl_datatypes.describe import describe_datatype
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
    get_latest_version_code,
    get_project_job,
    get_project_max_script_source_bytes,
    get_project_source_locations,
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
    binding_edit_auto_id,
    binding_form_kwargs,
    etl_section_context,
)


async def _rerender_section(
        request, project, permissions, section, *, manage_error=None, close_modal=False, **bound_forms):
    """Re-renders `section` after an action; `bound_forms` replace the section's unbound forms
    (a form that failed validation keeps what was typed). `close_modal` tells the page to close the app modal
    the action was submitted from (`close-app-modal`, handled in mires.js)."""
    section_context = await etl_section_context(project, permissions, section)
    section_context |= {name: form for name, form in bound_forms.items() if form is not None}
    if manage_error:
        section_context['manage_error'] = manage_error
    response = _htmx_tab_response(
        request, _ETL_SECTION_PANELS[section], project, 'etl-pipelines',
        extra_context={'etl_section': section} | section_context, with_sidebar=True,
    )
    if close_modal:
        response['HX-Trigger'] = 'close-app-modal'
    return response


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


async def _script_modal(
        request, project, permissions, script=None, *, create_form=None, edit_form=None, version_form=None,
        invalid=False):
    """The New script (no `script`) or Edit script modal body. A form that failed validation comes back bound, and
    the response then retargets the modal itself so the errors show where the user is working."""
    max_source_bytes = await get_project_max_script_source_bytes(project)
    if script is None:
        create_form = create_form or EtlScriptCreateForm(max_source_bytes=max_source_bytes)
    else:
        edit_form = edit_form or EtlScriptEditForm(initial={'name': script.name, 'description': script.description})
        if version_form is None:
            latest = await get_latest_version_code(script)
            version_form = EtlScriptVersionCreateForm(
                max_source_bytes=max_source_bytes, script_name=script.name, auto_id=False,
                initial={
                    'source_code': latest.code, 'language': latest.extension,
                    'config_schema': json.dumps(latest.config_schema, indent=2) if latest.config_schema else '',
                } if latest else None)
    response = HttpResponse(render_to_string('01_dashboard/_etl_script_modal.html', {
        'project': project, 'etl_permissions': permissions, 'script': script,
        'create_form': create_form, 'edit_form': edit_form, 'version_form': version_form,
    }, request=request))
    if invalid:
        response['HX-Retarget'] = '#app-modal-content'
        response['HX-Reswap'] = 'innerHTML'
    return response


async def _get_editable_custom_script_or_404(project, script_id) -> EtlScript:
    """A not-archived custom script of this project -- the only kind the Edit modal may open (it carries the
    script's code, so another project's script must 404 rather than render)."""
    return await aget_object_or_404(
        EtlScript, id=script_id, project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM, archived_at__isnull=True)


@htmx_login_required
async def etl_scripts_create(request, project_id):
    """GET: the New script modal. POST: creates the script."""
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    if request.method == 'GET':
        return await _script_modal(request, research_project, permissions)

    user = await request.auser()
    max_source_bytes = await get_project_max_script_source_bytes(research_project)
    form = EtlScriptCreateForm(request.POST, request.FILES, max_source_bytes=max_source_bytes)
    if not form.is_valid():
        return await _script_modal(request, research_project, permissions, create_form=form, invalid=True)

    await create_custom_script(
        project=research_project, user=user, request=request,
        name=form.cleaned_data['name'], description=form.cleaned_data['description'],
        datatype_name=form.cleaned_data['datatype'], source=form.cleaned_data['source'],
        config_schema=form.cleaned_data['config_schema'],
    )
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SCRIPTS, close_modal=True)


@htmx_login_required
async def etl_script_edit(request, project_id, script_id):
    """GET: the Edit script modal (settings, code and config schema). POST: saves the settings."""
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    if request.method == 'GET':
        script = await _get_editable_custom_script_or_404(research_project, script_id)
        return await _script_modal(request, research_project, permissions, script)

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    form = EtlScriptEditForm(request.POST)
    if not form.is_valid():
        return await _script_modal(request, research_project, permissions, script, edit_form=form, invalid=True)

    error = await _attempt(update_custom_script(
        project=research_project, user=user, request=request, script=script,
        name=form.cleaned_data['name'], description=form.cleaned_data['description'],
        datatype_name=form.cleaned_data['datatype'],
    ))
    return await _rerender_section(
        request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error, close_modal=True)


@htmx_login_required
async def etl_script_version_create(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    max_source_bytes = await get_project_max_script_source_bytes(research_project)
    form = EtlScriptVersionCreateForm(
        request.POST, request.FILES, max_source_bytes=max_source_bytes, script_name=script.name, auto_id=False)
    if not form.is_valid():
        return await _script_modal(request, research_project, permissions, script, version_form=form, invalid=True)

    error = await _attempt(create_script_version(
        project=research_project, user=user, request=request, script=script,
        source=form.cleaned_data['source'], config_schema=form.cleaned_data['config_schema'],
    ))
    return await _rerender_section(
        request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error, close_modal=True)


@htmx_login_required
async def etl_script_archive(request, project_id, script_id):
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage_admin_only:
        return HttpResponseForbidden()

    script = await aget_object_or_404(EtlScript, id=script_id)
    user = await request.auser()
    error = await _attempt(archive_custom_script(project=research_project, user=user, request=request, script=script))

    return await _rerender_section(
        request, research_project, permissions, ETL_SECTION_SCRIPTS, manage_error=error, close_modal=True)


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
    form_kwargs = await binding_form_kwargs(research_project, permissions) | {
        'source_locations': await get_project_source_locations(research_project)}

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
    if not permissions.can_manage_source_locations:
        raise Http404()
    return research_project, permissions


@htmx_login_required
async def etl_source_locations_create(request, project_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    form = EtlSourceLocationForm(request.POST)
    error = None
    if form.is_valid():
        error = await _attempt(create_source_location(
            project=research_project, user=await request.auser(), request=request, name=form.cleaned_data['name'],
            bucket=form.cleaned_data['bucket'], prefix=form.cleaned_data['prefix']))
    failed = error or not form.is_valid()
    return await _rerender_section(
        request, research_project, permissions, ETL_SECTION_SOURCES,
        manage_error=error, source_location_form=form if failed else None)


@htmx_login_required
async def etl_source_location_rename(request, project_id, location_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(EtlSourceLocation, project=research_project, id=location_id)
    form = EtlSourceLocationRenameForm(request.POST)
    if form.is_valid():
        error = await _attempt(rename_source_location(
            project=research_project, user=await request.auser(), request=request, location=location,
            name=form.cleaned_data['name']))
    else:
        error = _form_errors(form)
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, manage_error=error)


@htmx_login_required
async def etl_source_location_delete(request, project_id, location_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(EtlSourceLocation, project=research_project, id=location_id)
    error = await _attempt(delete_source_location(
        project=research_project, user=await request.auser(), request=request, location=location))
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, manage_error=error)


@htmx_login_required
async def etl_location_grants_create(request, project_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    form = EtlLocationGrantForm(request.POST)
    error = None
    if form.is_valid():
        error = await _attempt(create_location_grant(
            project=research_project, user=await request.auser(), request=request,
            bucket=form.cleaned_data['bucket'], prefix=form.cleaned_data['prefix']))
    failed = error or not form.is_valid()
    return await _rerender_section(
        request, research_project, permissions, ETL_SECTION_SOURCES,
        manage_error=error, location_grant_form=form if failed else None)


@htmx_login_required
async def etl_location_grant_delete(request, project_id, grant_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    grant = await aget_object_or_404(EtlLocationGrant, project=research_project, id=grant_id)
    error = await _attempt(delete_location_grant(
        project=research_project, user=await request.auser(), request=request, grant=grant))
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, manage_error=error)


@htmx_login_required
async def etl_datatype_schema(request, project_id):
    """The schema preview shown under the Datatype picker (#393): fields plus an example row."""
    _, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.can_manage:
        return HttpResponseForbidden()
    try:
        description = describe_datatype(request.GET.get('datatype', ''))
    except DatatypeNotRegistered:
        description = None
    return render(request, '01_dashboard/_etl_datatype_schema.html', {'description': description})
