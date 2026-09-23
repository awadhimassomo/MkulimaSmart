from django.urls import path

from . import views

app_name = "inputs"

urlpatterns = [
    path("", views.home, name="home"),

    # Input shop (agro-dealer)
    path("shop/", views.shop_dashboard, name="shop_dashboard"),
    path("shop/pos/", views.pos, name="pos"),
    path("shop/pos/checkout/", views.pos_checkout, name="pos_checkout"),
    path("shop/sales/", views.sale_list, name="sale_list"),
    path("shop/sales/<int:pk>/", views.sale_detail, name="sale_detail"),
    path("shop/stock/", views.stock_list, name="stock_list"),
    path("shop/stock/new/", views.stock_create, name="stock_create"),
    path("shop/stock/<int:pk>/", views.stock_edit, name="stock_edit"),
    path("shop/stock/<int:pk>/adjust/", views.stock_adjust, name="stock_adjust"),
    path("shop/catalog/", views.catalog, name="catalog"),
    path("shop/catalog/<int:pk>/", views.catalog_product, name="catalog_product"),
    path("shop/order-list/", views.order_cart, name="order_cart"),
    path("shop/order-list/update/", views.order_cart_update, name="order_cart_update"),
    path("shop/order-list/submit/<int:manufacturer_id>/", views.order_submit, name="order_submit"),
    path("shop/orders/", views.order_list, name="order_list"),
    path("shop/orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("shop/orders/<int:pk>/action/", views.order_action, name="order_action"),
    path("shop/farmer-orders/", views.farmer_order_list, name="farmer_order_list"),
    path("shop/farmer-orders/<int:pk>/", views.farmer_order_detail, name="farmer_order_detail"),

    # Manufacturer
    path("manufacturer/", views.manufacturer_dashboard, name="manufacturer_dashboard"),
    path("manufacturer/products/", views.manufacturer_products, name="manufacturer_products"),
    path("manufacturer/products/new/", views.manufacturer_product_form, name="manufacturer_product_create"),
    path("manufacturer/products/<int:pk>/", views.manufacturer_product_form, name="manufacturer_product_edit"),
    path("manufacturer/images/<int:pk>/", views.manufacturer_image_action, name="manufacturer_image_action"),
    path("manufacturer/orders/", views.manufacturer_orders, name="manufacturer_orders"),
    path("manufacturer/orders/<int:pk>/", views.manufacturer_order_detail, name="manufacturer_order_detail"),
]
