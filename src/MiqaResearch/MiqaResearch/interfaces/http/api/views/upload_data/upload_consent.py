import logging

from ninja import Schema, Router
from ninja.errors import HttpError

from MiqaResearch.interfaces.http.api.auth_types import ClientCredentialsAuth
from MiqaResearch.actions.consents.participant_consents import create_participant_consents
from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema
from contract.constants.scopes import SCOPE_UPSERT_CONSENT

logger = logging.getLogger(__name__)

router = Router()

class UploadConsentResponseSchema(Schema):
    message: str


@router.post(
    "/",
    response={201: UploadConsentResponseSchema, 401: UploadConsentResponseSchema, 500: UploadConsentResponseSchema},
    auth=ClientCredentialsAuth(required_scopes=[SCOPE_UPSERT_CONSENT])
)
def upload_consent_v1(request, data: list[UploadConsentSchema]):
    try:
        created_count, updated_count = create_participant_consents(new_consents=data)
    except Exception as e:
        logger.error("Error during participant consent upsertion", exc_info=True)
        return HttpError(
            status_code=500,
            message="Error during participant consent upsertion. Contact support if the issue persists."
        )

    return 201, {
        "message": (f"Consents uploaded successfully. Created {created_count} new consents, updated {updated_count} "
                    f"existing consents.")}
