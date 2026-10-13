from django.core.management.base import BaseCommand

from smsgateway import outbox, services


class Command(BaseCommand):
    help = "Answer waiting SMS (the slow ones) and expire old unsent replies. Also run by run_callcenter."

    def handle(self, *args, **options):
        counts = services.process_pending()
        expired = outbox.expire_old()
        self.stdout.write(f"Answered {counts['answered']}, gave up on {counts['gave_up']}, expired {expired} unsent replies.")
