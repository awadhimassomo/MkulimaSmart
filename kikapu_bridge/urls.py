from django.urls import path

from . import views

app_name = "kikapu_bridge"

urlpatterns = [
    path("shops/", views.ShopsView.as_view(), name="shops"),
    path("inputs/", views.InputsView.as_view(), name="inputs"),
    path("inputs/prices/", views.InputPricesView.as_view(), name="input_prices"),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("orders/<str:order_id>/", views.OrderDetailView.as_view(), name="order_detail"),
]
