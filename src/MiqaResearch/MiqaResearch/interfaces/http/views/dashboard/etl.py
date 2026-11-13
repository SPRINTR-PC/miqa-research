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
from django.utils.translation import gettext as _

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.actions.etl.bindings import create_pipeline_binding, update_pipeline_binding
from MiqaResearch.actions.etl.exceptions import EtlActionError
from MiqaResearch.actions.etl.jobs import retry_failed_job
from MiqaResearch.actions.etl.scripts import (
    archive_custom_script,
    create_custom_script,
    create_script_version,
    customize_native_script,
    delete_archived_script,
    update_custom_script,
)
from MiqaResearch.actions.etl.settings import update_etl_project_settings
from MiqaResearch.actions.etl.sources import (
    create_location_grant,
    create_source_location,
    delete_location_grant,
    delete_source_location,
    update_location_grant,
    update_source_location,
)
from MiqaResearch.actions.etl.storages import browse_storage
from MiqaResearch.data.models import EtlLocationGrant, EtlScript, EtlSourceLocation, EtlStorage, PipelineBinding
from MiqaResearch.etl_datatypes import DatatypeNotRegistered
from MiqaResearch.etl_datatypes.describe import describe_datatype
from MiqaResearch.interfaces.http.forms.etl import (
    EtlBindingCreateForm,
    EtlBindingEditForm,
    EtlLocationGrantEditForm,
    EtlLocationGrantForm,
    EtlProjectSettingsForm,
    EtlScriptCreateForm,
    EtlScriptEditForm,
    EtlSourceLocationForm,
    source_location_prefix,
)
from MiqaResearch.readers.etl_reader import (
    get_etl_storages,
    get_latest_version_code,
    get_project_job,
    get_project_location_grants,
    get_project_max_script_source_bytes,
    get_project_source_locations,
)
from MiqaResearch.readers.etl_storage_browser import EtlStorageBrowseError

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
        request, project, permissions, script=None, *, create_form=None, edit_form=None, invalid=False):
    """The New script (no `script`) or Edit script modal body. A form that failed validation comes back bound, and
    the response then retargets the modal itself so the errors show where the user is working."""
    max_source_bytes = await get_project_max_script_source_bytes(project)
    if script is None:
        create_form = create_form or EtlScriptCreateForm(max_source_bytes=max_source_bytes)
    else:
        if edit_form is None:
            latest = await get_latest_version_code(script)
            edit_form = EtlScriptEditForm(
                max_source_bytes=max_source_bytes,
                initial={
                    'name': script.name, 'description': script.description,
                    **({
                        'source_code': latest.code, 'language': latest.extension,
                        'config_schema': json.dumps(latest.config_schema, indent=2) if latest.config_schema else '',
                    } if latest else {}),
                })
    response = HttpResponse(render_to_string('01_dashboard/_etl_script_modal.html', {
        'project': project, 'etl_permissions': permissions, 'script': script,
        'create_form': create_form, 'edit_form': edit_form,
    }, request=request))
    if invalid:
        response['HX-Retarget'] = '#app-modal-content'
        response['HX-Reswap'] = 'innerHTML'
    return response


def _version_changed(latest, cleaned) -> bool:
    """Whether the posted code, language or config schema differ from the latest Version's, i.e. whether
    saving should add a Version. Code is compared with CRLF normalised and stripped: browsers post
    textareas with CRLF and the form strips."""
    if latest is None:
        return True

    def normalised(code):
        return code.replace('\r\n', '\n').strip()

    return (
        normalised(cleaned['source_code']) != normalised(latest.code)
        or cleaned['language'] != latest.extension
        or cleaned['config_schema'] != latest.config_schema)


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
    max_source_bytes = await get_project_max_script_source_bytes(research_project)
    form = EtlScriptEditForm(request.POST, request.FILES, max_source_bytes=max_source_bytes)
    if not form.is_valid():
        return await _script_modal(request, research_project, permissions, script, edit_form=form, invalid=True)

    error = await _attempt(update_custom_script(
        project=research_project, user=user, request=request, script=script,
        name=form.cleaned_data['name'], description=form.cleaned_data['description'],
        datatype_name=form.cleaned_data['datatype'],
    ))
    if error is None and _version_changed(await get_latest_version_code(script), form.cleaned_data):
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
async def etl_script_delete(request, project_id, script_id):
    """Superuser only. GET: the confirmation modal. POST: hard-deletes an archived, unused custom Script."""
    research_project, permissions = await get_user_etl_project_or_404(request, project_id)
    if not permissions.is_superuser:
        return HttpResponseForbidden()

    script = await aget_object_or_404(
        EtlScript, id=script_id, project=research_project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
    if request.method != 'POST':
        return HttpResponse(render_to_string('01_dashboard/_etl_script_delete_modal.html', {
            'project': research_project, 'script': script}, request=request))

    user = await request.auser()
    error = await _attempt(delete_archived_script(user=user, request=request, script=script))
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
        current_raw_retention=binding.raw_retention, storage_id=binding.storage_id,
        auto_id=binding_edit_auto_id(binding))
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


