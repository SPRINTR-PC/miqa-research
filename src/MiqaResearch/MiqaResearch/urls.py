from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from MiqaResearch.interfaces.http.api.urls import api
from MiqaResearch.interfaces.http.views import (
    UploadDataView,
    administration_index,
    landing_page_index,
    monitor_index,
)
from MiqaResearch.interfaces.http.views.accounts.eid import (
    bankid_login_redirect,
    eid_callback,
    siths_login_redirect,
)

urlpatterns = [
    path('', landing_page_index, name='home'),
    path('administration/', administration_index, name='administration'),
    path('upload/', UploadDataView.as_view(), name="upload_data"),
    path('mradmin/', admin.site.urls),
    path('monitor/', monitor_index, name='monitor'),
    path('accounts/siths/login/', siths_login_redirect, name='siths_login'),
    path('accounts/bankid/login/', bankid_login_redirect, name='bankid_login'),
    path('accounts/eid/callback/', eid_callback, name='eid_callback'),
    path('accounts/', include('allauth.urls')),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('api/', api.urls, name="api"),
    path(settings.ADMIN_URL, admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += debug_toolbar_urls()
