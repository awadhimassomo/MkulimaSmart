from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("agronomists/", views.agronomists, name="agronomists"),
    path("agronomists/<int:pk>/toggle/", views.agronomist_toggle, name="agronomist_toggle"),
    path("agronomists/invite/", views.invite_create, name="invite_create"),
    path("agronomists/invite/<int:pk>/revoke/", views.invite_revoke, name="invite_revoke"),
    path("chats/", views.chats, name="chats"),
    path("chats/<int:pk>/", views.chat_detail, name="chat"),
    path("web-orders/", views.web_orders, name="web_orders"),
    path("web-orders/<int:pk>/", views.web_order_update, name="web_order_update"),
    path("products/", views.products, name="products"),
    path("products/<int:pk>/toggle/", views.product_toggle, name="product_toggle"),
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/<int:pk>/reset-link/", views.account_reset_link, name="account_reset_link"),
    path("accounts/<int:pk>/reset-email/", views.account_reset_email, name="account_reset_email"),
    path("deliveries/", views.deliveries, name="deliveries"),
    path("deliveries/<str:kind>/<int:pk>/retry/", views.delivery_retry, name="delivery_retry"),
]
