from django.urls import path

from . import api

app_name = "inputs_api"

urlpatterns = [
    # Shared
    path("options/", api.OptionsView.as_view(), name="options"),
    path("profile/", api.ProfileView.as_view(), name="profile"),

    # Input shop
    path("shop/dashboard/", api.ShopDashboardView.as_view(), name="shop_dashboard"),
    path("shop/stock/", api.StockListView.as_view(), name="stock_list"),
    path("shop/stock/<int:pk>/", api.StockDetailView.as_view(), name="stock_detail"),
    path("shop/stock/<int:pk>/adjust/", api.StockAdjustView.as_view(), name="stock_adjust"),
    path("shop/stock/<int:pk>/movements/", api.StockMovementsView.as_view(), name="stock_movements"),
    path("shop/sales/", api.SaleListView.as_view(), name="sale_list"),
    path("shop/sales/<int:pk>/", api.SaleDetailView.as_view(), name="sale_detail"),
    path("shop/catalog/", api.CatalogView.as_view(), name="catalog"),
    path("shop/catalog/manufacturers/", api.CatalogManufacturersView.as_view(), name="catalog_manufacturers"),
    path("shop/catalog/<int:pk>/", api.CatalogDetailView.as_view(), name="catalog_detail"),
    path("shop/orders/", api.ShopOrderListView.as_view(), name="shop_orders"),
    path("shop/orders/<int:pk>/", api.ShopOrderDetailView.as_view(), name="shop_order_detail"),
    path("shop/orders/<int:pk>/receive/", api.ShopOrderActionView.as_view(action="receive"), name="shop_order_receive"),
    path("shop/orders/<int:pk>/cancel/", api.ShopOrderActionView.as_view(action="cancel"), name="shop_order_cancel"),
    path("shop/farmer-orders/", api.FarmerOrderListView.as_view(), name="farmer_orders"),
    path("shop/farmer-orders/<int:pk>/", api.FarmerOrderDetailView.as_view(), name="farmer_order_detail"),
    path("shop/farmer-orders/<int:pk>/status/", api.FarmerOrderStatusView.as_view(), name="farmer_order_status"),

    # Manufacturer
    path("manufacturer/dashboard/", api.ManufacturerDashboardView.as_view(), name="manufacturer_dashboard"),
    path("manufacturer/products/", api.ManufacturerProductListView.as_view(), name="manufacturer_products"),
    path("manufacturer/products/<int:pk>/", api.ManufacturerProductDetailView.as_view(), name="manufacturer_product_detail"),
    path("manufacturer/products/<int:pk>/images/", api.ManufacturerProductImagesView.as_view(), name="manufacturer_product_images"),
    path("manufacturer/images/<int:pk>/", api.ManufacturerImageView.as_view(), name="manufacturer_image"),
    path("manufacturer/images/<int:pk>/set-primary/", api.ManufacturerImagePrimaryView.as_view(), name="manufacturer_image_primary"),
    path("manufacturer/orders/", api.ManufacturerOrderListView.as_view(), name="manufacturer_orders"),
    path("manufacturer/orders/<int:pk>/", api.ManufacturerOrderDetailView.as_view(), name="manufacturer_order_detail"),
    path("manufacturer/orders/<int:pk>/status/", api.ManufacturerOrderStatusView.as_view(), name="manufacturer_order_status"),
]
