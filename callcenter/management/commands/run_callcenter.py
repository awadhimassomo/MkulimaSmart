import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from callcenter.models import Heartbeat
from callcenter.services import enabled, sweep
from smsgateway import outbox as sms_outbox
from smsgateway import services as sms_services
from kikapu_bridge.webhooks import deliver_replies


class Command(BaseCommand):
    help = (
        "Run the call center's timers: hand unaccepted chats to the AI, take chats back from agronomists "
        "who went quiet, and send queued replies to Kikapu. Run it with --loop as an always-on task."
    )

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running, checking every --interval seconds.")
        parser.add_argument("--interval", type=int, default=10, help="Seconds between checks in --loop mode (default 10).")

    def run_once(self):
        Heartbeat.beat()
        counts = sweep() if enabled() else {}
        sent, failed = deliver_replies()
        sms_services.process_pending()  # farmers' SMS that wait for the AI or an agronomist
        sms_outbox.expire_old()
        return counts, sent, failed

    def handle(self, *args, **options):
        if not options["loop"]:
            counts, sent, failed = self.run_once()
            self.stdout.write(f"Sweep {counts or 'skipped (CALLCENTER_ENABLED is off)'}; replies sent {sent}, failed {failed}.")
            return

        interval = max(options["interval"], 3)
        self.stdout.write(f"Call center worker running every {interval}s. Ctrl+C to stop.")
        while True:
            close_old_connections()
            try:
                counts, sent, failed = self.run_once()
                if any(counts.values()) or sent or failed:
                    self.stdout.write(f"Sweep {counts}; replies sent {sent}, failed {failed}.")
            except Exception as exc:  # keep the worker alive; the next round retries
                self.stderr.write(f"Round failed: {type(exc).__name__}: {exc}")
            self.stdout.flush()
            time.sleep(interval)
