import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login

User = get_user_model()

def authenticate_with_eid(code, method):
    """
    Action to authenticate a user with Svensk E-identitet.
    """
    client_id = settings.EID_CLIENT_ID
    client_secret = settings.EID_CLIENT_SECRET
    
    if not client_id or not client_secret:
        # Fallback for development if not configured
        if settings.DEBUG:
            email = 'debug-user@example.com'
            user, created = User.objects.get_or_create(email=email, defaults={
                'username': email,
                'first_name': 'Debug User',
            })
            return user
        return None