NIL_UUID = '00000000-0000-0000-0000-000000000000'


async def _sources_modal(request, project, template, *, form, error=None, **extra):
    """The New source location / New location grant modal body. A POST that failed comes back here with the bound
    form and the error, retargeting the modal itself so the message shows where the user is working."""
    response = HttpResponse(render_to_string(template, {
        'project': project, 'form': form, 'modal_error': error, 'nil_uuid': NIL_UUID,
        'location_grants': await get_project_location_grants(project), 'storages': await get_etl_storages(),
        **extra,
    }, request=request))
    if form.is_bound:
        response['HX-Retarget'] = '#app-modal-content'
        response['HX-Reswap'] = 'innerHTML'
    return response


@htmx_login_required
async def etl_source_locations_create(request, project_id):
    """GET: the New source location modal. POST: creates the location."""
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    template = '01_dashboard/_etl_source_location_modal.html'
    if request.method == 'GET':
        return await _sources_modal(request, research_project, template, form=EtlSourceLocationForm())
    form = EtlSourceLocationForm(request.POST)
    error = None
    if form.is_valid():
        grant = await EtlLocationGrant.objects.select_related('storage').filter(
            project=research_project, id=form.cleaned_data['grant']).afirst()
        if grant is None:
            form.add_error('grant', _('Choose one of the project\'s location grants.'))
        else:
            error = await _attempt(create_source_location(
                project=research_project, user=await request.auser(), request=request,
                name=form.cleaned_data['name'], storage=grant.storage, bucket=grant.bucket,
                prefix=source_location_prefix(grant.prefix, form.cleaned_data['subpath'])))
    if error or not form.is_valid():
        return await _sources_modal(request, research_project, template, form=form, error=error)
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, close_modal=True)


async def _grant_of_location(project, location) -> EtlLocationGrant | None:
    """The project's grant a Source Location sits in: same storage and bucket, the longest prefix of the location's."""
    grants = [
        grant async for grant in EtlLocationGrant.objects.select_related('storage').filter(
            project=project, storage_id=location.storage_id, bucket=location.bucket)
        if location.prefix.startswith(grant.prefix)]
    return max(grants, key=lambda grant: len(grant.prefix), default=None)


@htmx_login_required
async def etl_source_location_edit(request, project_id, location_id):
    """GET: the Edit source location modal. POST: saves it. The name always changes; the grant and prefix only while
    no Binding reads from the location."""
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(
        EtlSourceLocation.objects.select_related('storage'), project=research_project, id=location_id)
    locked = await location.bindings.aexists()
    template = '01_dashboard/_etl_source_location_modal.html'
    extra = {'location': location, 'locked': locked}
    if request.method == 'GET':
        grant = await _grant_of_location(research_project, location)
        initial = {'name': location.name}
        if grant is not None:
            initial |= {'grant': grant.id, 'subpath': location.prefix[len(grant.prefix):].lstrip('/')}
        return await _sources_modal(
            request, research_project, template, form=EtlSourceLocationForm(initial=initial, locked=locked), **extra)
    form = EtlSourceLocationForm(request.POST, locked=locked)
    error = None
    if form.is_valid():
        target = {}
        if not locked:
            grant = await EtlLocationGrant.objects.select_related('storage').filter(
                project=research_project, id=form.cleaned_data['grant']).afirst()
            if grant is None:
                form.add_error('grant', _('Choose one of the project\'s location grants.'))
            else:
                target = {
                    'storage': grant.storage, 'bucket': grant.bucket,
                    'prefix': source_location_prefix(grant.prefix, form.cleaned_data['subpath'])}
        if form.is_valid():
            error = await _attempt(update_source_location(
                project=research_project, user=await request.auser(), request=request, location=location,
                name=form.cleaned_data['name'], **target))
    if error or not form.is_valid():
        return await _sources_modal(request, research_project, template, form=form, error=error, **extra)
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, close_modal=True)


