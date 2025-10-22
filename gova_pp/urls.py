from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import api_views
from . import auth_api
from . import chat_api
from . import webhook_views
from django.conf import settings

app_name = 'gova_pp'

# Set up DRF router for API endpoints
router = DefaultRouter()
router.register(r'api/messages', api_views.MessageViewSet, basename='message')

urlpatterns = [
    # Authentication
    path('login/', views.government_login, name='login'),
    path('logout/', views.government_logout, name='logout'),
    
    # Alerts URLs
    path('alerts/', views.alerts, name='alerts'),
    path('alerts/create/', views.create_alert, name='create_alert'),
    path('alerts/send/<int:alert_id>/', views.send_alert, name='send_alert'),
    path('alerts/delete/<int:alert_id>/', views.delete_alert, name='delete_alert'),
    path('reports/', views.reports, name='reports'),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Messages
    path('messages/', views.messages_list, name='messages_list'),
    path('messages/<int:message_id>/', views.message_detail, name='message_detail'),
    
    # Image Analysis
    path('analyze-image/<int:message_id>/', views.analyze_image, name='analyze_image'),
    
    # API endpoints
    path('api/receive-message/', views.receive_farmer_message, name='receive_farmer_message'),
    path('api/token/', auth_api.obtain_token, name='obtain_token'),
    
    # Chat API endpoints
    path('api/chat/threads/', chat_api.chat_threads_endpoint, name='chat_threads'),
    path('api/chat/threads/create/', chat_api.create_chat_thread, name='create_chat_thread'),
    path('api/chat/threads/<int:thread_id>/messages/', chat_api.chat_thread_messages, name='chat_thread_messages'),
    # Change to match what the Flutter app is expecting
    path('api/chat/threads/<int:thread_id>/messages/', chat_api.create_thread_message, name='create_thread_message', kwargs={'allow_post': True}),
    
    # Webhook endpoints
    path('api/chat/webhook/', webhook_views.chat_webhook, name='chat_webhook'),
    path('api/chat/webhook/reply/', webhook_views.chat_webhook_reply, name='chat_webhook_reply'),
    path('api/chat/webhook/test/', webhook_views.webhook_test, name='webhook_test'),
    
    # Include DRF router for API views
    path('', include(router.urls)),
]
