from django.urls import re_path
from . import consumers

# WebSocket URL patterns with app prefix
websocket_urlpatterns = [
    re_path(r'^ws/gova-pp/chat/(?P<thread_id>[\w-]+)/$', consumers.ChatConsumer.as_asgi()),
]
