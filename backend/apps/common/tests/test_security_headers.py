"""Regression tests for SecurityHeadersMiddleware.

Asserts that every Django-rendered response carries the hardening headers
and that middleware-set headers don't clobber upstream values.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from apps.common.security_headers import SecurityHeadersMiddleware


class _Response(dict):
    """Minimal mapping that behaves like HttpResponse[headers]."""

    def __setitem__(self, k, v):
        super().__setitem__(k, v)

    def __contains__(self, k):
        return super().__contains__(k)


def _run(path: str = "/admin/", preset: dict | None = None):
    get_response = MagicMock(return_value=_Response(preset or {}))
    middleware = SecurityHeadersMiddleware(get_response)
    request = MagicMock()
    request.path = path
    return middleware(request)


def test_default_headers_are_attached():
    response = _run(path="/admin/")
    assert "Content-Security-Policy" in response
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert "Permissions-Policy" in response
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_admin_path_is_marked_noindex():
    response = _run(path="/admin/login/")
    assert response["X-Robots-Tag"] == "noindex, nofollow"


def test_non_admin_path_is_not_marked_noindex():
    response = _run(path="/api/v1/processes/")
    assert "X-Robots-Tag" not in response


def test_upstream_csp_is_not_overridden():
    preset = {"Content-Security-Policy": "default-src 'none'"}
    response = _run(preset=preset)
    assert response["Content-Security-Policy"] == "default-src 'none'"


def test_upstream_referrer_policy_is_not_overridden():
    preset = {"Referrer-Policy": "no-referrer"}
    response = _run(preset=preset)
    assert response["Referrer-Policy"] == "no-referrer"
