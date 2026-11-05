from typing import Any
from uuid import UUID

from ninja import Router
from ninja.pagination import paginate
from ninja.security import SessionAuth

from MiqaResearch.interfaces.http.api.pagination import DataTablePagination
from MiqaResearch.interfaces.http.views.dashboard.project import get_user_etl_project_or_404
from MiqaResearch.readers.etl_reader import get_project_custom_scripts_table_source

router = Router(auth=SessionAuth())


@router.get(
    "/{project_id}/scripts/table",
    response=list[dict[str, Any]],
    url_name="etl_scripts_table",
)
@paginate(DataTablePagination)
async def etl_scripts_table(request, project_id: UUID):
    """
    The project's custom ETL scripts for the Scripts section's Data Table. Visible to every ETL-visible role (404
    otherwise, like the tab itself); `edit_id` is only filled for roles that may manage scripts.

    Query parameters: `page`, `page_size`, `sort`, `include_columns` (see `DataTablePagination`) and the declared
    column filters.
    """
    project, permissions = await get_user_etl_project_or_404(request, project_id)
    return await get_project_custom_scripts_table_source(project, can_edit=permissions.can_manage)
