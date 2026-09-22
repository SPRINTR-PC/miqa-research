from .administration.index import index as administration_index
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
