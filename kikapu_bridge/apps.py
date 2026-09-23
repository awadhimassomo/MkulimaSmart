from django.apps import AppConfig


class KikapuBridgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kikapu_bridge"
    verbose_name = "Kikapu WhatsApp bridge"

    def ready(self):
        from inputs.signals import farmer_order_status_changed

        from . import webhooks

        farmer_order_status_changed.connect(webhooks.queue_status_update, dispatch_uid="kikapu_bridge.queue_status_update")
