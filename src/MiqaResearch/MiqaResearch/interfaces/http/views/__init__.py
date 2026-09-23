from .administration.index import index as administration_index
from .dashboard.etl import (
    etl_bindings_create as dashboard_tab_etl_bindings_create,
    etl_defaults_update as dashboard_tab_etl_defaults_update,
    etl_script_archive as dashboard_tab_etl_script_archive,
    etl_script_edit as dashboard_tab_etl_script_edit,
    etl_script_version_create as dashboard_tab_etl_script_version_create,
    etl_scripts_create as dashboard_tab_etl_scripts_create,
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
