from django.urls import path
from . import views

app_name = 'marketplace'

urlpatterns = [
    # Marketplace home page
    path('', views.home, name='home'),
    path('seller/', views.seller_start, name='seller_start'),
    path('seller/activate/', views.become_supplier, name='become_supplier'),
    path('seller/profile/', views.supplier_onboarding, name='supplier_onboarding'),
    path('supplier/', views.supplier_dashboard, name='supplier_dashboard'),
    path('supplier/seedling-batches/new/', views.supplier_seedling_batch_create, name='supplier_seedling_batch_create'),
    path('supplier/seedling-batches/<int:pk>/qr/', views.supplier_batch_qr_print, name='batch_qr_print'),
    path('supplier/seedling-batches/<int:pk>/qr.png', views.supplier_batch_qr_image, name='batch_qr_image'),
    path('supplier/products/new/', views.supplier_product_create, name='supplier_product_create'),
    path('supplier/products/<int:pk>/', views.supplier_product_detail, name='supplier_product_detail'),
    path('supplier/products/<int:pk>/edit/', views.supplier_product_edit, name='supplier_product_edit'),
    path('seedling-batches/scan/<str:seedling_batch_id>/', views.batch_scan, name='batch_scan'),
    path('planting-intake/<str:seedling_batch_id>/', views.planting_record_qr_intake, name='planting_qr_intake'),
]
