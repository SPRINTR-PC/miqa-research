from ninja import NinjaAPI, Router
from ninja.security import SessionAuth

from .auth_types import ClientCredentialsAuth
from .views.consent.router import router as dahboard_router
from .views.dicom.wado import router as wado_router
from .views.monitor.router import router as monitor_router
from .views.viewer.objects import router as viewer_objects_router

api = NinjaAPI(
    auth=ClientCredentialsAuth(required_scopes=["read"]),
    urls_namespace="api-v1"
)

api.add_router("/v1/monitor/", monitor_router)
api.add_router("/v1/dicom/", wado_router)
api.add_router("/v1/consent/", dahboard_router)
api.add_router("/v1/viewer/", viewer_objects_router)
