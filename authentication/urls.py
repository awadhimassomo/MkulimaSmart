"""
URL Configuration for Authentication App
Handles Kikapu-Led Registration sync endpoints
"""
from django.urls import path
from . import views
from . import oauth_client

# No app_name needed since we're not using namespace

urlpatterns = [
    # API Endpoints for Kikapu Sync - use specific patterns to override website api_urls
    path('api/auth/farmer/sync-register/', views.sync_register_from_kikapu, name='kikapu_sync_register'),
    path('api/auth/farmer/sync-register', views.sync_register_from_kikapu, name='kikapu_sync_register_no_slash'),
    path('api/auth/farmer/complete-profile/', views.complete_profile_submit, name='complete_profile_submit'),
    path('api/auth/farmer/complete-profile', views.complete_profile_submit, name='complete_profile_submit_no_slash'),
    path('api/auth/check-sync/', views.check_sync_status, name='check_sync_status'),
    path('api/auth/check-sync', views.check_sync_status, name='check_sync_status_no_slash'),
    
    # Profile Completion Page
    path('auth/complete-profile/', views.profile_completion_page, name='profile_completion_page'),
    path('auth/complete-profile', views.profile_completion_page, name='profile_completion_page_no_slash'),
    
    # Kikapu OAuth Login
    path('auth/kikapu/login/', oauth_client.kikapu_oauth_login, name='kikapu_oauth_login'),
    path('auth/kikapu/callback/', oauth_client.kikapu_oauth_callback, name='kikapu_oauth_callback'),
]
