from django.core.management.base import BaseCommand

from kikapu_bridge.webhooks import deliver_pending


class Command(BaseCommand):
    help = "Send queued order status updates to Kikapu. Run from cron every minute."

    def handle(self, *args, **options):
        sent, failed = deliver_pending()
        self.stdout.write(f"Sent {sent}, failed {failed}.")
