import logging
from http.client import HTTPResponse
from uuid import UUID

from django.utils.translation import gettext as _
from ninja import Router
from ninja.errors import HttpError

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.data.serializers.charts.bar import BarChartResponseSchema
from MiqaResearch.data.serializers.charts.xy import FilledAreaChartResponseSchema, LineChartResponseSchema
from MiqaResearch.data.serializers.participant_consent import ProjectConsentHistoryByClinicSchema
from MiqaResearch.readers.participant_consent_reader import (
    get_consent_history_by_clinic,
    get_consent_history_plot_by_clinic,
    get_consent_statistics_plot,
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
    research_project, has_required_role, error_response = await _check_research_and_role(request, project_id)

    if error_response:
        return error_response

    try:
        consent_history_data = await get_consent_history_by_clinic(research_project)
    except Exception as e:
        logger.error("Error retrieving consent history data for project %s", project_id, exc_info=True)
        return {"error": str(e)}

    return consent_history_data


@router.get(
    "/consent_by_clinic/{project_id}/plot",
    response=LineChartResponseSchema,
    url_name="dashboard_consent_plot_by_clinic"
)
async def dashboard_consent_plot_data_by_clinic(request, project_id: UUID):
    """
    Get consent data by clinic for a given project.
    """
    research_project, has_required_role, error_response = await _check_research_and_role(request, project_id)

    logger.debug("Extra query parameters: %s", request.GET)

    if not has_required_role or error_response:
        logger.error("Error checking research project and user role for project_id: %s", project_id)
        return HttpError(403, error_response)

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
    research_project, has_required_role, error_response = await _check_research_and_role(request, project_id)

    if not has_required_role or error_response:
        logger.error("Error checking research project and user role for project_id: %s", project_id)
        return HttpError(403, error_response)

    try:
        consent_statistics_plot_data = await get_consent_statistics_plot(research_project)
    except Exception as e:
        logger.error("Error retrieving consent statistics plot data for project %s", project_id, exc_info=True)
        return HttpError(500, str(e))

    logger.debug("Successfully retrieved consent statistics plot data for project %s", project_id)
    return consent_statistics_plot_data


async def _check_research_and_role(request, project_id: UUID):
    """
    Check if the research project exists and if the user has the required role.
    """
    try:
        logger.info("Checking research project and user role for project_id: %s", project_id)
        research_project, has_required_role = await check_user_project_role_by_name(request, project_id, required_role=("any",))
    except ResearchProject.DoesNotExist:
        logger.error("Research project with id %s does not exist", project_id)
        return None, False, {"error": _("Research project not found")}

    if not has_required_role:
        logger.error("User does not have permission to access project with id %s", project_id)
        return research_project, False, {"error": _("You do not have permission to access this project")}

    logger.debug("User has permission to access project with id %s", project_id)
    return research_project, True, None
