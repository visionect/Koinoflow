"""IP allowlist middleware for /admin/.

Cost-neutral replacement for Cloud Armor. Denies every request to /admin/*
whose client IP is not in ``ADMIN_IP_ALLOWLIST`` (comma-separated CIDR blocks
from env). Empty allowlist => admin is unreachable (fail-closed). Use the
escape hatch ``ADMIN_BYPASS_IP_GATE=1`` only for one-off local debugging.

Client IP is taken from the left-most entry of ``X-Forwarded-For`` because
the Google HTTPS LB prepends the real client IP there. Per GCP docs the
left-most entry is the original client IP when the request arrives from the
internet; LB hops come after.
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)

ADMIN_PREFIXES = ("/admin/", "/static/admin/")


def _parse_networks(raw: str) -> list[ipaddress._BaseNetwork]:
    nets: list[ipaddress._BaseNetwork] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            logger.warning("Ignoring malformed ADMIN_IP_ALLOWLIST entry: %s", chunk)
    return nets


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


class AdminIpAllowlistMiddleware:
    """Block non-allowlisted IPs from reaching /admin/."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._networks = _parse_networks(getattr(settings, "ADMIN_IP_ALLOWLIST", ""))
        self._bypass = bool(getattr(settings, "ADMIN_BYPASS_IP_GATE", False))
        self._enabled = getattr(settings, "ADMIN_IP_GATE_ENABLED", not settings.DEBUG)

    def __call__(self, request):
        if not self._enabled or self._bypass:
            return self.get_response(request)

        path = request.path or ""
        if not any(path.startswith(p) for p in ADMIN_PREFIXES):
            return self.get_response(request)

        ip = _client_ip(request)
        if not ip:
            logger.warning("admin_ip_gate: no client ip; denying %s", path)
            return HttpResponseForbidden("Forbidden")

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            logger.warning("admin_ip_gate: malformed client ip %r", ip)
            return HttpResponseForbidden("Forbidden")

        for net in self._networks:
            if addr in net:
                return self.get_response(request)

        logger.warning("admin_ip_gate: deny ip=%s path=%s", ip, path)
        return HttpResponseForbidden("Forbidden")
