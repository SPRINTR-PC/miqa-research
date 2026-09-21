from ninja import Router
from ninja.security import SessionAuth

from ...auth_types import ClientCredentialsAuth
from .consent_dashboard import router as consent_dashboard_router

router = Router(auth=(ClientCredentialsAuth([]), SessionAuth()))
router.add_router("/dashboard", consent_dashboard_router)
