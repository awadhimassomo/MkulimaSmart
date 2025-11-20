from django.urls import path
from . import consumers

# WebSocket URL patterns for chat
websocket_urlpatterns = [
    path('ws/chat/<int:thread_id>/', consumers.ChatConsumer.as_asgi()),
]

