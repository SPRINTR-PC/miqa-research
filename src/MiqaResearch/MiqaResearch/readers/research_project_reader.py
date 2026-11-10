import logging
from uuid import UUID

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import F

from MiqaResearch.data.models import ResearchProject, ResearchProjectRole

logger = logging.getLogger("mires")


async def check_user_project_role_by_name(
        request, project_id: UUID, required_role: tuple[str] = ("any",)) -> tuple[ResearchProject, bool]:
    """
    Check if the user has the required role for the given project.
    """
    if not required_role:
        logger.warning("User project role check requested with empty required_role for project %s", project_id)
        raise ValueError("required_role must not be empty")

    user, research_project, project_roles = await get_user_project_role_list_from_request_and_project(
        request, project_id
    )

    if research_project is None:
        logger.warning("User project role check requested for non-existent project %s", project_id)
        raise ResearchProject.DoesNotExist

    if user.is_superuser or "any" in required_role and project_roles:
        return research_project, True

    if not any(role["name"] in required_role for role in project_roles):
        return research_project, False

    return research_project, True


async def check_user_project_role_by_id(
        request, project_id: UUID, required_role: tuple[UUID | str] = ("any",)) -> tuple[ResearchProject | None, bool]:
    """
    Check if the user has the required role for the given project.
    """
    if not required_role:
        logger.error("check_user_project_role_by_id called with empty required_role for project %s", project_id)
        raise ValueError("required_role must not be empty")

    user, research_project, project_roles = await get_user_project_role_list_from_request_and_project(
        request, project_id
    )

    if research_project is None:
        logger.warning("User project role check requested for non-existent project %s", project_id)
        return None, False

    if user.is_superuser or "any" in required_role and project_roles:
        return research_project, True

    if not any(role["id"] in required_role or role["name"] in required_role for role in project_roles):
        return research_project, False

    return research_project, True


async def get_project_connected_clinics(project_id: UUID) -> list[dict[str, str | UUID]]:
    """
    Get the list of clinics connected to the given project.
    """
    try:
        query = (
            ResearchProject.objects
            .filter(id=project_id).prefetch_related("researchprojectclinicmap__clinic")
            .annotate(
                clinic_id=F("researchprojectclinicmap__clinic__id"),
                clinic_name=F("researchprojectclinicmap__clinic__clinic_name"),
            )
            .values("clinic_id", "clinic_name").distinct()
            .order_by("clinic_name")
        )
    except Exception:
        logger.error("Error fetching connected clinics for project %s", project_id, exc_info=True)
        raise

    return [clinic async for clinic in query]


async def get_user_project_connected_clinics(request, project_id: UUID) -> list[dict[str, str | UUID]]:
    """
    Get the list of clinics connected to the given project that the user is allowed to see data for.
    """
    try:
        user = await request.auser()
        query = ResearchProject.objects.filter(id=project_id).prefetch_related("researchprojectclinicmap__clinic")

        if not user.is_superuser:
            has_project_wide_access = await ResearchProject.objects.filter(
                id=project_id,
                researchprojectuserrolemap__user=user,
                researchprojectuserrolemap__role__name__in=[
                    "Project Admin",
                    "Principal Investigator",
                ],
            ).aexists()

            if not has_project_wide_access:
                query = query.filter(
                    researchprojectuserrolemap__user=user,
                    researchprojectuserrolemap__clinic=F("researchprojectclinicmap__clinic"),
                )

        query = (
            query
            .annotate(
                clinic_id=F("researchprojectclinicmap__clinic__id"),
                clinic_name=F("researchprojectclinicmap__clinic__clinic_name"),
            )
            .values("clinic_id", "clinic_name")
            .distinct()
            .order_by("clinic_name")
        )
    except Exception:
        logger.error("Error fetching connected clinics for project %s", project_id, exc_info=True)
        raise

    return [clinic async for clinic in query]


async def get_user_project_role_list_from_request_and_project(
        request, project_id: UUID) -> tuple[User | AnonymousUser, ResearchProject | None, list[dict[str, str | UUID]]]:
    """
    Get the list of roles the user in a request object has for the given project.
    """
    user = await request.auser()
    if not user.is_authenticated:
        logger.warning("User project role list requested for unauthenticated user for project %s", project_id)
        return user, None, []

    return await get_user_project_role_list_for_project_id(user, project_id)


async def get_user_project_role_list_for_project_id(
        user, project_id: UUID) -> tuple[User | AnonymousUser, ResearchProject | None, list[dict[str, str | UUID]]]:
    """
    Get the list of roles the user has for the given project id.
    """
    try:
        research_project = await ResearchProject.objects.aget(id=project_id)
    except ResearchProject.DoesNotExist:
        logger.error("User project role list requested for non-existent project %s", project_id, exc_info=True)
        return user, None, []

    user_roles = await get_user_project_role_list(user, research_project)

    return user, research_project, user_roles


async def get_user_project_role_list(
        user, project: ResearchProject) -> list[dict[str, str | UUID]]:
    """
    Get the list of roles the user has for the given project id.
    """
    queryset = ResearchProjectRole.objects.filter(
        researchprojectuserrolemap__project=project,
        researchprojectuserrolemap__user__exact=user
    ).values("id", "name")

    return [role async for role in queryset]
