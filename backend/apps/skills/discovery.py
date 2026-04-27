import hashlib
import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.orgs.enums import EntityType
from apps.orgs.models import CoreSlug
from apps.skills.enums import StatusChoices
from apps.skills.models import SkillDiscoveryEmbedding, SkillVersion

logger = logging.getLogger(__name__)

MAX_INDEXED_TEXT_CHARS = 20_000
SUPPORTED_EMBEDDING_DIMENSIONS = 768


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    dimensions: int


def get_embedding_config() -> EmbeddingConfig:
    dimensions = int(getattr(settings, "SKILL_DISCOVERY_EMBEDDING_DIMENSIONS", 768))
    if dimensions != SUPPORTED_EMBEDDING_DIMENSIONS:
        raise ValueError(
            "SKILL_DISCOVERY_EMBEDDING_DIMENSIONS must be 768 until the vector "
            "column dimension is migrated."
        )
    return EmbeddingConfig(
        model=getattr(settings, "SKILL_DISCOVERY_EMBEDDING_MODEL", "gemini-embedding-2"),
        dimensions=dimensions,
    )


def normalize_metadata(raw) -> dict:
    result = {
        "retrieval_keywords": [],
        "risk_level": None,
        "requires_human_approval": False,
        "prerequisites": [],
        "audience": [],
    }
    if not isinstance(raw, dict):
        return result
    for key in ("retrieval_keywords", "prerequisites", "audience"):
        values = raw.get(key)
        if isinstance(values, list):
            result[key] = [str(v) for v in values if isinstance(v, str) and v]
    risk = raw.get("risk_level")
    if risk in ("low", "medium", "high", "critical"):
        result["risk_level"] = risk
    approval = raw.get("requires_human_approval")
    if isinstance(approval, bool):
        result["requires_human_approval"] = approval
    return result


def _get_slug(entity_type: str, entity_id) -> str:
    return (
        CoreSlug.objects.filter(entity_type=entity_type, entity_id=entity_id)
        .values_list("slug", flat=True)
        .first()
        or ""
    )


def build_skill_indexed_text(version: SkillVersion) -> str:
    skill = version.skill
    department = skill.department
    team = department.team
    metadata = normalize_metadata(version.koinoflow_metadata)
    team_slug = _get_slug(EntityType.TEAM, team.id)
    department_slug = _get_slug(EntityType.DEPARTMENT, department.id)
    parts = [
        f"Title: {skill.title}",
        f"Slug: {skill.slug}",
        f"Description: {skill.description}",
        f"Team: {team.name} ({team_slug})",
        f"Department: {department.name} ({department_slug})",
        f"Retrieval keywords: {', '.join(metadata['retrieval_keywords'])}",
        f"Audience: {', '.join(metadata['audience'])}",
        f"Prerequisites: {', '.join(metadata['prerequisites'])}",
        f"Risk level: {metadata['risk_level'] or ''}",
        f"Requires human approval: {metadata['requires_human_approval']}",
        "",
        version.frontmatter_yaml,
        version.content_md,
    ]
    text = "\n".join(part for part in parts if part is not None).strip()
    return text[:MAX_INDEXED_TEXT_CHARS]


def discovery_content_hash(indexed_text: str, config: EmbeddingConfig) -> str:
    payload = {
        "model": config.model,
        "dimensions": config.dimensions,
        "text": indexed_text,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class VertexEmbeddingClient:
    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or get_embedding_config()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from apps.connectors.capture.llm import GeminiProvider, _resolve_vertex_project

            # Reuse Capture's Vertex client setup so service-account handling
            # stays centralized across generation and discovery embeddings.
            self._client = GeminiProvider(
                model=self.config.model,
                project=_resolve_vertex_project(settings, settings.VERTEX_PROJECT_ID),
                location=settings.VERTEX_LOCATION,
            )._get_client()
        return self._client

    def embed_document(self, text: str) -> list[float]:
        prompt = f"Represent this Koinoflow skill for retrieval by a user's task.\n\n{text}"
        return self._embed(prompt)

    def embed_query(self, query: str) -> list[float]:
        prompt = (
            "Represent this user task for retrieving the most relevant Koinoflow "
            f"skill.\n\nTask: {query}"
        )
        return self._embed(prompt)

    def _embed(self, text: str) -> list[float]:
        from google.genai import types

        response = self._get_client().models.embed_content(
            model=self.config.model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.config.dimensions),
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise ValueError("Vertex embedding response did not include embeddings")
        first = embeddings[0]
        values = getattr(first, "values", None)
        if values is None and isinstance(first, dict):
            values = first.get("values")
        if values is None:
            values = first
        vector = [float(v) for v in values]
        if len(vector) != self.config.dimensions:
            raise ValueError(
                f"Expected {self.config.dimensions} embedding dimensions, got {len(vector)}"
            )
        return vector


def index_skill_version(version_id: str, *, force: bool = False) -> SkillDiscoveryEmbedding | None:
    version = (
        SkillVersion.objects.select_related("skill__department__team").filter(id=version_id).first()
    )
    if version is None:
        return None

    skill = version.skill
    if skill.status != StatusChoices.PUBLISHED or skill.current_version_id != version.id:
        SkillDiscoveryEmbedding.objects.filter(version=version).delete()
        return None

    config = get_embedding_config()
    indexed_text = build_skill_indexed_text(version)
    content_hash = discovery_content_hash(indexed_text, config)
    existing = getattr(version, "discovery_embedding", None)
    if (
        existing
        and not force
        and existing.content_hash == content_hash
        and existing.embedding_model == config.model
        and existing.embedding_dimensions == config.dimensions
    ):
        return existing

    vector = VertexEmbeddingClient(config).embed_document(indexed_text)
    embedding, _ = SkillDiscoveryEmbedding.objects.update_or_create(
        version=version,
        defaults={
            "embedding": vector,
            "embedding_model": config.model,
            "embedding_dimensions": config.dimensions,
            "content_hash": content_hash,
            "indexed_text": indexed_text,
            "indexed_at": timezone.now(),
        },
    )
    return embedding


def queue_skill_discovery_embedding(version_id: str, *, force: bool = False) -> None:
    try:
        from tasks import task_backend

        task_backend.enqueue(
            "index_skill_discovery_embedding",
            version_id=str(version_id),
            force=force,
        )
    except Exception:
        logger.warning("Failed to queue skill discovery embedding", exc_info=True)
