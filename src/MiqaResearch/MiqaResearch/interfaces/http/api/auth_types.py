from django.utils import timezone
from ninja.errors import HttpError
from ninja.security import HttpBearer
from oauth2_provider.models import AccessToken

from MiqaResearch.data.models import BearerToken


class ClientCredentialsAuth(HttpBearer):
    def __init__(self, required_scopes: list[str]):
        super().__init__()
        self.required_scopes = set(required_scopes)

    async def authenticate(self, request, token):
        try:
            access_token = await AccessToken.objects.select_related("application").aget(token=token)
            if access_token.expires < timezone.now():
                return None

            token_scopes = set(access_token.scope.split())
            if not self.required_scopes.issubset(token_scopes):
                raise HttpError(status_code=403, message="Insufficient scope")

            request.application = access_token.application
            request.access_token = access_token

            return access_token.application
        except AccessToken.DoesNotExist:
            return None
