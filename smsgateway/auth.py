import os
import hmac

from django.conf import settings
from rest_framework import authentication, exceptions, permissions

from .models import Device, hash_token


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """Authorization: Bearer <device token>. An unknown token is 401; a known but revoked or switched-off device is 403."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        scheme, _, raw = header.partition(" ")
        if scheme.lower() != "bearer" or not raw.strip():
            raise exceptions.AuthenticationFailed("Use Authorization: Bearer <device token>.")
        digest = hash_token(raw.strip())
        device = Device.objects.filter(token_hash=digest).first()
        if device is None or not hmac.compare_digest(device.token_hash, digest):
            raise exceptions.AuthenticationFailed("The device token is not valid.")
        if not device.is_active:
            raise exceptions.PermissionDenied("This device has been switched off.", code="device_disabled")
        device.touch()
        return device, device

    def authenticate_header(self, request):
        return "Bearer"


def require_https():
    """A setting wins; else the SMSGATEWAY_REQUIRE_HTTPS environment variable; else on whenever DEBUG is off."""
    if hasattr(settings, "SMSGATEWAY_REQUIRE_HTTPS"):
        return settings.SMSGATEWAY_REQUIRE_HTTPS
    env = os.environ.get("SMSGATEWAY_REQUIRE_HTTPS")
    if env is not None:
        return env.strip().lower() not in ("false", "0", "no")
    return not settings.DEBUG


class IsDevice(permissions.BasePermission):
    message = "A device token is required."

    def has_permission(self, request, view):
        if not isinstance(request.auth, Device):
            return False
        if require_https() and not request.is_secure():
            seen = f"scheme={request.scheme}, x-forwarded-proto={request.META.get('HTTP_X_FORWARDED_PROTO', 'none')}"
            raise exceptions.PermissionDenied(f"HTTPS is required ({seen}).", code="https_required")
        return True
