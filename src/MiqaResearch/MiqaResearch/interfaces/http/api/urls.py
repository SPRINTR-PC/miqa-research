from ninja import NinjaAPI, Router
from ninja.security import SessionAuth

from .auth_types import ClientCredentialsAuth
from .views.consent.router import router as dahboard_router
from .views.dicom.wado import router as wado_router
from .views.monitor.router import router as monitor_router
from .views.viewer.blinding import router as viewer_blinding_router
from .views.viewer.objects import router as viewer_objects_router

api = NinjaAPI(
    auth=ClientCredentialsAuth(required_scopes=["read"]),
    urls_namespace="api-v1"
)

api.add_router("/v1/monitor/", monitor_router)
# WADO serves machine clients (Bearer) and the browser viewer (Session); handlers branch on the
# caller type (views/dicom/access.py, #276).
api.add_router(
    "/v1/dicom/", wado_router, auth=[ClientCredentialsAuth(required_scopes=["read"]), SessionAuth()]
)
api.add_router("/v1/consent/", dahboard_router)
api.add_router("/v1/viewer/", viewer_objects_router)
api.add_router("/v1/viewer/", viewer_blinding_router)
