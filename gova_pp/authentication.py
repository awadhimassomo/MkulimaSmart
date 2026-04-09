from rest_framework import authentication, exceptions
from rest_framework.authentication import get_authorization_header
from django.conf import settings
from website.models import User
import jwt
import logging

# Set up logging
logger = logging.getLogger(__name__)

class JWTAuthentication(authentication.BaseAuthentication):
    """
    Custom JWT authentication for DRF to handle mobile app requests
    """
    
    def authenticate(self, request):
        logger.debug("JWTAuth: Starting authentication process")
        
        # Debug all request headers and important request data
        headers = {k: v for k, v in request.META.items() if k.startswith('HTTP_')}
        logger.debug(f"JWTAuth: All request headers: {headers}")
        logger.debug(f"JWTAuth: Request method: {request.method}")
        logger.debug(f"JWTAuth: Request path: {request.path}")
        
        # Log raw request body for debugging (but be careful with sensitive data)
        try:
            if request.body:
                logger.debug(f"JWTAuth: Request body (first 500 chars): {str(request.body)[:500]}")
        except Exception as e:
            logger.debug(f"JWTAuth: Could not read request body: {str(e)}")
        
        # First try Authorization header
        auth_header = get_authorization_header(request).decode('utf-8').strip() if get_authorization_header(request) else ''
        logger.debug(f"JWTAuth: Raw Authorization header: '{auth_header}'")
        
        token = None
        
        if not auth_header:
            # If no Authorization header, try X-Auth-Token
            token = request.META.get('HTTP_X_AUTH_TOKEN')
            logger.debug(f"JWTAuth: No Authorization header, X-Auth-Token: {token is not None}")
            
            # Also try token in request parameters
            if not token:
                token = request.GET.get('token') or request.data.get('token')
                logger.debug(f"JWTAuth: Checking request params for token: {token is not None}")
                
            if not token:
                logger.debug("JWTAuth: No token found in any location")
                return None
        else:
            # Handle different authentication schemes
            auth_parts = auth_header.split()
            logger.debug(f"JWTAuth: Auth parts count: {len(auth_parts)}")
            
            # No auth header parts
            if len(auth_parts) == 0:
                logger.debug("JWTAuth: Empty Authorization header")
                return None
                
            # Handle Authorization: <token> format
            if len(auth_parts) == 1:
                token = auth_parts[0]
                logger.debug("JWTAuth: Using token-only format")
                logger.debug(f"JWTAuth: Extracted token (first 20 chars): {token[:20]}...")
            # Handle Authorization: <scheme> <token> format
            elif len(auth_parts) == 2:
                # Extract token regardless of scheme (Bearer, Token, JWT)
                scheme, token = auth_parts
                logger.debug(f"JWTAuth: Using scheme '{scheme}' with token")
                logger.debug(f"JWTAuth: Extracted token (first 20 chars): {token[:20]}...")
            else:
                logger.debug(f"JWTAuth: Invalid format with {len(auth_parts)} parts")
                raise exceptions.AuthenticationFailed(
                    'Invalid Authorization header format. Use "Bearer <token>" format.'
                )
        
        try:
            logger.debug(f"JWTAuth: Attempting to decode token: {token[:10]}...")
            logger.debug(f"JWTAuth: Using secret key: {settings.SECRET_KEY[:5]}...")
            
            # Decode the JWT token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            logger.debug(f"JWTAuth: Successfully decoded token. Payload: {payload}")
            
            # Get the user based on the payload
            # Support both 'uid' (our token format) and 'user_id' (standard JWT format)
            user_id = payload.get('uid') or payload.get('user_id')
            logger.debug(f"JWTAuth: Extracted user_id from payload: {user_id}")
            
            if not user_id:
                logger.debug(f"JWTAuth: No user_id found in token payload. Payload keys: {list(payload.keys())}")
                raise exceptions.AuthenticationFailed('Invalid token payload: missing user identifier')
                
            try:
                user = User.objects.get(id=user_id)
                logger.debug(f"JWTAuth: User found: {user.id}, {user.phone_number}")
            except User.DoesNotExist:
                logger.debug(f"JWTAuth: No user found with id {user_id}")
                raise exceptions.AuthenticationFailed('User not found')
                
            # Return user and token
            logger.debug("JWTAuth: Authentication successful")
            return (user, token)
            
        except jwt.ExpiredSignatureError:
            logger.debug("JWTAuth: Token has expired")
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            logger.debug("JWTAuth: Invalid token format or signature")
            raise exceptions.AuthenticationFailed('Invalid token')
        except Exception as e:
            logger.debug(f"JWTAuth: Authentication exception: {str(e)}")
            raise exceptions.AuthenticationFailed(f'Authentication failed: {str(e)}')
    
    def authenticate_header(self, request):
        return 'Bearer'
