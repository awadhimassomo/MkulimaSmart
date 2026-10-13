from django.urls import path

from . import views

app_name = "smsgateway"

urlpatterns = [
    path("v1/ping/", views.PingView.as_view(), name="ping"),
    path("v1/inbox/", views.InboxView.as_view(), name="inbox"),
    path("v1/outbox/", views.OutboxView.as_view(), name="outbox"),
    path("v1/outbox/status/", views.OutboxStatusBatchView.as_view(), name="outbox_status_batch"),
    path("v1/outbox/<int:pk>/status/", views.OutboxStatusView.as_view(), name="outbox_status"),
    path("v1/heartbeat/", views.HeartbeatView.as_view(), name="heartbeat"),
]
