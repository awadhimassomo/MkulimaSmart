import hmac

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication, exceptions, permissions

from .models import PartnerToken, hash_token


class PartnerTokenAuthentication(authentication.BaseAuthentication):
    """Authorization: Bearer <token issued to the partner>. Never logs the token."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        scheme, _, raw = header.partition(" ")
        if scheme.lower() != "bearer" or not raw.strip():
            raise exceptions.AuthenticationFailed("Use Authorization: Bearer <token>.")
        digest = hash_token(raw.strip())
        token = PartnerToken.objects.filter(token_hash=digest, is_active=True).first()
        # compare_digest keeps the check constant-time even though the lookup is by hash.
        if token is None or not hmac.compare_digest(token.token_hash, digest):
            raise exceptions.AuthenticationFailed("Invalid or revoked partner token.")
        token.mark_used()
        return AnonymousUser(), token

    def authenticate_header(self, request):
        return "Bearer"


class IsBridgePartner(permissions.BasePermission):
    message = "A partner token is required."

    def has_permission(self, request, view):
        if not isinstance(request.auth, PartnerToken):
            return False
        if getattr(settings, "KIKAPU_BRIDGE_REQUIRE_HTTPS", not settings.DEBUG) and not request.is_secure():
            raise exceptions.PermissionDenied("HTTPS is required.")
        return True
