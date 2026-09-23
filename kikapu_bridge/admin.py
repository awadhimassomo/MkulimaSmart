from django.contrib import admin, messages

from . import webhooks
from .models import PartnerToken, WebhookDelivery


@admin.register(PartnerToken)
class PartnerTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "token_prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    readonly_fields = ("token_prefix", "created_at", "last_used_at")
    fields = ("name", "token_prefix", "is_active", "created_at", "last_used_at")

    def has_add_permission(self, request):
        # Keys are issued with `manage.py issue_kikapu_token` so the raw value is shown exactly once.
        return False


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "state", "attempts", "last_response_code", "next_attempt_at", "created_at")
    list_filter = ("status", "gave_up")
    readonly_fields = [f.name for f in WebhookDelivery._meta.fields]
    actions = ["retry_now"]

    @admin.action(description="Retry now")
    def retry_now(self, request, queryset):
        queryset.filter(delivered_at__isnull=True).update(gave_up=False, attempts=0)
        sent, failed = webhooks.deliver_pending()
        self.message_user(request, f"Sent {sent}, still failing {failed}.", messages.INFO)
