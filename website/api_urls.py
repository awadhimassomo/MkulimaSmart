from django.urls import path
from rest_framework import routers
from . import api_views
from .api_auth import (
    UserRegistrationAPIView, 
    UserLoginAPIView,
    UserLogoutAPIView,
    UserProfileAPIView,
    RefreshTokenView
)
from gova_pp.auth_api import obtain_token

app_name = 'website_api'

# DRF Router for viewsets
router = routers.DefaultRouter()

# API URLs
urlpatterns = [
    # Authentication endpoints
    # Old endpoints (for backward compatibility)
    path('auth/farmer/register/', api_views.register_farmer, name='farmer_register'),
    path('auth/token/', obtain_token, name='obtain_token'),
    
    # New JWT-based authentication endpoints
    path('auth/register/', UserRegistrationAPIView.as_view(), name='api_register'),
    path('auth/login/', UserLoginAPIView.as_view(), name='api_login'),
    path('auth/logout/', UserLogoutAPIView.as_view(), name='api_logout'),
    path('auth/refresh-token/', RefreshTokenView.as_view(), name='token_refresh'),
    path('auth/profile/', UserProfileAPIView.as_view(), name='user_profile'),
    
    # Weather forecast API endpoints (both /weather/ and /forecast/ for backward compatibility)
    path('weather/', api_views.weather_forecast, name='weather_forecast'),
    path('forecast/', api_views.weather_forecast, name='forecast_alias'),  # Alias for backward compatibility
    path('plan-timetable/', api_views.plan_farming_timetable, name='plan_timetable'),
<<<<<<< HEAD
    path('rainfall/monthly-plan/', api_views.monthly_rainfall_plan, name='monthly_rainfall_plan'),
=======
>>>>>>> 41ded11a88a936651d40cdbfd9f129ce3e3c686d
    path('crop-prices/', api_views.crop_prices, name='crop_prices'),
    
    # Farm API endpoints
    path('farms/', api_views.FarmListCreateAPIView.as_view(), name='farm_list'),
    path('farms/<int:pk>/', api_views.FarmDetailAPIView.as_view(), name='farm_detail'),
<<<<<<< HEAD
    path('farms/<int:pk>/mapping/start/', api_views.FarmMappingStartAPIView.as_view(), name='farm_mapping_start'),
    path('farms/<int:pk>/mapping/finish/', api_views.FarmMappingFinishAPIView.as_view(), name='farm_mapping_finish'),
    path('farms/<int:pk>/boundary/', api_views.FarmBoundaryUploadAPIView.as_view(), name='farm_boundary_upload'),
    path('farms/<int:pk>/verify-boundary/', api_views.FarmBoundaryVerificationAPIView.as_view(), name='farm_boundary_verify'),
    path('farms/<int:pk>/boundary/pdf/', api_views.FarmBoundaryPdfAPIView.as_view(), name='farm_boundary_pdf'),
=======
>>>>>>> 41ded11a88a936651d40cdbfd9f129ce3e3c686d
    path('farms/crops-weather/', api_views.get_farmer_crops_weather, name='farmer_crops_weather'),
    path('crops/', api_views.CropListCreateAPIView.as_view(), name='crop_list'),
    path('crops/<int:pk>/', api_views.CropDetailAPIView.as_view(), name='crop_detail'),
    
    # Marketplace API endpoints
    path('products/', api_views.ProductListAPIView.as_view(), name='product_list'),
    path('categories/', api_views.CategoryListAPIView.as_view(), name='category_list'),
]

# Add router URLs
urlpatterns += router.urls
