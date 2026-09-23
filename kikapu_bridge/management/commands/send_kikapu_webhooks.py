import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from kikapu_bridge.webhooks import deliver_pending


class Command(BaseCommand):
    help = (
        "Send queued order status updates to Kikapu. Run once from cron every minute, "
        "or with --loop as a long-running (e.g. PythonAnywhere always-on) task."
    )

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running, checking every --interval seconds.")
        parser.add_argument("--interval", type=int, default=30, help="Seconds between checks in --loop mode (default 30).")

    def handle(self, *args, **options):
        if not options["loop"]:
            sent, failed = deliver_pending()
            self.stdout.write(f"Sent {sent}, failed {failed}.")
            return

        interval = max(options["interval"], 5)
        self.stdout.write(f"Sending Kikapu webhooks every {interval}s. Ctrl+C to stop.")
        while True:
            close_old_connections()  # don't hold a stale database connection between rounds
            try:
                sent, failed = deliver_pending()
                if sent or failed:
                    self.stdout.write(f"Sent {sent}, failed {failed}.")
            except Exception as exc:  # keep the task alive; the next round retries
                self.stderr.write(f"Webhook round failed: {type(exc).__name__}: {exc}")
            self.stdout.flush()
            time.sleep(interval)
