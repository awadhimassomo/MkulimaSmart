"""
URL configuration for MkulimaSmart project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.conf.urls.i18n import i18n_patterns
from gova_pp import chat_api
from gova_pp import webhook_views
from chat.views import ThreadMessageCreateView

# Non-prefixed URLs (don't get language prefix)
urlpatterns = [
    # Language switcher URL
    path('i18n/', include('django.conf.urls.i18n')),
    
    # Redirect root to default language home
    path('', RedirectView.as_view(url='/en/', permanent=False)),
    
    # Authentication & Sync APIs (MUST come before api/ to avoid conflicts)
    path('', include('authentication.urls')),
    
    # API URLs (no language prefix)
    path('api/', include('website.api_urls')),
    
    # Direct access to chat API endpoints for mobile app integration
    path('api/chat/threads/', chat_api.chat_threads_endpoint, name='direct_chat_threads'),
    
    # Route encrypted media messages to our new ThreadMessageCreateView 
    path('api/chat/threads/<int:thread_id>/messages/', ThreadMessageCreateView.as_view(), name='encrypted_chat_messages'),
    
    # Webhook endpoints (no language prefix for external integrations)
    path('api/chat/webhook/', webhook_views.chat_webhook, name='chat_webhook'),
    path('api/chat/webhook/reply/', webhook_views.chat_webhook_reply, name='chat_webhook_reply'),
    path('api/chat/webhook/test/', webhook_views.webhook_test, name='webhook_test'),
    
    # Chat test page (no language prefix for WebSocket testing)
    path('chat/', include('chat.urls', namespace='chat')),
]

# Prefixed URLs with language code
urlpatterns += i18n_patterns(
    # Admin site
    path('admin/', admin.site.urls),
    
    # Authentication URLs with auth namespace - DISABLED (using custom auth in website app)
    # path('accounts/', include('django.contrib.auth.urls')),
    
    # Include tradepoint URLs FIRST to avoid conflicts with website URLs
    path('marketplace/', include('marketplace.urls', namespace='marketplace')),
    
    # Include website URLs
    path('', include('website.urls', namespace='website')),
    
    # Gova PP App
    path('gova-pp/', include('gova_pp.urls', namespace='gova_pp')),
    
    # Predictions App
    path('predictions/', include('predictions.urls', namespace='predictions')),
    
    # Training App
    path('training/', include('training.urls', namespace='training')),
    
    # Include default language in URL
    prefix_default_language=True
)

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
