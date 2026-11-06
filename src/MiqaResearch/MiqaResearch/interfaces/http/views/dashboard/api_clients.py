"""The API clients tab (#277, ADR 0027): a project's machine clients and their Client Binding.

Only a superuser or the project's Admin gets the tab and its actions; anyone else gets 404, as if
it didn't exist. Each action re-renders the panel; issuing and rotating render the new secret once
(it is stored hashed and never shown again).
"""
from django.http import Http404
from django.shortcuts import aget_object_or_404, render
from django.views.decorators.http import require_POST

from MiqaResearch.actions.client_bindings import (
    ClientBindingError,
    issue_client,
    revoke_client,
    rotate_client_secret,
    update_client,
)
from MiqaResearch.data.models import ClientBinding, Clinic
from MiqaResearch.interfaces.http.forms.api_clients import ApiClientIssueForm, ApiClientUpdateForm
from MiqaResearch.readers.client_bindings import get_project_client_bindings, user_can_manage_clients
from MiqaResearch.readers.participant_consent_reader import get_project_consent_participant_count
from MiqaResearch.readers.research_project_reader import get_project_connected_clinics

from .htmx_auth import htmx_login_required
from .project import get_user_project_or_404
from .tabs import _htmx_tab_response, _is_partial_request

TAB = "api-clients"
PANEL = "01_dashboard/_panel_api_clients.html"


async def _get_clients_project_or_404(request, project_id):
    project = await get_user_project_or_404(request, project_id)
    if not await user_can_manage_clients(await request.auser(), project):
        raise Http404()
    return project


async def _project_sites(project) -> list[dict]:
    return [site for site in await get_project_connected_clinics(project.id) if site["clinic_id"] is not None]


async def _panel_context(project, *, issue_form=None, issued=None, error=None) -> dict:
    sites = await _project_sites(project)
    bindings = await get_project_client_bindings(project)
    for binding in bindings:
        binding.update_form = ApiClientUpdateForm(
            sites=sites, auto_id=f"id_client_{binding.id}_%s",
            initial={"clinic": str(binding.clinic_id or ""), "dicom_raw": binding.dicom_raw})
    return {
        "client_bindings": bindings,
        "issue_form": issue_form or ApiClientIssueForm(sites=sites),
        "issued": issued,
        "manage_error": error,
    }


async def _render_panel(request, project, **panel_kwargs):
    return _htmx_tab_response(request, PANEL, project, TAB, extra_context=await _panel_context(project, **panel_kwargs))


async def _clinic_or_none(clinic_id: str):
    return await Clinic.objects.aget(pk=clinic_id) if clinic_id else None


@htmx_login_required
async def api_clients(request, project_id):
    project = await _get_clients_project_or_404(request, project_id)
    if _is_partial_request(request):
        return await _render_panel(request, project)
    sites = await _project_sites(project)
    return render(request, "01_dashboard/project.html", {
        "project": project, "active_tab": TAB, "site_count": len(sites),
        "participant_count": await get_project_consent_participant_count(project=project),
    } | await _panel_context(project))


@require_POST
@htmx_login_required
async def api_client_issue(request, project_id):
    project = await _get_clients_project_or_404(request, project_id)
    form = ApiClientIssueForm(request.POST, sites=await _project_sites(project))
    if not form.is_valid():
        return await _render_panel(request, project, issue_form=form)
    try:
        issued = await issue_client(
            project=project, user=await request.auser(), request=request, name=form.cleaned_data["name"],
            site=await _clinic_or_none(form.cleaned_data["clinic"]), dicom_raw=form.cleaned_data["dicom_raw"])
    except ClientBindingError as error:
        return await _render_panel(request, project, issue_form=form, error=str(error))
    return await _render_panel(request, project, issued=issued)


async def _binding_or_404(project, binding_id) -> ClientBinding:
    return await aget_object_or_404(
        ClientBinding.objects.select_related("application", "research_project"), research_project=project, id=binding_id
    )


@require_POST
@htmx_login_required
async def api_client_update(request, project_id, binding_id):
    project = await _get_clients_project_or_404(request, project_id)
    binding = await _binding_or_404(project, binding_id)
    form = ApiClientUpdateForm(request.POST, sites=await _project_sites(project))
    if not form.is_valid():
        return await _render_panel(request, project, error="; ".join(
            str(error) for errors in form.errors.values() for error in errors))
    try:
        await update_client(
            binding=binding, user=await request.auser(), request=request,
            site=await _clinic_or_none(form.cleaned_data["clinic"]), dicom_raw=form.cleaned_data["dicom_raw"])
    except ClientBindingError as error:
        return await _render_panel(request, project, error=str(error))
    return await _render_panel(request, project)


@require_POST
@htmx_login_required
async def api_client_rotate(request, project_id, binding_id):
    project = await _get_clients_project_or_404(request, project_id)
    binding = await _binding_or_404(project, binding_id)
    issued = await rotate_client_secret(binding=binding, user=await request.auser(), request=request)
    return await _render_panel(request, project, issued=issued)


@require_POST
@htmx_login_required
async def api_client_revoke(request, project_id, binding_id):
    project = await _get_clients_project_or_404(request, project_id)
    binding = await _binding_or_404(project, binding_id)
    await revoke_client(binding=binding, user=await request.auser(), request=request)
    return await _render_panel(request, project)
