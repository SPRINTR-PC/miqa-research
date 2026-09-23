"""ETL permissions policy (#158): the single source of truth for who may view or manage the
ETL Pipelines tab's Scripts/Bindings/Defaults sections. Every view that renders or accepts an ETL
management action must go through `get_etl_permissions` (or `etl_permissions_for_roles` when the
role set is already known) instead of re-deriving these boundaries ad hoc.

Role boundaries:
- Admin, Data Manager, or superuser: manage (create/edit/archive Scripts, create Bindings, edit
  EtlProjectSettings).
- Admin or superuser only: the subset of manage actions that lower platform-wide limits/retention
  or archive a Script.
- PI, Investigator: read-only visibility, no manage controls rendered or accepted.
- Any other role (Contributor, Annotator, Participant Recruiter, ...): no visibility at all -- the
  caller should 404 rather than render a read-only or forbidden page.
"""
from dataclasses import dataclass

from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_DATA_MANAGER,
    PROJECT_ROLE_INVESTIGATOR,
    PROJECT_ROLE_PI,
)

ETL_MANAGE_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_DATA_MANAGER)
ETL_ADMIN_ONLY_ROLES = (PROJECT_ROLE_ADMIN,)
ETL_READ_ONLY_ROLES = (PROJECT_ROLE_PI, PROJECT_ROLE_INVESTIGATOR)
ETL_VISIBLE_ROLES = ETL_MANAGE_ROLES + ETL_READ_ONLY_ROLES


@dataclass(frozen=True)
class EtlPermissions:
    is_superuser: bool
    role_names: frozenset[str]

    @property
    def can_view(self) -> bool:
        """May see the ETL Pipelines tab at all (read-only or manage)."""
        return self.is_superuser or bool(self.role_names.intersection(ETL_VISIBLE_ROLES))

    @property
    def can_manage(self) -> bool:
        """May create/edit Scripts and Versions, create Bindings, edit non-admin-only settings."""
        return self.is_superuser or bool(self.role_names.intersection(ETL_MANAGE_ROLES))

    @property
    def can_manage_admin_only(self) -> bool:
        """May archive a Script, or change platform-wide limit/retention overrides."""
        return self.is_superuser or bool(self.role_names.intersection(ETL_ADMIN_ONLY_ROLES))


def etl_permissions_for_roles(*, is_superuser: bool, role_names) -> EtlPermissions:
    """Pure constructor: builds an `EtlPermissions` from an already-known role-name collection."""
    return EtlPermissions(is_superuser=is_superuser, role_names=frozenset(role_names))


async def get_etl_permissions(request, project) -> EtlPermissions:
    """Computes ETL permissions for the requesting user within `project`."""
    from MiqaResearch.readers.research_project_reader import get_user_project_role_list

    user = await request.auser()
    role_names = {role["name"] for role in await get_user_project_role_list(user, project)}
    return etl_permissions_for_roles(is_superuser=user.is_superuser, role_names=role_names)
