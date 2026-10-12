from django.apps import AppConfig


class InputsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inputs"
    verbose_name = "Input Supply Chain"

    def ready(self):
        from django.db.models.signals import post_save

        from . import website_listing
        from .models import ShopStockItem, WholesaleProduct

        for model in (ShopStockItem, WholesaleProduct):
            post_save.connect(website_listing.sync_listing, sender=model, dispatch_uid=f"inputs.website_listing.{model.__name__}")
