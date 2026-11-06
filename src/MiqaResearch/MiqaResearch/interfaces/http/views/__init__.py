from .administration.index import index as administration_index
from .dashboard.api_clients import (
    api_client_issue as dashboard_tab_api_client_issue,
)
from .dashboard.api_clients import (
    api_client_revoke as dashboard_tab_api_client_revoke,
)
from .dashboard.api_clients import (
    api_client_rotate as dashboard_tab_api_client_rotate,
)
from .dashboard.api_clients import (
    api_client_update as dashboard_tab_api_client_update,
)
from .dashboard.api_clients import (
    api_clients as dashboard_tab_api_clients,
)
from .dashboard.etl import (
    etl_binding_config_fields as dashboard_tab_etl_binding_config_fields,
)
from .dashboard.etl import (
    etl_binding_edit as dashboard_tab_etl_binding_edit,
)
from .dashboard.etl import (
    etl_bindings_create as dashboard_tab_etl_bindings_create,
)
from .dashboard.etl import (
    etl_datatype_schema as dashboard_tab_etl_datatype_schema,
)
from .dashboard.etl import (
    etl_defaults_update as dashboard_tab_etl_defaults_update,
)
from .dashboard.etl import (
    etl_job_detail as dashboard_tab_etl_job_detail,
)
from .dashboard.etl import (
    etl_job_retry as dashboard_tab_etl_job_retry,
)
from .dashboard.etl import (
    etl_location_grant_delete as dashboard_tab_etl_location_grant_delete,
)
from .dashboard.etl import (
    etl_location_grants_create as dashboard_tab_etl_location_grants_create,
)
from .dashboard.etl import (
    etl_script_archive as dashboard_tab_etl_script_archive,
)
from .dashboard.etl import (
    etl_script_customize as dashboard_tab_etl_script_customize,
)
from .dashboard.etl import (
    etl_script_edit as dashboard_tab_etl_script_edit,
)
from .dashboard.etl import (
    etl_script_version_create as dashboard_tab_etl_script_version_create,
)
from .dashboard.etl import (
    etl_scripts_create as dashboard_tab_etl_scripts_create,
)
from .dashboard.etl import (
    etl_source_location_delete as dashboard_tab_etl_source_location_delete,
)
from .dashboard.etl import (
    etl_source_location_rename as dashboard_tab_etl_source_location_rename,
)
from .dashboard.etl import (
    etl_source_locations_create as dashboard_tab_etl_source_locations_create,
)
from .dashboard.index import index as dashboard_index
from .dashboard.project import project as dashboard_project
from .dashboard.tabs import consent_statistics as dashboard_tab_consent_statistics
from .dashboard.tabs import consent_statistics_content as dashboard_tab_consent_statistics_content
from .dashboard.tabs import etl_pipelines as dashboard_tab_etl_pipelines
from .dashboard.tabs import etl_pipelines_content as dashboard_tab_etl_pipelines_content
from .dashboard.tabs import goals as dashboard_tab_goals
from .landing_page.index import index as landing_page_index
from .monitor.index import index as monitor_index
from .upload_data.index import UploadData as UploadDataView
