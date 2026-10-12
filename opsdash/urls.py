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
    path("deliveries/", views.deliveries, name="deliveries"),
    path("deliveries/<str:kind>/<int:pk>/retry/", views.delivery_retry, name="delivery_retry"),
]
