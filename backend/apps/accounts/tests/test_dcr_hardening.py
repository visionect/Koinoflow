"""Regression tests for Dynamic Client Registration hardening.

- Redirect-URI validation: https-only for non-loopback, no fragments,
  no arbitrary schemes.
- Rate limiting keyed on left-most X-Forwarded-For so a single attacker
  behind the LB cannot burn the shared REMOTE_ADDR bucket.
- Client-name sanitisation: known first-party client names are tagged
  as "(unverified)" so a malicious registration cannot visually spoof
  Claude / Cursor on the consent screen.
"""

from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.oauth_views import (
    _sanitise_client_name,
    _validate_redirect_uri,
)


class TestValidateRedirectUri:
    @pytest.mark.parametrize(
        "uri",
        [
            "https://mcp.example.com/callback",
            "https://cursor.sh/cb",
            "cursor://oauth/callback",
            "vscode://vscode.vscode-mcp/callback",
            "http://127.0.0.1:51820/callback",
            "http://localhost:51820/callback",
            "http://[::1]/cb",
        ],
    )
    def test_accepts_valid_uris(self, uri):
        assert _validate_redirect_uri(uri) is None, uri

    @pytest.mark.parametrize(
        "uri,reason_substring",
        [
            ("", "non-empty"),
            ("http://example.com/cb", "loopback"),
            ("http://attacker.internal/cb", "loopback"),
            ("javascript:alert(1)", "not allowed"),
            ("data:text/html,<script>alert(1)</script>", "not allowed"),
            ("ftp://example.com/cb", "not allowed"),
            ("https://mcp.example.com/cb#fragment", "fragment"),
            ("https:///missing-host", "must include a host"),
        ],
    )
    def test_rejects_invalid_uris(self, uri, reason_substring):
        reason = _validate_redirect_uri(uri)
        assert reason is not None, uri
        assert reason_substring in reason, (reason_substring, reason)

    def test_rejects_non_string(self):
        assert _validate_redirect_uri(None) is not None
        assert _validate_redirect_uri(123) is not None

    def test_rejects_overly_long_uri(self):
        assert _validate_redirect_uri("https://e.com/" + "a" * 3000) is not None


class TestSanitiseClientName:
    def test_default_when_empty(self):
        assert _sanitise_client_name("") == "MCP Client"
        assert _sanitise_client_name(None) == "MCP Client"
        assert _sanitise_client_name("   ") == "MCP Client"

    def test_truncates_to_120_chars(self):
        out = _sanitise_client_name("x" * 500)
        assert len(out) == 120

    @pytest.mark.parametrize(
        "name",
        ["Claude Desktop", "CURSOR", "Cursor", "Claude", "MCP Inspector", "Koinoflow"],
    )
    def test_protected_first_party_names_are_tagged_unverified(self, name):
        assert "(unverified)" in _sanitise_client_name(name)

    def test_non_protected_name_passes_through(self):
        assert _sanitise_client_name("My Internal MCP Tool") == "My Internal MCP Tool"


@pytest.mark.django_db
class TestOAuthMetadataScopes:
    def test_authorization_server_metadata_advertises_mcp_skill_scopes(self):
        resp = Client().get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200

        data = resp.json()
        assert data["scopes_supported"] == ["skills:read", "skills:write", "usage:write"]

    def test_dynamic_registration_defaults_to_mcp_skill_scopes(self):
        resp = Client().post(
            "/oauth/register",
            data=json.dumps(
                {
                    "client_name": "test-client",
                    "redirect_uris": ["https://mcp.example.com/cb"],
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201

        data = resp.json()
        assert data["scope"] == "skills:read skills:write usage:write"


@pytest.mark.django_db
class TestDCRRateLimit:
    def setup_method(self):
        cache.clear()

    def _post(self, client: Client, ip: str):
        return client.post(
            "/oauth/register",
            data=json.dumps(
                {
                    "client_name": "test-client",
                    "redirect_uris": ["https://mcp.example.com/cb"],
                }
            ),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR=ip,
        )

    def test_per_ip_rate_limit_fires_at_11th_request(self):
        client = Client()
        for i in range(10):
            resp = self._post(client, "1.2.3.4")
            assert resp.status_code in (200, 201), (i, resp.status_code, resp.content)
        resp = self._post(client, "1.2.3.4")
        assert resp.status_code == 429

    def test_second_ip_is_not_rate_limited_by_first(self):
        client = Client()
        # Exhaust IP A.
        for _ in range(10):
            self._post(client, "1.2.3.4")
        assert self._post(client, "1.2.3.4").status_code == 429
        # IP B should still be allowed.
        resp = self._post(client, "5.6.7.8")
        assert resp.status_code in (200, 201)

    def test_rate_limit_uses_leftmost_xff(self):
        """Behind GCP LB the XFF is 'real-client, lb-ip, …'; the limiter must
        key on the real client, not on the LB IP that would make every
        request share a bucket."""
        client = Client()
        # 10 distinct real clients all going through the same LB IP trailing.
        for i in range(10):
            resp = self._post(client, f"10.{i}.0.1, 130.211.0.1, 35.191.0.2")
            assert resp.status_code in (200, 201), (i, resp.status_code)
