"""Regression tests for apps.common.admin_ip_gate.AdminIpAllowlistMiddleware.

Covers the fail-closed admin IP gate: when enabled, requests to /admin/*
must be blocked unless the client IP matches ADMIN_IP_ALLOWLIST. Non-admin
paths must pass through untouched regardless of IP.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.test import override_settings

from apps.common.admin_ip_gate import AdminIpAllowlistMiddleware


def _request(path: str, xff: str | None = None, remote_addr: str | None = None):
    request = MagicMock()
    request.path = path
    request.META = {}
    if xff is not None:
        request.META["HTTP_X_FORWARDED_FOR"] = xff
    if remote_addr is not None:
        request.META["REMOTE_ADDR"] = remote_addr
    return request


def _build(**settings_overrides):
    """Instantiate the middleware with the given overridden settings."""
    get_response = MagicMock(return_value="PASSTHROUGH")
    defaults = {
        "ADMIN_IP_ALLOWLIST": "",
        "ADMIN_IP_GATE_ENABLED": True,
        "ADMIN_BYPASS_IP_GATE": False,
        "DEBUG": False,
    }
    defaults.update(settings_overrides)
    with override_settings(**defaults):
        mw = AdminIpAllowlistMiddleware(get_response)
    return mw, get_response


def test_non_admin_path_is_never_blocked():
    mw, get_response = _build(ADMIN_IP_ALLOWLIST="")
    resp = mw(_request("/api/v1/processes/", xff="1.2.3.4"))
    assert resp == "PASSTHROUGH"
    get_response.assert_called_once()


def test_admin_path_fails_closed_when_allowlist_empty():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="")
    resp = mw(_request("/admin/", xff="1.2.3.4"))
    assert resp.status_code == 403


def test_admin_path_blocked_when_ip_not_in_allowlist():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="10.0.0.0/8")
    resp = mw(_request("/admin/", xff="1.2.3.4"))
    assert resp.status_code == 403


def test_admin_path_allowed_when_ip_in_cidr():
    mw, get_response = _build(ADMIN_IP_ALLOWLIST="10.0.0.0/8, 192.168.1.42/32")
    resp = mw(_request("/admin/login/", xff="10.5.6.7"))
    assert resp == "PASSTHROUGH"
    get_response.assert_called_once()


def test_admin_path_allowed_for_single_ip_entry():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="192.168.1.42")
    resp = mw(_request("/admin/", xff="192.168.1.42"))
    assert resp == "PASSTHROUGH"


def test_xff_leftmost_ip_is_used_not_lb_hop():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="1.2.3.4/32")
    # GCP LB appends its own hop; the real client is always leftmost.
    resp = mw(_request("/admin/", xff="1.2.3.4, 130.211.0.1, 35.191.0.2"))
    assert resp == "PASSTHROUGH"


def test_spoofed_trailing_xff_entry_does_not_bypass_gate():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="1.2.3.4/32")
    # Attacker tries to append their own IP to XFF; leftmost is the real one.
    resp = mw(_request("/admin/", xff="9.9.9.9, 1.2.3.4"))
    assert resp.status_code == 403


def test_malformed_ip_is_denied():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="1.2.3.4/32")
    resp = mw(_request("/admin/", xff="not-an-ip"))
    assert resp.status_code == 403


def test_malformed_cidr_in_allowlist_is_ignored_safely():
    # Bogus entry must not crash startup and must not implicitly allow anything.
    mw, _ = _build(ADMIN_IP_ALLOWLIST="not-a-cidr, 1.2.3.4/32")
    resp_allowed = mw(_request("/admin/", xff="1.2.3.4"))
    resp_denied = mw(_request("/admin/", xff="5.6.7.8"))
    assert resp_allowed == "PASSTHROUGH"
    assert resp_denied.status_code == 403


def test_bypass_flag_disables_gate():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="", ADMIN_BYPASS_IP_GATE=True)
    resp = mw(_request("/admin/", xff="1.2.3.4"))
    assert resp == "PASSTHROUGH"


def test_explicitly_disabled_gate_passes_everything_through():
    mw, _ = _build(
        ADMIN_IP_ALLOWLIST="",
        ADMIN_IP_GATE_ENABLED=False,
    )
    resp = mw(_request("/admin/", xff="1.2.3.4"))
    assert resp == "PASSTHROUGH"


def test_static_admin_path_is_also_gated():
    mw, _ = _build(ADMIN_IP_ALLOWLIST="1.2.3.4/32")
    # /static/admin/ still leaks admin UI assets; gate covers it too.
    resp = mw(_request("/static/admin/css/base.css", xff="9.9.9.9"))
    assert resp.status_code == 403


@pytest.mark.parametrize("path", ["/", "/healthz", "/api/", "/static/img/logo.png"])
def test_public_paths_are_never_gated(path):
    mw, _ = _build(ADMIN_IP_ALLOWLIST="1.2.3.4/32")
    resp = mw(_request(path, xff="5.5.5.5"))
    assert resp == "PASSTHROUGH"
