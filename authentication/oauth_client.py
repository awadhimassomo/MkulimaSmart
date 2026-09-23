"""
Kikapu OAuth Client
Handles OAuth 2.0 authentication flow with Kikapu
"""
import requests
import logging
from django.shortcuts import redirect
from django.contrib.auth import login, get_user_model
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from website.models import Farm

User = get_user_model()
logger = logging.getLogger(__name__)


def get_kikapu_oauth_url():
    """Get the Kikapu OAuth authorization URL"""
    kikapu_base = getattr(settings, 'KIKAPU_OAUTH_BASE_URL', 'http://localhost:8001')
    client_id = getattr(settings, 'KIKAPU_OAUTH_CLIENT_ID', 'mkulima_smart')
    redirect_uri = getattr(settings, 'KIKAPU_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/kikapu/callback')
    
    # Build OAuth authorization URL
    auth_url = (
        f"{kikapu_base}/oauth/authorize?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=read&"
        f"state=mkulima_smart_oauth"
    )
    
    return auth_url


@require_http_methods(["GET"])
def kikapu_oauth_login(request):
    """
    Initiate OAuth login with Kikapu
    Redirects user to Kikapu authorization page
    """
    auth_url = get_kikapu_oauth_url()
    logger.info(f"Redirecting to Kikapu OAuth: {auth_url}")
    return redirect(auth_url)


@require_http_methods(["GET"])
def kikapu_oauth_callback(request):
    """
    OAuth callback handler
    Receives authorization code from Kikapu and exchanges it for access token
    """
    # Get authorization code from query parameters
    code = request.GET.get('code')
    error = request.GET.get('error')
    state = request.GET.get('state')
    
    # Handle authorization errors
    if error:
        error_description = request.GET.get('error_description', 'Unknown error')
        logger.error(f"Kikapu OAuth error: {error} - {error_description}")
        return JsonResponse({
            'error': error,
            'message': f"Authorization failed: {error_description}"
        }, status=400)
    
    # Validate state parameter
    if state != 'mkulima_smart_oauth':
        logger.error(f"Invalid state parameter: {state}")
        return JsonResponse({
            'error': 'invalid_state',
            'message': 'Invalid state parameter'
        }, status=400)
    
    # Validate authorization code
    if not code:
        logger.error("No authorization code received")
        return JsonResponse({
            'error': 'invalid_request',
            'message': 'No authorization code received'
        }, status=400)
    
    try:
        # Exchange authorization code for access token
        token_response = exchange_code_for_token(code)
        
        if not token_response.get('access_token'):
            logger.error("Failed to get access token")
            return JsonResponse({
                'error': 'token_error',
                'message': 'Failed to obtain access token'
            }, status=400)
        
        access_token = token_response['access_token']
        
        # Fetch user info from Kikapu
        user_info = fetch_kikapu_user_info(access_token)
        
        if not user_info:
            logger.error("Failed to fetch user info")
            return JsonResponse({
                'error': 'userinfo_error',
                'message': 'Failed to fetch user information'
            }, status=400)
        
        # Create or update user in Mkulima Smart
        user = create_or_update_user(user_info)
        
        # Log the user in
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        logger.info(f"✅ User {user.phone_number} logged in via Kikapu OAuth")
        
        # Redirect to dashboard
        return redirect('website:dashboard')
        
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return JsonResponse({
            'error': 'server_error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)


def exchange_code_for_token(code):
    """
    Exchange authorization code for access token
    
    Args:
        code: Authorization code from Kikapu
        
    Returns:
        dict: Token response with access_token, refresh_token, etc.
    """
    kikapu_base = getattr(settings, 'KIKAPU_OAUTH_BASE_URL', 'http://localhost:8001')
    client_id = getattr(settings, 'KIKAPU_OAUTH_CLIENT_ID', 'mkulima_smart')
    client_secret = getattr(settings, 'KIKAPU_OAUTH_CLIENT_SECRET', 'mkulima_smart_secret_key_2024')
    redirect_uri = getattr(settings, 'KIKAPU_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/kikapu/callback')
    
    token_url = f"{kikapu_base}/oauth/token"
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info("Successfully exchanged code for token")
        
        return token_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Token exchange failed: {str(e)}")
        raise


def fetch_kikapu_user_info(access_token):
    """
    Fetch user information from Kikapu using access token
    
    Args:
        access_token: OAuth access token
        
    Returns:
        dict: User information from Kikapu
    """
    kikapu_base = getattr(settings, 'KIKAPU_OAUTH_BASE_URL', 'http://localhost:8001')
    userinfo_url = f"{kikapu_base}/oauth/userinfo"
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(userinfo_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        user_info = response.json()
        logger.info(f"Successfully fetched user info for: {user_info.get('phone_number')}")
        
        return user_info
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch user info: {str(e)}")
        raise


def create_or_update_user(kikapu_user_info):
    """
    Create or update Mkulima Smart user based on Kikapu user info
    
    Args:
        kikapu_user_info: User information from Kikapu
        
    Returns:
        User: Created or updated user object
    """
    phone_number = kikapu_user_info.get('phone_number')
    
    if not phone_number:
        raise ValueError("Phone number not provided in Kikapu user info")
    
    # Try to get existing user
    try:
        user = User.objects.get(phone_number=phone_number)
        logger.info(f"Existing user found: {phone_number}")
        
        # Update user info if provided
        updated = False
        if kikapu_user_info.get('given_name') and not user.first_name:
            user.first_name = kikapu_user_info['given_name']
            updated = True
        if kikapu_user_info.get('family_name') and not user.last_name:
            user.last_name = kikapu_user_info['family_name']
            updated = True
        if kikapu_user_info.get('email') and not user.email:
            user.email = kikapu_user_info['email']
            updated = True
        
        if updated:
            user.save()
            logger.info(f"Updated user info for: {phone_number}")
        
        return user
        
    except User.DoesNotExist:
        # Create new user
        logger.info(f"Creating new user from Kikapu: {phone_number}")
        
        user = User.objects.create_user(
            phone_number=phone_number,
            first_name=kikapu_user_info.get('given_name', ''),
            last_name=kikapu_user_info.get('family_name', ''),
            email=kikapu_user_info.get('email', ''),
            is_farmer=True
        )
        
        # Create a basic farm profile if business profile exists
        if 'profile' in kikapu_user_info and 'business_name' in kikapu_user_info['profile']:
            profile = kikapu_user_info['profile']
            
            Farm.objects.create(
                owner=user,
                name=profile.get('business_name', f"{user.get_full_name()}'s Farm"),
                location=profile.get('location', ''),
                size=0,  # Will be updated later
                description=profile.get('description', 'Synced from Kikapu')
            )
            
            logger.info(f"Created farm profile for: {phone_number}")
        
        logger.info(f"✅ New user created from Kikapu: {phone_number}")
        
        return user
