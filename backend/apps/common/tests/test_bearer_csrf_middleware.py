"""Regression tests for apps.common.middleware.BearerTokenCSRFExemptMiddleware.

Covers the CSRF + session-riding fix: when an Authorization: Bearer / Api-Key
header is set, the middleware must (a) strip cookie-based auth (sessionid,
csrftoken, kf_admin_sessionid) before SessionMiddleware ever sees them and
(b) mark the request as CSRF-exempt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.common.middleware import BearerTokenCSRFExemptMiddleware


def _make_request(auth: str | None, cookies: dict[str, str] | None = None):
    """Minimal stand-in for a Django HttpRequest."""
    request = MagicMock()
    request.META = {}
    if auth is not None:
        request.META["HTTP_AUTHORIZATION"] = auth
    request.COOKIES = dict(cookies or {})
    request._dont_enforce_csrf_checks = False
    return request


@pytest.mark.parametrize(
    "auth",
    [
        "Bearer kf_abc123",
        "Api-Key foo",
    ],
)
def test_bearer_auth_strips_session_cookies(auth):
    response_sentinel = object()
    get_response = MagicMock(return_value=response_sentinel)
    middleware = BearerTokenCSRFExemptMiddleware(get_response)

    request = _make_request(
        auth,
        cookies={
            "sessionid": "victim-session",
            "csrftoken": "victim-csrf",
            "kf_admin_sessionid": "victim-admin-session",
            "other_cookie": "keep-me",
        },
    )

    result = middleware(request)

    assert result is response_sentinel
    assert "sessionid" not in request.COOKIES
    assert "csrftoken" not in request.COOKIES
    assert "kf_admin_sessionid" not in request.COOKIES
    assert request.COOKIES.get("other_cookie") == "keep-me"
    assert request._dont_enforce_csrf_checks is True


def test_bearer_auth_sets_csrf_exempt_flag_even_without_cookies():
    get_response = MagicMock(return_value=MagicMock())
    middleware = BearerTokenCSRFExemptMiddleware(get_response)

    request = _make_request("Bearer kf_xyz", cookies={})

    middleware(request)
    assert request._dont_enforce_csrf_checks is True


def test_session_only_request_is_untouched():
    get_response = MagicMock(return_value=MagicMock())
    middleware = BearerTokenCSRFExemptMiddleware(get_response)

    request = _make_request(
        auth=None,
        cookies={"sessionid": "real-session", "csrftoken": "real-csrf"},
    )

    middleware(request)
    # No Authorization header => cookies must be preserved and CSRF enforced.
    assert request.COOKIES.get("sessionid") == "real-session"
    assert request.COOKIES.get("csrftoken") == "real-csrf"
    assert request._dont_enforce_csrf_checks is False


def test_malformed_authorization_header_is_ignored():
    get_response = MagicMock(return_value=MagicMock())
    middleware = BearerTokenCSRFExemptMiddleware(get_response)

    request = _make_request(
        auth="Basic dXNlcjpwYXNz",
        cookies={"sessionid": "keep"},
    )

    middleware(request)
    assert request.COOKIES.get("sessionid") == "keep"
    assert request._dont_enforce_csrf_checks is False
