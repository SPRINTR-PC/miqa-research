from ninja import NinjaAPI, Router

from .views.monitor.router import router as monitor_router
from .views.dicom.wado import router as wado_router


api = NinjaAPI()

api.add_router("/v1/monitor/", monitor_router)
api.add_router("/v1/dicom/", wado_router)
