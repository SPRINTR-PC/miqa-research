from .administration.index import index as administration_index
from .dashboard.etl import (
    etl_binding_config_fields as dashboard_tab_etl_binding_config_fields,
    etl_binding_edit as dashboard_tab_etl_binding_edit,
    etl_bindings_create as dashboard_tab_etl_bindings_create,
    etl_defaults_update as dashboard_tab_etl_defaults_update,
    etl_job_detail as dashboard_tab_etl_job_detail,
    etl_job_retry as dashboard_tab_etl_job_retry,
    etl_location_grant_delete as dashboard_tab_etl_location_grant_delete,
    etl_location_grants_create as dashboard_tab_etl_location_grants_create,
    etl_script_archive as dashboard_tab_etl_script_archive,
    etl_script_customize as dashboard_tab_etl_script_customize,
    etl_script_edit as dashboard_tab_etl_script_edit,
    etl_script_version_create as dashboard_tab_etl_script_version_create,
    etl_scripts_create as dashboard_tab_etl_scripts_create,
    etl_source_location_delete as dashboard_tab_etl_source_location_delete,
    etl_source_location_rename as dashboard_tab_etl_source_location_rename,
    etl_source_locations_create as dashboard_tab_etl_source_locations_create,
)
from .dashboard.index import index as dashboard_index
from .dashboard.project import project as dashboard_project
from .dashboard.tabs import (
    consent_statistics as dashboard_tab_consent_statistics,
    consent_statistics_content as dashboard_tab_consent_statistics_content,
    etl_pipelines as dashboard_tab_etl_pipelines,
    etl_pipelines_content as dashboard_tab_etl_pipelines_content,
    goals as dashboard_tab_goals
)
from .landing_page.index import index as landing_page_index
from .monitor.index import index as monitor_index
from .upload_data.index import UploadData as UploadDataView
