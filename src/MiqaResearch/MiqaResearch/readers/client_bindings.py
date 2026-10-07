"""Machine clients of a project (ADR 0027): who may manage them, and the listing.

Only a superuser or the project's Admin ("Project Admin") issues, rotates and revokes clients, picks
their Site and grants `dicom:raw`; for anyone else the API clients tab doesn't exist (404). Like the
rest of the dashboard, a superuser still reaches a project through membership.
"""
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN
from MiqaResearch.data.models import ClientBinding

CLIENT_MANAGE_ROLES = (PROJECT_ROLE_ADMIN,)


def can_manage_clients(*, role_names, is_superuser: bool) -> bool:
    return is_superuser or bool(set(role_names).intersection(CLIENT_MANAGE_ROLES))


async def user_can_manage_clients(user, project) -> bool:
    from MiqaResearch.readers.research_project_reader import get_user_project_role_list

    role_names = {role["name"] for role in await get_user_project_role_list(user, project)}
    return can_manage_clients(role_names=role_names, is_superuser=user.is_superuser)


async def get_project_client_bindings(project) -> list[ClientBinding]:
    return [
        binding async for binding in ClientBinding.objects.filter(research_project=project)
        .select_related("application", "clinic").order_by("created_at")
    ]
