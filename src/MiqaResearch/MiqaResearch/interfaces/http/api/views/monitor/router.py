from ninja import Router

from .monitor_columns import router as monitor_columns_router
from .filter import router as monitor_filter_router

router = Router()
router.add_router("/columnlist", monitor_columns_router)
router.add_router("/filter", monitor_filter_router)