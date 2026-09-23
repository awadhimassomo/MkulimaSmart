from django.core.management.base import BaseCommand

from kikapu_bridge.models import PartnerToken


class Command(BaseCommand):
    help = "Issue an API token for Kikapu to call /api/kikapu-bridge/. The token is printed once and never stored."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Kikapu", help="Label for this token, e.g. 'Kikapu production'.")
        parser.add_argument("--revoke-others", action="store_true", help="Deactivate all existing tokens (use when rotating).")

    def handle(self, *args, **options):
        if options["revoke_others"]:
            revoked = PartnerToken.objects.filter(is_active=True).update(is_active=False)
            self.stdout.write(f"Revoked {revoked} existing token(s).")
        token, raw = PartnerToken.issue(options["name"])
        self.stdout.write(self.style.SUCCESS(f"Issued token '{token.name}' ({token.token_prefix}…)."))
        self.stdout.write("Give this to Kikapu over a secure channel. It won't be shown again:\n")
        self.stdout.write(raw)
