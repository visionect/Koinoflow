"""Tests for the extraction pipeline (Phase 2)."""

from unittest.mock import MagicMock, patch

import pytest

from apps.connectors.capture.extraction import (
    _create_candidate,
    _extract_from_page,
    _parse_json_array,
    _unique_slug,
)
from apps.connectors.capture.llm import LLMResult
from apps.connectors.enums import AutomationTier, CandidateStatus
from apps.connectors.tests.factories import (
    CaptureCandidateFactory,
    ConnectorCredentialFactory,
    SyncedPageFactory,
)


@pytest.mark.django_db
class TestCreateCandidate:
    def test_creates_candidate_with_required_fields(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        data = {
            "title": "Deploy to Production",
            "description": "Production deployment process.",
            "content_md": "## Steps\n\n1. Build\n2. Deploy",
            "frontmatter_yaml": "name: Deploy\ntags:\n  - deploy",
            "automation_tier": "ready",
            "automation_reasoning": "Uses standard CLI tools.",
            "integration_needs": [],
        }
        candidate = _create_candidate(credential, page, data, page_score=0.9)
        assert candidate.title == "Deploy to Production"
        assert candidate.automation_tier == AutomationTier.READY
        assert candidate.probability_score == 0.9
        assert candidate.status == CandidateStatus.PENDING
        assert candidate.sources.filter(synced_page=page).exists()

    def test_persists_grounding_sources(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        sources = [{"uri": "https://docs.github.com", "title": "GitHub Docs"}]
        data = {
            "title": "Use GitHub Actions",
            "description": "CI/CD via GitHub Actions.",
            "content_md": "## Steps\n\n1. Push",
            "frontmatter_yaml": "",
            "automation_tier": "ready",
            "automation_reasoning": "Uses GitHub.",
            "integration_needs": [],
        }
        candidate = _create_candidate(
            credential,
            page,
            data,
            page_score=0.8,
            grounding_sources=sources,
        )
        assert candidate.grounding_sources == sources

    def test_validates_integration_needs_with_new_fields(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        data = {
            "title": "Sync via Salesforce",
            "description": "Sync CRM data.",
            "content_md": "## Steps\n\n1. Query Salesforce",
            "frontmatter_yaml": "",
            "automation_tier": "needs_integration",
            "automation_reasoning": "Requires Salesforce API.",
            "integration_needs": [
                {
                    "system": "Salesforce",
                    "steps_affected": ["1"],
                    "reason": "Needs CRM data",
                    "access_required": "OAuth token",
                    "api_endpoint": "https://api.salesforce.com",
                    "mcp_server": "@smithery-ai/salesforce",
                    "documentation_url": "https://developer.salesforce.com",
                    "auth_method": "OAuth 2.0",
                }
            ],
        }
        candidate = _create_candidate(credential, page, data, page_score=0.75)
        need = candidate.integration_needs[0]
        assert need["api_endpoint"] == "https://api.salesforce.com"
        assert need["mcp_server"] == "@smithery-ai/salesforce"
        assert need["auth_method"] == "OAuth 2.0"

    def test_strips_integration_needs_for_ready_tier(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        data = {
            "title": "Simple git push",
            "description": "Push code.",
            "content_md": "## Steps\n\n1. git push",
            "frontmatter_yaml": "",
            "automation_tier": "ready",
            "automation_reasoning": "Standard git.",
            "integration_needs": [
                {
                    "system": "ignored",
                    "steps_affected": [],
                    "reason": "",
                    "access_required": "",
                }
            ],
        }
        candidate = _create_candidate(credential, page, data, page_score=0.9)
        assert candidate.integration_needs == []

    def test_falls_back_to_manual_only_for_unknown_tier(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        data = {
            "title": "Some process",
            "description": "",
            "content_md": "",
            "frontmatter_yaml": "",
            "automation_tier": "unknown_value",
            "automation_reasoning": "",
            "integration_needs": [],
        }
        candidate = _create_candidate(credential, page, data, page_score=0.5)
        assert candidate.automation_tier == AutomationTier.MANUAL_ONLY

    def test_grounding_sources_defaults_to_empty_list(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        data = {
            "title": "Another process",
            "description": "",
            "content_md": "",
            "frontmatter_yaml": "",
            "automation_tier": "ready",
            "automation_reasoning": "",
            "integration_needs": [],
        }
        candidate = _create_candidate(credential, page, data, page_score=0.6)
        assert candidate.grounding_sources == []


@pytest.mark.django_db
class TestUniqueSlug:
    def test_returns_slugified_title(self):
        credential = ConnectorCredentialFactory()
        slug = _unique_slug(credential, "Deploy to Staging")
        assert slug == "deploy-to-staging"

    def test_appends_counter_on_collision(self):
        credential = ConnectorCredentialFactory()
        CaptureCandidateFactory(credential=credential, slug="deploy-to-staging")
        slug = _unique_slug(credential, "Deploy to Staging")
        assert slug == "deploy-to-staging-1"

    def test_dismissed_candidates_do_not_cause_collision(self):
        credential = ConnectorCredentialFactory()
        CaptureCandidateFactory(
            credential=credential, slug="deploy-to-staging", status=CandidateStatus.DISMISSED
        )
        slug = _unique_slug(credential, "Deploy to Staging")
        assert slug == "deploy-to-staging"


@pytest.mark.django_db
class TestExtractFromPage:
    def _make_mock_model(self, candidates_json: str, sources=None):
        model = MagicMock()
        model.generate.return_value = LLMResult(
            text=candidates_json,
            grounding_sources=sources or [],
        )
        return model

    def test_creates_candidates_from_valid_response(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        json_response = """[
            {
                "title": "Run tests",
                "description": "Execute the test suite.",
                "content_md": "## Steps\\n\\n1. pytest",
                "frontmatter_yaml": "name: Run tests\\ntags: []",
                "automation_tier": "ready",
                "automation_reasoning": "Uses pytest.",
                "integration_needs": []
            }
        ]"""
        model = self._make_mock_model(json_response)

        with (
            patch("apps.connectors.capture.extraction.build_smithery_context", return_value=""),
            patch("apps.connectors.capture.extraction.extract_service_keywords", return_value=[]),
        ):
            created = _extract_from_page(
                model,
                credential,
                page,
                0.85,
                "system prompt",
                "{title}\n{content}\n{smithery_block}",
            )

        assert created == 1

    def test_persists_grounding_sources_on_candidate(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        sources = [{"uri": "https://pytest.org", "title": "pytest"}]
        json_response = """[
            {
                "title": "Run tests",
                "description": "Execute the test suite.",
                "content_md": "## Steps\\n\\n1. pytest",
                "frontmatter_yaml": "",
                "automation_tier": "ready",
                "automation_reasoning": "Uses pytest.",
                "integration_needs": []
            }
        ]"""
        model = self._make_mock_model(json_response, sources=sources)

        with (
            patch("apps.connectors.capture.extraction.build_smithery_context", return_value=""),
            patch("apps.connectors.capture.extraction.extract_service_keywords", return_value=[]),
        ):
            _extract_from_page(
                model,
                credential,
                page,
                0.85,
                "system prompt",
                "{title}\n{content}\n{smithery_block}",
            )

        from apps.connectors.models import CaptureCandidate

        candidate = CaptureCandidate.objects.get(credential=credential)
        assert candidate.grounding_sources == sources

    def test_calls_generate_with_grounded_true(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        model = self._make_mock_model("[]")

        with (
            patch("apps.connectors.capture.extraction.build_smithery_context", return_value=""),
            patch("apps.connectors.capture.extraction.extract_service_keywords", return_value=[]),
        ):
            _extract_from_page(
                model, credential, page, 0.85, "sys", "{title}\n{content}\n{smithery_block}"
            )

        call_kwargs = model.generate.call_args[1]
        assert call_kwargs.get("grounded") is True

    def test_injects_smithery_context_into_prompt(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential, title="GitHub Actions Workflow")
        model = self._make_mock_model("[]")

        smithery_block = "### Available MCP servers\n- **GitHub MCP**"

        with (
            patch(
                "apps.connectors.capture.extraction.build_smithery_context",
                return_value=smithery_block,
            ) as mock_ctx,
            patch(
                "apps.connectors.capture.extraction.extract_service_keywords",
                return_value=["github"],
            ),
        ):
            _extract_from_page(
                model, credential, page, 0.85, "sys", "{title}\n{content}\n{smithery_block}"
            )
            mock_ctx.assert_called_once_with(["github"])

        call_kwargs = model.generate.call_args[1]
        assert smithery_block in call_kwargs["user"]

    def test_returns_zero_on_empty_json_array(self):
        credential = ConnectorCredentialFactory()
        page = SyncedPageFactory(credential=credential)
        model = self._make_mock_model("[]")

        with (
            patch("apps.connectors.capture.extraction.build_smithery_context", return_value=""),
            patch("apps.connectors.capture.extraction.extract_service_keywords", return_value=[]),
        ):
            created = _extract_from_page(
                model, credential, page, 0.5, "sys", "{title}\n{content}\n{smithery_block}"
            )

        assert created == 0


class TestParseJsonArray:
    def test_parses_plain_json(self):
        result = _parse_json_array('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_parses_fenced_json(self):
        result = _parse_json_array('```json\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_returns_empty_list_on_garbage(self):
        result = _parse_json_array("sorry I cannot do that")
        assert result == []

    def test_returns_empty_list_on_bare_object(self):
        result = _parse_json_array('{"not": "an array"}')
        assert result == []
