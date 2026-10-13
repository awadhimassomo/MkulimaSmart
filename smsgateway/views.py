"""
The phone's API: /api/sms-gateway/v1/ (see docs/integrations/sms-gateway-device-api.md).

    GET  ping/                    check the token
    POST inbox/                   the phone uploads received SMS
    GET  outbox/                  the phone fetches replies to send
    POST outbox/<id>/status/      the phone reports what happened to one reply
    POST outbox/status/           the same for several at once
    POST heartbeat/               "I am alive" with battery, network and queue sizes; returns our settings
"""
import re

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import outbox, services
from .auth import DeviceTokenAuthentication, IsDevice
from .models import Device, OutboundSms

MAX_BATCH = 50
STATUSES = ("sent", "delivered", "failed")


def fail(status, code, message, **extra):
    return Response({"error": {"code": code, "message": message, **extra}}, status=status)


def now_iso():
    return timezone.now().isoformat().replace("+00:00", "Z")


def version_tuple(value):
    return tuple(int(part) for part in re.findall(r"\d+", value or "")[:3])


class UpgradeRequired(exceptions.APIException):
    status_code = 426
    default_code = "upgrade_required"

    def __init__(self, minimum):
        super().__init__(f"Please update the app to version {minimum} or newer.")
        self.minimum = minimum


class GatewayView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]

    def handle_exception(self, exc):
        if isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated)):
            return fail(401, "invalid_token", str(exc.detail))
        if isinstance(exc, exceptions.PermissionDenied):
            code = getattr(exc.detail, "code", None)
            return fail(403, code if code in ("device_disabled", "https_required") else "device_disabled", str(exc.detail))
        if isinstance(exc, UpgradeRequired):
            return fail(426, "upgrade_required", str(exc.detail), min_app_version=exc.minimum)
        if isinstance(exc, exceptions.ParseError):
            return fail(400, "invalid_request", "The request body is not valid JSON.")
        if isinstance(exc, exceptions.Throttled):
            return fail(429, "rate_limited", "Too many requests.", retry_after=exc.wait)
        return super().handle_exception(exc)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # An app older than the oldest we accept must update; it keeps storing messages meanwhile.
        device = request.auth
        version = request.headers.get("X-App-Version") or (request.data.get("app_version") if hasattr(request.data, "get") else "")
        if version and version_tuple(version) < version_tuple(device.min_app_version):
            raise UpgradeRequired(device.min_app_version)

    def finalize_response(self, request, response, *args, **kwargs):
        if isinstance(getattr(response, "data", None), dict) and "retry_after" in response.data.get("error", {}):
            response["Retry-After"] = str(int(response.data["error"]["retry_after"] or 5))
        return super().finalize_response(request, response, *args, **kwargs)


class PingView(GatewayView):
    def get(self, request):
        return Response({"ok": True, "device": request.auth.name, "server_time": now_iso()})


class InboxView(GatewayView):
    def post(self, request):
        items = request.data.get("messages") if hasattr(request.data, "get") else None
        if not isinstance(items, list) or not items:
            return fail(422, "validation_failed", "Send between 1 and 50 messages.", fields={"messages": ["Send between 1 and 50 messages."]})
        if len(items) > MAX_BATCH:
            return fail(413, "batch_too_large", f"Send at most {MAX_BATCH} messages at a time.")
        results = services.store_inbound(request.auth, items)
        return Response({"results": results, "server_time": now_iso()})


class OutboxView(GatewayView):
    def get(self, request):
        device = request.auth
        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 20))
        except (TypeError, ValueError):
            limit = 10
        leased = outbox.lease(device, limit)
        return Response({
            "messages": [
                {
                    "id": sms.pk, "to": sms.to, "body": sms.body, "encoding": sms.encoding, "parts": sms.parts,
                    "lease_expires_at": sms.lease_expires_at.isoformat().replace("+00:00", "Z"),
                    "expires_at": sms.expires_at.isoformat().replace("+00:00", "Z"),
                }
                for sms in leased
            ],
            "poll_after_seconds": device.poll_interval_seconds if leased else device.idle_poll_interval_seconds,
            "server_time": now_iso(),
        })


def _apply_report(device, pk, data):
    """Returns (ok, error message). One report from the phone about one outbox message."""
    status = data.get("status") if isinstance(data, dict) else None
    if status not in STATUSES:
        return False, "status must be sent, delivered or failed"
    sms = OutboundSms.objects.filter(pk=pk, device=device).first()
    if sms is None:
        return False, "unknown message"
    at = parse_datetime(data.get("at")) if isinstance(data.get("at"), str) else None
    outbox.apply_status(sms, status, error=str(data.get("error") or ""), retryable=bool(data.get("retryable")), at=at)
    return True, ""


class OutboxStatusView(GatewayView):
    def post(self, request, pk):
        ok, message = _apply_report(request.auth, pk, request.data)
        if not ok:
            if message == "unknown message":
                return fail(404, "not_found", "No such message for this device.")
            return fail(422, "validation_failed", message, fields={"status": [message]})
        return Response({"ok": True})


class OutboxStatusBatchView(GatewayView):
    def post(self, request):
        items = request.data.get("results") if hasattr(request.data, "get") else None
        if not isinstance(items, list) or not items:
            return fail(422, "validation_failed", "Send a list of results.", fields={"results": ["Required."]})
        if len(items) > 100:
            return fail(413, "batch_too_large", "Send at most 100 results at a time.")
        results = []
        for item in items:
            pk = item.get("id") if isinstance(item, dict) else None
            ok, message = _apply_report(request.auth, pk, item) if isinstance(pk, int) else (False, "missing id")
            results.append({"id": pk, "ok": ok, **({"error": message} if not ok else {})})
        return Response({"ok": True, "results": results})


class HeartbeatView(GatewayView):
    def post(self, request):
        data = request.data if hasattr(request.data, "get") else {}
        device = request.auth

        def number(key, low=0, high=100000):
            value = data.get(key)
            return value if isinstance(value, int) and low <= value <= high else None

        sim = data.get("sim") if isinstance(data.get("sim"), dict) else {}
        updates = {
            "last_seen": timezone.now(),
            "app_version": str(data.get("app_version") or request.headers.get("X-App-Version") or "")[:20],
            "battery_percent": number("battery_percent", 0, 100),
            "charging": data.get("charging") if isinstance(data.get("charging"), bool) else None,
            "network": str(data.get("network") or "")[:10],
            "signal": number("signal", 0, 10),
            "sim_operator": str(sim.get("operator") or "")[:60],
            "sim_slot": sim.get("slot") if isinstance(sim.get("slot"), int) else None,
            "sent_today": number("sent_today", 0, 10 ** 6) or 0,
            "last_heartbeat": {k: v for k, v in data.items() if k in ("android_sdk", "queue", "sim", "network", "signal")},
        }
        Device.objects.filter(pk=device.pk).update(**updates)
        device.refresh_from_db()
        return Response({"server_time": now_iso(), "config": device.config()})
