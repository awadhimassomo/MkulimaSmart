from django.urls import path
from . import views

app_name = 'marketplace'

urlpatterns = [
    # Marketplace home page
    path('', views.home, name='home'),
<<<<<<< HEAD
    path('seller/', views.seller_start, name='seller_start'),
    path('seller/activate/', views.become_supplier, name='become_supplier'),
    path('supplier/', views.supplier_dashboard, name='supplier_dashboard'),
    path('supplier/products/new/', views.supplier_product_create, name='supplier_product_create'),
    path('supplier/products/<int:pk>/', views.supplier_product_detail, name='supplier_product_detail'),
    path('supplier/products/<int:pk>/edit/', views.supplier_product_edit, name='supplier_product_edit'),
=======
    # Add other marketplace URLs here as needed
>>>>>>> 
]