@htmx_login_required
async def etl_location_grant_edit(request, project_id, grant_id):
    """GET: the Edit location grant modal. POST: saves it -- only the name can change."""
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    grant = await aget_object_or_404(
        EtlLocationGrant.objects.select_related('storage'), project=research_project, id=grant_id)
    template = '01_dashboard/_etl_location_grant_modal.html'
    if request.method == 'GET':
        return await _sources_modal(
            request, research_project, template, form=EtlLocationGrantEditForm(initial={'name': grant.name}),
            grant=grant)
    form = EtlLocationGrantEditForm(request.POST)
    if not form.is_valid():
        return await _sources_modal(request, research_project, template, form=form, grant=grant)
    await update_location_grant(
        project=research_project, user=await request.auser(), request=request, grant=grant,
        name=form.cleaned_data['name'].strip())
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, close_modal=True)


@htmx_login_required
async def etl_source_location_delete(request, project_id, location_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    location = await aget_object_or_404(EtlSourceLocation, project=research_project, id=location_id)
    error = await _attempt(delete_source_location(
        project=research_project, user=await request.auser(), request=request, location=location))
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, manage_error=error)


@htmx_login_required
async def etl_location_grants_create(request, project_id):
    """GET: the New location grant modal. POST: creates the grant."""
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    template = '01_dashboard/_etl_location_grant_modal.html'
    if request.method == 'GET':
        return await _sources_modal(request, research_project, template, form=EtlLocationGrantForm())
    form = EtlLocationGrantForm(request.POST)
    error = None
    if form.is_valid():
        storage = await _chosen_storage(form.cleaned_data['storage'])
        error = await _attempt(create_location_grant(
            project=research_project, user=await request.auser(), request=request,
            bucket=form.cleaned_data['bucket'], prefix=form.cleaned_data['prefix'], storage=storage,
            name=form.cleaned_data['name'].strip()))
    if error or not form.is_valid():
        return await _sources_modal(request, research_project, template, form=form, error=error)
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, close_modal=True)


@htmx_login_required
async def etl_location_grant_delete(request, project_id, grant_id):
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    grant = await aget_object_or_404(EtlLocationGrant, project=research_project, id=grant_id)
    error = await _attempt(delete_location_grant(
        project=research_project, user=await request.auser(), request=request, grant=grant))
    return await _rerender_section(request, research_project, permissions, ETL_SECTION_SOURCES, manage_error=error)


async def _chosen_storage(storage_id) -> EtlStorage | None:
    """The Connected Storage a form named, 404 if it doesn't exist; None when none was chosen."""
    return await aget_object_or_404(EtlStorage, id=storage_id) if storage_id else None


@htmx_login_required
async def etl_storage_browse(request, project_id, storage_id):
    """Read-only browse step in the Location Grant form (#394): buckets, or one folder level of
    `?bucket=` under `?prefix=`. Staff and superusers only; a failure renders inline so the
    bucket/prefix can still be typed."""
    research_project, permissions = await _get_sources_project_or_404(request, project_id)
    if not permissions.can_manage_location_grants:
        return HttpResponseForbidden()
    storage = await aget_object_or_404(EtlStorage, id=storage_id)
    bucket = request.GET.get('bucket', '')
    prefix = request.GET.get('prefix', '')
    listing = error = None
    try:
        listing = await browse_storage(
            user=await request.auser(), request=request, project=research_project, storage=storage,
            bucket=bucket or None, prefix=prefix)
    except EtlStorageBrowseError as exc:
        error = str(exc)
    # `nodes=1` is a tree folder expanding: just its children, not the whole browser.
    template = '01_dashboard/_etl_storage_browse.html'
    if request.GET.get('nodes'):
        template = '01_dashboard/_etl_storage_tree_nodes.html'
    return render(request, template, {
        'project': research_project, 'storage': storage, 'bucket': bucket, 'prefix': prefix,
        'listing': listing, 'browse_error': error,
        'parent_prefix': prefix[:prefix.rstrip('/').rfind('/') + 1] if prefix else '',
    })


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
