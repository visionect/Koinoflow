"""Tests for the Smithery MCP registry client."""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.connectors.capture.registry import (
    build_smithery_context,
    extract_service_keywords,
    search_mcp_servers,
)

_TEST_QUERIES = ["github", "gitlab", "unknown-tool-xyz"]


@pytest.fixture(autouse=True)
def clear_registry_cache():
    """Wipe known Smithery cache entries between tests."""
    for q in _TEST_QUERIES:
        cache.delete(f"smithery:q:{q}")
    yield
    for q in _TEST_QUERIES:
        cache.delete(f"smithery:q:{q}")


class TestExtractServiceKeywords:
    def test_detects_known_services(self):
        keywords = extract_service_keywords(
            "Deploy to AWS with Kubernetes",
            "We use GitHub for source control and Slack for notifications.",
        )
        assert "aws" in keywords
        assert "kubernetes" in keywords
        assert "github" in keywords
        assert "slack" in keywords

    def test_case_insensitive(self):
        keywords = extract_service_keywords("JIRA Ticket Process", "Use JIRA to track work.")
        assert "jira" in keywords

    def test_returns_empty_for_no_matches(self):
        keywords = extract_service_keywords("Meeting notes", "We had a great meeting today.")
        assert keywords == []

    def test_does_not_duplicate(self):
        keywords = extract_service_keywords("github flow", "github github github")
        assert keywords.count("github") == 1


def _mock_httpx_response(json_data, status_code=200):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    if status_code >= 400:
        from httpx import HTTPStatusError

        mock_resp.raise_for_status.side_effect = HTTPStatusError(
            message="Error",
            request=MagicMock(),
            response=MagicMock(),
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


class TestSearchMcpServers:
    def _patch_client(self, mock_response):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        return mock_client

    def test_returns_servers_on_success(self):
        payload = {
            "servers": [
                {
                    "qualifiedName": "@smithery-ai/github",
                    "displayName": "GitHub MCP",
                    "description": "Manage GitHub repos",
                    "homepage": "https://smithery.ai/server/github",
                }
            ]
        }
        mock_resp = _mock_httpx_response(payload)
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            result = search_mcp_servers("github")

        assert len(result) == 1
        assert result[0]["qualifiedName"] == "@smithery-ai/github"

    def test_returns_empty_list_on_network_error(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = ConnectionError("Network unreachable")

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            result = search_mcp_servers("github")

        assert result == []

    def test_returns_empty_list_on_http_error(self):
        mock_resp = _mock_httpx_response({}, status_code=401)
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            result = search_mcp_servers("github", api_key="bad-key")

        assert result == []

    def test_sends_bearer_token_when_api_key_provided(self):
        mock_resp = _mock_httpx_response({"servers": []})
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            search_mcp_servers("github", api_key="sk-test-123")

        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-123"

    def test_omits_auth_header_without_api_key(self):
        mock_resp = _mock_httpx_response({"servers": []})
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            search_mcp_servers("github", api_key="")

        call_kwargs = mock_client.get.call_args[1]
        assert "Authorization" not in call_kwargs["headers"]

    # ── Caching behaviour ────────────────────────────────────────────────

    def test_cache_miss_fetches_from_registry(self, settings):
        settings.SMITHERY_CACHE_TTL_SECONDS = 3600
        payload = {"servers": [{"qualifiedName": "@x/github", "displayName": "GH"}]}
        mock_resp = _mock_httpx_response(payload)
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            result = search_mcp_servers("github")

        assert mock_client.get.call_count == 1
        assert result[0]["qualifiedName"] == "@x/github"

    def test_cache_hit_skips_http_request(self, settings):
        settings.SMITHERY_CACHE_TTL_SECONDS = 3600
        cached_servers = [{"qualifiedName": "@x/github", "displayName": "GH"}]
        cache.set("smithery:q:github", cached_servers, timeout=3600)

        mock_client = MagicMock()
        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            result = search_mcp_servers("github")

        mock_client.assert_not_called()
        assert result == cached_servers

    def test_successful_result_is_written_to_cache(self, settings):
        settings.SMITHERY_CACHE_TTL_SECONDS = 3600
        payload = {"servers": [{"qualifiedName": "@x/github", "displayName": "GH"}]}
        mock_resp = _mock_httpx_response(payload)
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            search_mcp_servers("github")

        assert cache.get("smithery:q:github") == payload["servers"]

    def test_error_result_is_not_cached(self, settings):
        settings.SMITHERY_CACHE_TTL_SECONDS = 3600
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = ConnectionError("unreachable")

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            search_mcp_servers("github")

        assert cache.get("smithery:q:github") is None

    def test_second_call_uses_cache_not_http(self, settings):
        settings.SMITHERY_CACHE_TTL_SECONDS = 3600
        payload = {"servers": [{"qualifiedName": "@x/github", "displayName": "GH"}]}
        mock_resp = _mock_httpx_response(payload)
        mock_client = self._patch_client(mock_resp)

        with patch("apps.connectors.capture.registry.httpx.Client", return_value=mock_client):
            search_mcp_servers("github")
            search_mcp_servers("github")

        assert mock_client.get.call_count == 1  # only one real HTTP call


class TestBuildSmitheryContext:
    def _patch_search(self, return_value):
        return patch(
            "apps.connectors.capture.registry.search_mcp_servers",
            return_value=return_value,
        )

    def test_returns_empty_string_for_no_keywords(self, settings):
        settings.SMITHERY_API_KEY = ""
        result = build_smithery_context([])
        assert result == ""

    def test_returns_markdown_block_when_results_found(self, settings):
        settings.SMITHERY_API_KEY = ""
        servers = [
            {
                "qualifiedName": "@smithery-ai/github",
                "displayName": "GitHub MCP",
                "description": "Manage repos",
                "homepage": "https://smithery.ai",
            }
        ]
        with self._patch_search(servers):
            result = build_smithery_context(["github"])

        assert "GitHub MCP" in result
        assert "@smithery-ai/github" in result
        assert "### Available MCP servers" in result

    def test_deduplicates_servers_across_keywords(self, settings):
        settings.SMITHERY_API_KEY = ""
        server = {
            "qualifiedName": "@smithery-ai/github",
            "displayName": "GitHub MCP",
            "description": "",
            "homepage": "",
        }
        with self._patch_search([server]):
            result = build_smithery_context(["github", "gitlab"])

        assert result.count("@smithery-ai/github") == 1

    def test_returns_empty_string_when_no_servers_found(self, settings):
        settings.SMITHERY_API_KEY = ""
        with self._patch_search([]):
            result = build_smithery_context(["unknown-tool-xyz"])

        assert result == ""
