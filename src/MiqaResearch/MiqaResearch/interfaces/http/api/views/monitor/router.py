from ninja import Router
from ninja.security import SessionAuth

from .monitor_columns import router as monitor_columns_router
from .filter import router as monitor_filter_router
from ...auth_types import ClientCredentialsAuth

router = Router(auth=(ClientCredentialsAuth([]), SessionAuth()))
router.add_router("/columnlist", monitor_columns_router)
router.add_router("/filter", monitor_filter_router)