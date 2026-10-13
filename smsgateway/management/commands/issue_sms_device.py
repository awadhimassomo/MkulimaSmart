from django.core.management.base import BaseCommand

from smsgateway.models import Device


class Command(BaseCommand):
    help = "Create an SMS gateway phone and print its token once (it cannot be shown again)."

    def add_arguments(self, parser):
        parser.add_argument("name", help='For example "office phone 1" or "sandbox"')
        parser.add_argument("--project", default="mkulima", help="Which service the phone belongs to (default mkulima).")

    def handle(self, *args, **options):
        device, raw = Device.issue(options["name"], project=options["project"])
        self.stdout.write(f"Device {device.name} (id {device.pk}, project {device.project}) created.")
        self.stdout.write("Token (shown once, keep it safe):")
        self.stdout.write(raw)
