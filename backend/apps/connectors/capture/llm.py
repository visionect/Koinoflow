"""
LLM provider abstraction for the Capture extraction pipeline.

Supports Gemini (via Vertex AI google-genai) and Claude (via Anthropic Vertex SDK).
The active provider is selected at runtime from Django settings.

When grounded=True, GeminiProvider attaches the GoogleSearch tool so the model
can retrieve up-to-date information from the web. ClaudeVertexProvider silently
ignores grounded=True (no native tool available) and returns empty grounding_sources.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
INITIAL_BACKOFF_SECS = 2.0
MAX_BACKOFF_SECS = 60.0
VERTEX_AUTH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


@dataclass
class LLMResult:
    """Structured result from a single LLM generate() call."""

    text: str
    grounding_sources: list[dict] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        grounded: bool = False,
    ) -> LLMResult:
        """Generate a completion. Raises on unrecoverable errors."""


class GeminiProvider(LLMProvider):
    def __init__(self, model: str, project: str, location: str) -> None:
        self.model = model
        self.project = project
        self.location = location
        self._client = None

    def _get_client(self):
        if self._client is None:
            from django.conf import settings
            from google import genai

            credentials_info = _vertex_service_account_info(settings)
            client_kwargs = {
                "vertexai": True,
                "project": _resolve_vertex_project(settings, self.project),
                "location": self.location,
            }
            if credentials_info is not None:
                from google.oauth2 import service_account

                client_kwargs["credentials"] = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=[VERTEX_AUTH_SCOPE],
                )

            self._client = genai.Client(**client_kwargs)
        return self._client

    def generate(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        grounded: bool = False,
    ) -> LLMResult:
        from google.genai import types
        from google.genai.errors import ClientError

        client = self._get_client()
        config_kwargs: dict = {
            "system_instruction": system,
            "temperature": 0.1,
            "max_output_tokens": max_tokens,
        }
        if grounded:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(**config_kwargs)

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=self.model, contents=user, config=config
                )
                text = _extract_full_text(response)
                finish = getattr(
                    response.candidates[0] if response.candidates else None,
                    "finish_reason",
                    None,
                )
                if finish and str(finish) not in ("STOP", "1", "FinishReason.STOP"):
                    logger.warning(
                        "Gemini response truncated (finish_reason=%s, model=%s): %s",
                        finish,
                        self.model,
                        text[:200],
                    )
                grounding_sources = _extract_grounding_sources(response)
                return LLMResult(text=text, grounding_sources=grounding_sources)
            except ClientError as exc:
                last_exc = exc
                if exc.status_code == 429 and attempt < MAX_RETRIES:
                    backoff = min(
                        INITIAL_BACKOFF_SECS * (2 ** (attempt - 1)),
                        MAX_BACKOFF_SECS,
                    )
                    jitter = random.uniform(0, backoff * 0.5)
                    sleep_secs = backoff + jitter
                    logger.warning(
                        "Gemini 429 rate-limited (model=%s, attempt %d/%d), retrying in %.1fs",
                        self.model,
                        attempt,
                        MAX_RETRIES,
                        sleep_secs,
                    )
                    time.sleep(sleep_secs)
                    continue
                logger.error("Gemini API error (model=%s): %s", self.model, exc)
                raise

        raise last_exc  # type: ignore[misc]


def _extract_full_text(response) -> str:
    """Concatenate all text parts from a Gemini response.

    response.text only returns the first text part, which can miss content
    when the model splits output across multiple parts.
    """
    try:
        parts = response.candidates[0].content.parts or []
        fragments = [p.text for p in parts if getattr(p, "text", None)]
        if fragments:
            return "".join(fragments)
    except (IndexError, AttributeError):
        pass
    return response.text or ""


def _extract_grounding_sources(response) -> list[dict]:
    """Extract web grounding citations from a Gemini response."""
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
        sources = []
        seen_uris: set[str] = set()
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                uri = web.uri
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    sources.append({"uri": uri, "title": getattr(web, "title", "") or ""})
        return sources
    except Exception:
        return []


class ClaudeVertexProvider(LLMProvider):
    def __init__(self, model: str, project: str, location: str) -> None:
        self.model = model
        self.project = project
        self.location = location
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AnthropicVertex(project_id=self.project, region=self.location)
        return self._client

    def generate(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        grounded: bool = False,  # noqa: ARG002 — Claude Vertex has no native search tool
    ) -> LLMResult:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text if response.content else ""
        return LLMResult(text=text, grounding_sources=[])


def get_scoring_model() -> LLMProvider:
    from django.conf import settings

    return _build_provider(settings.CAPTURE_SCORING_MODEL, settings)


def get_extraction_model() -> LLMProvider:
    from django.conf import settings

    return _build_provider(settings.CAPTURE_EXTRACTION_MODEL, settings)


def _vertex_service_account_info(settings) -> dict | None:
    required_fields = {
        "project_id": getattr(settings, "VERTEX_CLIENT_PROJECT_ID", ""),
        "private_key_id": getattr(settings, "VERTEX_CLIENT_PRIVATE_KEY_ID", ""),
        "private_key": getattr(settings, "VERTEX_CLIENT_PRIVATE_KEY", ""),
        "client_email": getattr(settings, "VERTEX_CLIENT_EMAIL", ""),
        "client_id": getattr(settings, "VERTEX_CLIENT_ID", ""),
        "client_x509_cert_url": getattr(settings, "VERTEX_CLIENT_CERT_URL", ""),
    }
    if not all(required_fields.values()):
        return None
    return {
        "type": "service_account",
        **required_fields,
        "private_key": required_fields["private_key"].replace("\\n", "\n"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "universe_domain": "googleapis.com",
    }


def _resolve_vertex_project(settings, fallback: str = "") -> str:
    if _vertex_service_account_info(settings) is not None:
        return getattr(settings, "VERTEX_CLIENT_PROJECT_ID", "")
    return fallback or getattr(settings, "VERTEX_PROJECT_ID", "")


def _build_provider(model_name: str, settings) -> LLMProvider:
    project = _resolve_vertex_project(settings)
    location = getattr(settings, "VERTEX_LOCATION", "global")

    if "claude" in model_name.lower():
        return ClaudeVertexProvider(model=model_name, project=project, location=location)
    return GeminiProvider(model=model_name, project=project, location=location)
