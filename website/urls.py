from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views, api_views, auth_views as custom_auth_views

app_name = 'website'

urlpatterns = [
    # Landing Page & Main Sections
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Marketplace
    path('marketplace/', views.marketplace, name='marketplace'),
    path('marketplace/category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('marketplace/product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('marketplace/cart/', views.cart, name='cart'),
    path('marketplace/cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('marketplace/cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('marketplace/checkout/', views.checkout, name='checkout'),
    path('marketplace/orders/', views.order_list, name='order_list'),
    path('marketplace/orders/<int:order_id>/', views.order_detail, name='order_detail'),
    
    # Booking
    path('booking/', views.booking_home, name='booking_home'),
    path('booking/personnel/', views.personnel_booking, name='personnel_booking'),
    path('booking/soil/', views.soil_booking, name='soil_booking'),
    path('booking/rooms/', views.rooms_booking, name='rooms_booking'),
    path('booking/equipment/', views.equipment_booking, name='equipment_booking'),
    path('booking/machinery/', views.machinery_booking, name='machinery_booking'),
    path('booking/warehouse/', views.warehouse_list, name='warehouse_list'),
    path('booking/warehouse/<int:warehouse_id>/', views.warehouse_detail, name='warehouse_detail'),
    path('booking/warehouse/book/<int:warehouse_id>/', views.warehouse_booking, name='warehouse_booking'),
    path('booking/transport/', views.transport_list, name='transport_list'),
    path('booking/transport/<int:transport_id>/', views.transport_detail, name='transport_detail'),
    path('booking/transport/book/<int:transport_id>/', views.transport_booking, name='transport_booking'),
    path('booking/my-bookings/', views.my_bookings, name='my_bookings'),
    
    # Training
    path('training/', views.training_home, name='training_home'),
    path('training/course/<slug:slug>/', views.course_detail, name='course_detail'),
    path('training/lesson/<int:lesson_id>/', views.lesson_detail, name='lesson_detail'),
    path('training/my-courses/', views.my_courses, name='my_courses'),
    
    # About
    path('about/', views.about, name='about'),
    
    # Farm Management
    path('farm/<int:farm_id>/', views.farm_detail, name='farm_detail'),
    path('farm/add/', views.farm_add, name='farm_add'),
    path('farm/edit/<int:farm_id>/', views.farm_edit, name='farm_edit'),
    path('farm/<int:farm_id>/crop/add/', views.crop_add, name='crop_add'),
    path('farm/<int:farm_id>/crop/edit/<int:crop_id>/', views.crop_edit, name='crop_edit'),
    
    # Authentication
    path('register/', custom_auth_views.FarmerRegistrationView.as_view(), name='register'),
    path('login/', custom_auth_views.FarmerLoginView.as_view(), name='login'),
    path('logout/', custom_auth_views.logout_view, name='logout'),
    
    # Password Reset URLs
    path('password-reset/', custom_auth_views.CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', custom_auth_views.CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', custom_auth_views.CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', custom_auth_views.CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    
    # API Endpoints
    path('api/', include('website.api_urls')),
]
