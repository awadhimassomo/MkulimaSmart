from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner
        # Used when URLRouter calls as_asgi_application
        self.asgi_routes = getattr(inner, "asgi_routes", [])

    async def __call__(self, scope, receive, send):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔐 JWT Middleware called for path: {scope.get('path', 'unknown')}")

        # Special case for test endpoint - bypass authentication
        if scope.get('path') == '/ws/test/':
            from django.contrib.auth.models import AnonymousUser
            scope["user"] = AnonymousUser()
            logger.info("✅ Test endpoint detected, bypassing authentication")
            return await self.inner(scope, receive, send)

        token = None
        token_source = None
        
        # Try to extract token from multiple sources
        try:
            headers = scope.get("headers", [])
            
            # Method 1: Check subprotocol header (sec-websocket-protocol)
            proto = next((v.decode() for k, v in headers if k == b"sec-websocket-protocol"), None)
            if proto:
                logger.info(f"📡 Found subprotocol: {proto}")
                if proto.startswith("Bearer "):
                    token = proto.split(" ", 1)[1]
                    token_source = "subprotocol"
                    logger.info("✅ Extracted token from subprotocol")
                # Also check if the entire protocol is the token (some clients do this)
                elif len(proto) > 50:  # JWT tokens are typically long
                    token = proto
                    token_source = "subprotocol (direct)"
                    logger.info("✅ Using subprotocol value as token")
            
            # Method 2: Check query string
            if not token:
                qs = parse_qs(scope.get("query_string", b"").decode())
                token = (qs.get("token") or [None])[0]
                if token:
                    token_source = "query_string"
                    logger.info("✅ Found token in query string")

            if not token:
                logger.warning("⚠️ No token found in request")
                scope["user"] = AnonymousUser()
                scope["auth_error"] = "no_token"
            else:
                logger.info(f"🔑 Authenticating with token from {token_source}")
                user = await self._get_user_from_token(token)
                scope["user"] = user
                
                if user.is_authenticated:
                    logger.info(f"✅ User authenticated successfully: {user.id}")
                else:
                    logger.warning("⚠️ Authentication failed - invalid token")
                    scope["auth_error"] = "invalid_token"
                    
            return await self.inner(scope, receive, send)
            
        except Exception as e:
            logger.error(f"❌ Error in JWT middleware: {str(e)}", exc_info=True)
            # Allow the connection to continue with AnonymousUser
            from django.contrib.auth.models import AnonymousUser
            scope["user"] = AnonymousUser()
            scope["auth_error"] = "exception"
            return await self.inner(scope, receive, send)

    @database_sync_to_async
    def _get_user_from_token(self, token):
        import logging
        logger = logging.getLogger(__name__)
        
        if not token:
            logger.info("ℹ️ No token provided")
            return AnonymousUser()
            
        # Log token prefix for debugging (first 20 chars)
        token_prefix = token[:20] if len(token) > 20 else token
        logger.info(f"🔍 Validating token (prefix): {token_prefix}...")
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            logger.info(f"✅ Token decoded successfully. Payload keys: {list(payload.keys())}")
            
            # Support both 'uid' (our format) and 'user_id' (standard JWT format)
            user_id = payload.get('uid') or payload.get('user_id')
            
            if not user_id:
                logger.warning(f"⚠️ No user identifier found in token payload. Keys: {list(payload.keys())}")
                return AnonymousUser()
            
            logger.info(f"🔍 Looking up user with id: {user_id}")
            user = User.objects.get(id=user_id)
            logger.info(f"✅ User found: {user.id}, {user.phone_number}")
            return user
        except jwt.ExpiredSignatureError:
            logger.warning("⏰ Token has expired")
            return AnonymousUser()
        except jwt.InvalidTokenError as e:
            logger.warning(f"❌ Invalid token: {str(e)}")
            return AnonymousUser()
        except User.DoesNotExist:
            logger.warning(f"❌ User with id {user_id} not found in database")
            return AnonymousUser()
        except Exception as e:
            logger.error(f"❌ Error decoding token: {str(e)}", exc_info=True)
            return AnonymousUser()
