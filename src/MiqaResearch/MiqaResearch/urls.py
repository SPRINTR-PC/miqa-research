from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from MiqaResearch.interfaces.http.api.urls import api
from MiqaResearch.interfaces.http.views import (
    UploadDataView,
    administration_index,
    dashboard_index,
    dashboard_project,
    dashboard_tab_api_client_issue,
    dashboard_tab_api_client_revoke,
    dashboard_tab_api_client_rotate,
    dashboard_tab_api_client_update,
    dashboard_tab_api_clients,
    dashboard_tab_consent_statistics,
    dashboard_tab_consent_statistics_content,
    dashboard_tab_etl_binding_config_fields,
    dashboard_tab_etl_binding_edit,
    dashboard_tab_etl_bindings_create,
    dashboard_tab_etl_datatype_schema,
    dashboard_tab_etl_defaults_update,
    dashboard_tab_etl_job_detail,
    dashboard_tab_etl_job_retry,
    dashboard_tab_etl_location_grant_delete,
    dashboard_tab_etl_location_grant_edit,
    dashboard_tab_etl_location_grants_create,
    dashboard_tab_etl_pipelines,
    dashboard_tab_etl_pipelines_content,
    dashboard_tab_etl_script_archive,
    dashboard_tab_etl_script_customize,
    dashboard_tab_etl_script_edit,
    dashboard_tab_etl_scripts_create,
    dashboard_tab_etl_source_location_delete,
    dashboard_tab_etl_source_location_edit,
    dashboard_tab_etl_source_locations_create,
    dashboard_tab_etl_storage_browse,
    dashboard_tab_goals,
    landing_page_index,
    monitor_index,
)
from MiqaResearch.interfaces.http.views.accounts.eid import (
    bankid_login_redirect,
    eid_callback,
)
from MiqaResearch.interfaces.http.views.accounts.login import LoginView
from MiqaResearch.interfaces.http.views.accounts.logout import LogoutView
from MiqaResearch.interfaces.http.views.viewer.dev import dev as viewer_dev
from MiqaResearch.interfaces.http.views.viewer.page import unlinked_viewer_page, viewer_page

urlpatterns = [
    path('', landing_page_index, name='home'),
    path('administration/', administration_index, name='administration'),
    path('upload/', UploadDataView.as_view(), name="upload_data"),
    path('dashboard/', include([
        path('', dashboard_index, name='dashboard'),
        path('<uuid:project_id>/', include([
            path('', dashboard_project, name='dashboard_project'),
            path('tabs/consent-statistics/', dashboard_tab_consent_statistics, name='dashboard_tab_consent_statistics'),
            path('tabs/consent-statistics/content/', dashboard_tab_consent_statistics_content, name='dashboard_tab_consent_statistics_content'),
            path('tabs/goals/', dashboard_tab_goals, name='dashboard_tab_goals'),
            path('tabs/etl-pipelines/', dashboard_tab_etl_pipelines, name='dashboard_tab_etl_pipelines'),
            path('tabs/etl-pipelines/content/', dashboard_tab_etl_pipelines_content, name='dashboard_tab_etl_pipelines_content'),
            path('tabs/etl-pipelines/datatype-schema/', dashboard_tab_etl_datatype_schema, name='dashboard_tab_etl_datatype_schema'),
            path('tabs/etl-pipelines/scripts/', dashboard_tab_etl_scripts_create, name='dashboard_tab_etl_scripts_create'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/edit/', dashboard_tab_etl_script_edit, name='dashboard_tab_etl_script_edit'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/archive/', dashboard_tab_etl_script_archive, name='dashboard_tab_etl_script_archive'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/customize/', dashboard_tab_etl_script_customize, name='dashboard_tab_etl_script_customize'),
            path('tabs/etl-pipelines/bindings/', dashboard_tab_etl_bindings_create, name='dashboard_tab_etl_bindings_create'),
            path('tabs/etl-pipelines/bindings/<uuid:binding_id>/edit/', dashboard_tab_etl_binding_edit, name='dashboard_tab_etl_binding_edit'),
            path('tabs/etl-pipelines/bindings/config-fields/', dashboard_tab_etl_binding_config_fields, name='dashboard_tab_etl_binding_config_fields'),
            path('tabs/etl-pipelines/jobs/<uuid:job_id>/', dashboard_tab_etl_job_detail, name='dashboard_tab_etl_job_detail'),
            path('tabs/etl-pipelines/jobs/<uuid:job_id>/retry/', dashboard_tab_etl_job_retry, name='dashboard_tab_etl_job_retry'),
            path('tabs/etl-pipelines/defaults/', dashboard_tab_etl_defaults_update, name='dashboard_tab_etl_defaults_update'),
            path('tabs/etl-pipelines/sources/', dashboard_tab_etl_source_locations_create, name='dashboard_tab_etl_source_locations_create'),
            path('tabs/etl-pipelines/sources/<uuid:location_id>/edit/', dashboard_tab_etl_source_location_edit, name='dashboard_tab_etl_source_location_edit'),
            path('tabs/etl-pipelines/grants/<uuid:grant_id>/edit/', dashboard_tab_etl_location_grant_edit, name='dashboard_tab_etl_location_grant_edit'),
            path('tabs/etl-pipelines/sources/<uuid:location_id>/delete/', dashboard_tab_etl_source_location_delete, name='dashboard_tab_etl_source_location_delete'),
            path('tabs/etl-pipelines/storages/<uuid:storage_id>/browse/', dashboard_tab_etl_storage_browse, name='dashboard_tab_etl_storage_browse'),
            path('tabs/etl-pipelines/grants/', dashboard_tab_etl_location_grants_create, name='dashboard_tab_etl_location_grants_create'),
            path('tabs/etl-pipelines/grants/<uuid:grant_id>/delete/', dashboard_tab_etl_location_grant_delete, name='dashboard_tab_etl_location_grant_delete'),
            path('tabs/api-clients/', dashboard_tab_api_clients, name='dashboard_tab_api_clients'),
            path('tabs/api-clients/issue/', dashboard_tab_api_client_issue, name='dashboard_tab_api_client_issue'),
            path('tabs/api-clients/<uuid:binding_id>/update/', dashboard_tab_api_client_update, name='dashboard_tab_api_client_update'),
            path('tabs/api-clients/<uuid:binding_id>/rotate/', dashboard_tab_api_client_rotate, name='dashboard_tab_api_client_rotate'),
            path('tabs/api-clients/<uuid:binding_id>/revoke/', dashboard_tab_api_client_revoke, name='dashboard_tab_api_client_revoke'),
        ])),
    ])),
    path(settings.ADMIN_URL, admin.site.urls),
    path('manuals/', include('documentation.urls')),
    path('monitor/', monitor_index, name='monitor'),
    path('projects/<uuid:project_id>/participants/<uuid:participant_id>/viewer/', viewer_page, name='viewer_page'),
    path('projects/<uuid:project_id>/unlinked-imaging/<uuid:key_id>/viewer/', unlinked_viewer_page,
         name='unlinked_viewer_page'),
    path('viewer/dev/', viewer_dev, name='viewer_dev'),  # DEBUG-only, for the browser harness (#278, #279)
    path('accounts/bankid/login/', bankid_login_redirect, name='bankid_login'),
    path('accounts/eid/callback/', eid_callback, name='eid_callback'),
    path('accounts/login/', LoginView.as_view(), name='account_login'),
    path('accounts/logout/', LogoutView.as_view(), name='account_logout'),
    path('accounts/', include('allauth.urls')),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('api/', api.urls, name="api"),
]

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
