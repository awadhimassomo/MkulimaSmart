from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for API viewsets
router = DefaultRouter()
router.register(r'crops', views.CropDataViewSet)
router.register(r'soil', views.SoilDataViewSet)
router.register(r'predictions', views.PredictionResultViewSet)
router.register(r'notifications', views.NotificationViewSet, basename='notification')

# App name for namespacing URLs
app_name = 'predictions'

urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),
    path('api/generate/', views.GeneratePredictionView.as_view(), name='generate_prediction'),
    
    # Form views for manual rain observations
    path('rain-observation/', views.RainObservationFormView.as_view(), name='rain_observation_form'),
    path('rain-observation/thanks/', views.rain_observation_thanks, name='rain_observation_thanks'),
    
    # Notification dashboard views
    path('notifications/', views.NotificationDashboardView.as_view(), name='notifications_dashboard'),
    path('notifications/<int:pk>/', views.NotificationDetailView.as_view(), name='notification_detail'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_read'),
    
    # Admin dashboard views
    path('admin/prediction-quality/', views.prediction_quality_dashboard, name='prediction_quality_dashboard'),
]
