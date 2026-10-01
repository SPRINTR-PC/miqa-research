from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from MiqaResearch.interfaces.http.api.urls import api
from MiqaResearch.interfaces.http.views import (
    UploadDataView,
    administration_index,
    dashboard_index,
    dashboard_project,
    dashboard_tab_consent_statistics,
    dashboard_tab_consent_statistics_content,
    dashboard_tab_etl_binding_edit,
    dashboard_tab_etl_bindings_create,
    dashboard_tab_etl_defaults_update,
    dashboard_tab_etl_job_detail,
    dashboard_tab_etl_job_retry,
    dashboard_tab_etl_pipelines,
    dashboard_tab_etl_pipelines_content,
    dashboard_tab_etl_script_archive,
    dashboard_tab_etl_script_customize,
    dashboard_tab_etl_script_edit,
    dashboard_tab_etl_script_version_create,
    dashboard_tab_etl_scripts_create,
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
            path('tabs/etl-pipelines/scripts/', dashboard_tab_etl_scripts_create, name='dashboard_tab_etl_scripts_create'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/edit/', dashboard_tab_etl_script_edit, name='dashboard_tab_etl_script_edit'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/versions/', dashboard_tab_etl_script_version_create, name='dashboard_tab_etl_script_version_create'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/archive/', dashboard_tab_etl_script_archive, name='dashboard_tab_etl_script_archive'),
            path('tabs/etl-pipelines/scripts/<uuid:script_id>/customize/', dashboard_tab_etl_script_customize, name='dashboard_tab_etl_script_customize'),
            path('tabs/etl-pipelines/bindings/', dashboard_tab_etl_bindings_create, name='dashboard_tab_etl_bindings_create'),
            path('tabs/etl-pipelines/bindings/<uuid:binding_id>/edit/', dashboard_tab_etl_binding_edit, name='dashboard_tab_etl_binding_edit'),
            path('tabs/etl-pipelines/jobs/<uuid:job_id>/', dashboard_tab_etl_job_detail, name='dashboard_tab_etl_job_detail'),
            path('tabs/etl-pipelines/jobs/<uuid:job_id>/retry/', dashboard_tab_etl_job_retry, name='dashboard_tab_etl_job_retry'),
            path('tabs/etl-pipelines/defaults/', dashboard_tab_etl_defaults_update, name='dashboard_tab_etl_defaults_update'),
        ])),
    ])),
    path(settings.ADMIN_URL, admin.site.urls),
    path('manuals/', include('documentation.urls')),
    path('monitor/', monitor_index, name='monitor'),
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
