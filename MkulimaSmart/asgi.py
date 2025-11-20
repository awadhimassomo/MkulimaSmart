"""
ASGI config for MkulimaSmart project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MkulimaSmart.settings')

# Initialize Django FIRST
django_asgi_app = get_asgi_application()

# THEN import other modules that depend on Django being configured
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from chat.jwt_middleware import JWTAuthMiddleware

# Now it's safe to import consumers
from chat.test_consumer import TestConsumer
from chat.consumers import ChatConsumer

# Import WebSocket URLs from different apps
from gova_pp.routing import websocket_urlpatterns as gova_ws_urls
from chat.routing import websocket_urlpatterns as chat_ws_urls

# Define WebSocket URL patterns here after Django is initialized
websocket_urlpatterns = [
    # Test endpoint
    path('ws/test/', TestConsumer.as_asgi()),
] + chat_ws_urls + gova_ws_urls  # Include chat and gova_pp WebSocket URLs

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
