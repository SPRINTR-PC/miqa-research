from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from MiqaResearch.data.models import BearerToken
from MiqaResearch.interfaces.http.api.auth_types import ClientCredentialsAuth

User = get_user_model()

class AuthBearerTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="password")
        self.bearer_token = BearerToken.generate_token(self.user)
        self.auth = ClientCredentialsAuth(required_scopes=["read"])

    def test_authenticate_success(self):
        request = self.factory.get("/")
        authenticated_user = self.auth.authenticate(request, self.bearer_token.plain_token)
        self.assertEqual(authenticated_user, self.user)
        
        # Verify last_used_at is updated
        self.bearer_token.refresh_from_db()
        self.assertIsNotNone(self.bearer_token.last_used_at)

    def test_authenticate_invalid_token(self):
        request = self.factory.get("/")
        authenticated_user = self.auth.authenticate(request, "invalid-token")
        self.assertIsNone(authenticated_user)

    def test_authenticate_inactive_token(self):
        self.bearer_token.is_active = False
        self.bearer_token.save()
        
        request = self.factory.get("/")
        authenticated_user = self.auth.authenticate(request, self.bearer_token.plain_token)
        self.assertIsNone(authenticated_user)
