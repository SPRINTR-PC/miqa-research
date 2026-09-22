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
        ])),
    ])),
    path(settings.ADMIN_URL, admin.site.urls),
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

    from MiqaResearch.interfaces.http.views.prototype_etl_management.index import index as prototype_etl_management_index

    urlpatterns += debug_toolbar_urls()
    urlpatterns += [
        path('prototype/etl-management/', prototype_etl_management_index, name='prototype_etl_management'),
    ]
