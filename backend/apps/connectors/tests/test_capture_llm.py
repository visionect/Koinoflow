"""Tests for the LLM provider abstraction (LLMResult, grounding)."""

from unittest.mock import MagicMock, patch

from apps.connectors.capture.llm import (
    ClaudeVertexProvider,
    GeminiProvider,
    LLMResult,
    _build_provider,
    _extract_grounding_sources,
)


class TestLLMResult:
    def test_defaults(self):
        result = LLMResult(text="hello")
        assert result.text == "hello"
        assert result.grounding_sources == []

    def test_with_sources(self):
        sources = [{"uri": "https://example.com", "title": "Example"}]
        result = LLMResult(text="hello", grounding_sources=sources)
        assert result.grounding_sources == sources


class TestExtractGroundingSources:
    def _make_response(self, chunks):
        chunk_objs = []
        for uri, title in chunks:
            web = MagicMock()
            web.uri = uri
            web.title = title
            chunk = MagicMock()
            chunk.web = web
            chunk_objs.append(chunk)

        meta = MagicMock()
        meta.grounding_chunks = chunk_objs
        candidate = MagicMock()
        candidate.grounding_metadata = meta
        response = MagicMock()
        response.candidates = [candidate]
        return response

    def test_extracts_uri_and_title(self):
        response = self._make_response([("https://docs.github.com", "GitHub Docs")])
        sources = _extract_grounding_sources(response)
        assert len(sources) == 1
        assert sources[0]["uri"] == "https://docs.github.com"
        assert sources[0]["title"] == "GitHub Docs"

    def test_deduplicates_by_uri(self):
        response = self._make_response(
            [
                ("https://docs.github.com", "GitHub Docs"),
                ("https://docs.github.com", "GitHub Docs again"),
            ]
        )
        sources = _extract_grounding_sources(response)
        assert len(sources) == 1

    def test_returns_empty_on_missing_metadata(self):
        response = MagicMock()
        response.candidates = []
        sources = _extract_grounding_sources(response)
        assert sources == []

    def test_returns_empty_on_exception(self):
        sources = _extract_grounding_sources(None)
        assert sources == []


class TestGeminiProvider:
    def _make_provider(self):
        return GeminiProvider(model="gemini-test", project="test-project", location="us-central1")

    def test_returns_llm_result(self):
        provider = self._make_provider()

        mock_response = MagicMock()
        mock_response.text = "some output"
        mock_response.candidates = []

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        provider._client = mock_client

        result = provider.generate(system="sys", user="user msg")
        assert isinstance(result, LLMResult)
        assert result.text == "some output"

    def test_grounded_call_injects_google_search_tool(self):
        provider = self._make_provider()

        mock_response = MagicMock()
        mock_response.text = "grounded output"
        mock_response.candidates = []

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        provider._client = mock_client

        with patch("google.genai.types") as mock_types:
            mock_tool = MagicMock()
            mock_types.Tool.return_value = mock_tool
            mock_types.GoogleSearch.return_value = MagicMock()
            mock_types.GenerateContentConfig.return_value = MagicMock()
            provider.generate(system="sys", user="msg", grounded=True)

        # The config was built with tools — verify GenerateContentConfig was called with tools
        mock_types.GenerateContentConfig.assert_called_once()
        _, cfg_kwargs = mock_types.GenerateContentConfig.call_args
        assert "tools" in cfg_kwargs

    def test_returns_empty_string_on_none_text(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = None
        mock_response.candidates = []
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        provider._client = mock_client

        result = provider.generate(system="sys", user="msg")
        assert result.text == ""


class TestClaudeVertexProvider:
    def _make_provider(self):
        return ClaudeVertexProvider(
            model="claude-test", project="test-project", location="us-east5"
        )

    def test_returns_llm_result(self):
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = "claude output"
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        provider._client = mock_client

        result = provider.generate(system="sys", user="user msg")
        assert isinstance(result, LLMResult)
        assert result.text == "claude output"
        assert result.grounding_sources == []

    def test_ignores_grounded_param(self):
        """grounded=True should not raise, just returns empty grounding_sources."""
        provider = self._make_provider()

        mock_content = MagicMock()
        mock_content.text = "output"
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        provider._client = mock_client

        result = provider.generate(system="sys", user="msg", grounded=True)
        assert result.grounding_sources == []

    def test_returns_empty_string_when_no_content(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.content = []
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        provider._client = mock_client

        result = provider.generate(system="sys", user="msg")
        assert result.text == ""


class TestBuildProvider:
    def test_claude_model_returns_claude_provider(self, settings):
        settings.VERTEX_PROJECT_ID = "my-project"
        settings.VERTEX_LOCATION = "us-east5"
        provider = _build_provider("claude-sonnet-4-6", settings)
        assert isinstance(provider, ClaudeVertexProvider)

    def test_gemini_model_returns_gemini_provider(self, settings):
        settings.VERTEX_PROJECT_ID = "my-project"
        settings.VERTEX_LOCATION = "global"
        provider = _build_provider("gemini-3-flash-preview", settings)
        assert isinstance(provider, GeminiProvider)
