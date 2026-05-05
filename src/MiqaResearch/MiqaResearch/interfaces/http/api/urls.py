from ninja import NinjaAPI, Router
from ninja.security import SessionAuth

from .auth_types import ClientCredentialsAuth
from .views.monitor.router import router as monitor_router
from .views.dicom.wado import router as wado_router


api = NinjaAPI(auth=ClientCredentialsAuth(required_scopes=["read"]))

api.add_router("/v1/monitor/", monitor_router)
api.add_router("/v1/dicom/", wado_router)
