from django.apps import AppConfig


class SmsgatewayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "smsgateway"
    verbose_name = "SMS gateway (our own phone)"
