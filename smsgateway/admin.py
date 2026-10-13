from django.contrib import admin

from .models import Contact, Device, Example, Guidance, InboundSms, OutboundSms


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "is_active", "paused", "last_seen", "battery_percent", "app_version")
    readonly_fields = ("token_prefix", "last_seen", "last_heartbeat", "created_at")
    exclude = ("token_hash",)


@admin.register(InboundSms)
class InboundSmsAdmin(admin.ModelAdmin):
    list_display = ("sender", "short_body", "status", "handler", "created_at")
    list_filter = ("status", "handler")
    search_fields = ("sender", "body")

    @admin.display(description="Message")
    def short_body(self, obj):
        return obj.body[:60]


@admin.register(OutboundSms)
class OutboundSmsAdmin(admin.ModelAdmin):
    list_display = ("to", "short_body", "status", "attempts", "created_at")
    list_filter = ("status", "handler")
    search_fields = ("to", "body")

    @admin.display(description="Message")
    def short_body(self, obj):
        return obj.body[:60]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("phone", "language", "opted_out", "last_message_at")
    list_filter = ("opted_out", "language")


@admin.register(Guidance)
class GuidanceAdmin(admin.ModelAdmin):
    list_display = ("updated_at",)


@admin.register(Example)
class ExampleAdmin(admin.ModelAdmin):
    list_display = ("farmer_says", "is_active", "created_at")
