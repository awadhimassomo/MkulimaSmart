from django.urls import path
from . import views
from .views import ThreadMessageCreateView, MediaRetrieveView

app_name = 'chat'

urlpatterns = [
    path('test/', views.ws_test, name='ws_test'),
    
    # API endpoint for sending messages with encrypted media
    path('threads/<int:thread_id>/messages/', ThreadMessageCreateView.as_view(), name='thread-message-create'),
    
    # Endpoint for retrieving encrypted media files
    path('media/<int:media_id>/', MediaRetrieveView.as_view(), name='media-retrieve'),
]
