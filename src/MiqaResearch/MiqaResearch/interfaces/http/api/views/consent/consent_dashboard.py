import logging
from http.client import HTTPResponse
from typing import Any
from uuid import UUID

from django.utils.translation import gettext as _
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.data.serializers.charts.bar import BarChartResponseSchema
from MiqaResearch.data.serializers.charts.xy import FilledAreaChartResponseSchema, LineChartResponseSchema
from MiqaResearch.data.serializers.participant_consent import ProjectConsentHistoryByClinicSchema
from MiqaResearch.interfaces.http.api.pagination import DataTablePagination
from MiqaResearch.readers.participant_consent_reader import (
    CONSENT_TABLE_ROLES,
    get_consent_history_by_clinic,
    get_consent_history_plot_by_clinic,
    get_consent_statistics_plot,
    get_consent_table_data_for_project,
)
from MiqaResearch.readers.research_project_reader import check_user_project_role_by_name

logger = logging.getLogger("mires")

router = Router()


@router.get(
    "/consent_by_clinic/{project_id}",
    response=ProjectConsentHistoryByClinicSchema,
    url_name="dashboard_consent_by_clinic"
)
async def dashboard_consent_data_by_clinic(request, project_id: UUID):
    """
    Get consent data by clinic for a given project.
    """
    research_project = await _check_research_and_role(request, project_id)

    try:
        consent_history_data = await get_consent_history_by_clinic(research_project)
    except Exception as e:
        logger.error("Error retrieving consent history data for project %s", project_id, exc_info=True)
        return {"error": str(e)}

    return consent_history_data


@router.get(
    "consent_by_clinic/{project_id}/table",
    response=list[dict[str, Any]],
    url_name="dashboard_consent_statistics_table"
)
@paginate(DataTablePagination)
async def dashboard_consent_table_data(request, project_id: UUID, include_pid: bool = False):
    """
    Get consent data by clinic for a specific research project for showing in a data table. The data is limited to the
    clinics the user is associated with for the given research project.

    Query parameters: `page`, `page_size`, `include_columns` (see `DataTablePagination`) and `include_pid`.
    """
    research_project = await _check_research_and_role(
        request, project_id, required_role=CONSENT_TABLE_ROLES)

    return await get_consent_table_data_for_project(
        research_project, await request.auser(), include_pid=include_pid)


@router.get(
    "/consent_by_clinic/{project_id}/plot",
    response=LineChartResponseSchema,
    url_name="dashboard_consent_plot_by_clinic"
)
async def dashboard_consent_plot_data_by_clinic(request, project_id: UUID):
    """
    Get consent data by clinic for a given project.
    """
    research_project = await _check_research_and_role(request, project_id)

    logger.debug("Extra query parameters: %s", request.GET)

    try:
        consent_plot_data = await get_consent_history_plot_by_clinic(research_project)
    except Exception as e:
        logger.error("Error retrieving consent plot data for project %s", project_id, exc_info=True)
        return HttpError(500, str(e))

    logger.debug("Successfully retrieved consent plot data for project %s", project_id)
    return consent_plot_data


@router.get(
    "/consent_statistics/{project_id}/plot",
    response=BarChartResponseSchema,
    url_name="dashboard_consent_statistics_plot"
)
async def dashboard_consent_statistics_plot(request, project_id: UUID):
    """
    Get consent statistics plot data for a given project.
    """
    research_project = await _check_research_and_role(request, project_id)

    try:
        consent_statistics_plot_data = await get_consent_statistics_plot(research_project)
    except Exception as e:
        logger.error("Error retrieving consent statistics plot data for project %s", project_id, exc_info=True)
        return HttpError(500, str(e))

    logger.debug("Successfully retrieved consent statistics plot data for project %s", project_id)
    return consent_statistics_plot_data


async def _check_research_and_role(request, project_id: UUID, required_role: tuple[str, ...] = ("any",)):
    """
    Check if the research project exists and if the user has the required role. Raises HttpError 404 for a missing
    project and 403 when the user lacks the role.
    """
    try:
        logger.info("Checking research project and user role for project_id: %s", project_id)
        research_project, has_required_role = await check_user_project_role_by_name(
            request, project_id, required_role=required_role)
    except ResearchProject.DoesNotExist:
        logger.error("Research project with id %s does not exist", project_id)
        raise HttpError(404, _("Research project not found"))

    if not has_required_role:
        logger.error("User does not have permission to access project with id %s", project_id)
        raise HttpError(403, _("You do not have permission to access this project"))

    logger.debug("User has permission to access project with id %s", project_id)
    return research_project
