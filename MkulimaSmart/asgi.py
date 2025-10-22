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

# Define WebSocket URL patterns here after Django is initialized
websocket_urlpatterns = [
    path('ws/chat/<str:thread_id>/', ChatConsumer.as_asgi()),
    path('ws/test/', TestConsumer.as_asgi()),  # Simple test endpoint
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
