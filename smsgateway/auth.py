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


class IsDevice(permissions.BasePermission):
    message = "A device token is required."

    def has_permission(self, request, view):
        if not isinstance(request.auth, Device):
            return False
        if getattr(settings, "SMSGATEWAY_REQUIRE_HTTPS", not settings.DEBUG) and not request.is_secure():
            raise exceptions.PermissionDenied("HTTPS is required.", code="https_required")
        return True
