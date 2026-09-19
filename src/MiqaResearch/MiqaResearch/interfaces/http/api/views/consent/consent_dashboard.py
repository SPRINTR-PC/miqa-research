import logging
from http.client import HTTPResponse
from uuid import UUID

from math import ceil
from django.utils.translation import gettext as _
from ninja import Query, Router
from ninja.errors import HttpError

from MiqaResearch.data.models import ResearchProject
from MiqaResearch.data.serializers.charts.bar import BarChartResponseSchema
from MiqaResearch.data.serializers.charts.xy import FilledAreaChartResponseSchema, LineChartResponseSchema
from MiqaResearch.data.serializers.data_table import DataTableResponseSchema, PaginationMetaSchema
from MiqaResearch.data.serializers.participant_consent import ProjectConsentHistoryByClinicSchema
from MiqaResearch.readers.participant_consent_reader import (
    get_consent_history_by_clinic,
    get_consent_history_plot_by_clinic,
    get_consent_statistics_plot,
    get_consent_table_data_for_project,
)
from MiqaResearch.readers.research_project_reader import check_user_project_role_by_name
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_PARTICIPANT_RECRUITER,
    PROJECT_ROLE_PI,
)

logger = logging.getLogger("mires")

router = Router()

TABLE_ALLOWED_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI, PROJECT_ROLE_PARTICIPANT_RECRUITER)


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
    response=DataTableResponseSchema,
    url_name="dashboard_consent_statistics_table"
)
async def dashboard_consent_table_data(
        request, project_id: UUID, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    """
    Get consent data by clinic for a specific research project for showing in a data table. The data is limited to the
    clinics the user is associated with for the given research project.
    """
    research_project = await _check_research_and_role(
        request, project_id, required_role=TABLE_ALLOWED_ROLES)

    include_pid = request.GET.get("include_pid", "false").lower() == "true"
    include_columns = request.GET.get("columns", "true").lower() == "true"

    consent_table_query, columns = await get_consent_table_data_for_project(
        research_project, await request.auser(), include_pid=include_pid)
    total_items = await consent_table_query.acount()
    offset = (page - 1) * per_page
    rows = [row async for row in consent_table_query[offset:offset + per_page]]
    consent_table_data = DataTableResponseSchema(
        columns=columns if include_columns else None,
        rows=rows,
        pagination=PaginationMetaSchema(
            page=page,
            page_size=per_page,
            total_pages=max(ceil(total_items / per_page), 1),
            total_items=total_items,
        )
    )

    return consent_table_data


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
