from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from urllib.parse import urlencode
from django.contrib.auth import login as auth_login
from MiqaResearch.actions.accounts.eid import authenticate_with_eid

def siths_login_redirect(request):
    """
    Redirects to Svensk E-identitet for SITHS login.
    """
    # These should be in settings.py or env
    client_id = getattr(settings, 'EID_CLIENT_ID', 'test-client-id')
    redirect_uri = request.build_absolute_uri(reverse('eid_callback'))
    
    # Base URL for Svensk E-identitet OIDC/SAML (simplified for now)
    base_url = "https://server.e-identitet.se/v1/auth/openid" 
    
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid profile',
        'method': 'siths', # Specific for SITHS
        'state': 'siths', # Using state to remember method
    }
    
    return redirect(f"{base_url}?{urlencode(params)}")

def bankid_login_redirect(request):
    """
    Redirects to Svensk E-identitet for BankID login.
    """
    client_id = getattr(settings, 'EID_CLIENT_ID', 'test-client-id')
    redirect_uri = request.build_absolute_uri(reverse('eid_callback'))
    
    base_url = "https://server.e-identitet.se/v1/auth/openid"
    
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid profile',
        'method': 'bankid', # Specific for BankID
        'state': 'bankid', # Using state to remember method
    }
    
    return redirect(f"{base_url}?{urlencode(params)}")

def eid_callback(request):
    """
    Handles the callback from Svensk E-identitet.
    """
    code = request.GET.get('code')
    method = request.GET.get('state', 'bankid') # Simple way to track method

    if not code:
        return redirect('account_login')
    
    # Use action to authenticate
    user = authenticate_with_eid(code, method)
    
    if user:
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('home')
    
    return redirect('account_login')
