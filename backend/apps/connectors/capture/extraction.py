"""
Phase 2 — Process extraction.

For each page that passed the scoring threshold, the flagship LLM extracts
one or more CaptureCandidate records with full SKILL.md content and
automation classification.

Pages are processed sequentially (unlike scoring) because each page may
produce multiple candidates and we want to keep DB writes atomic per page.

When Google Search grounding is available (GeminiProvider), the LLM can
verify integration details in real time; grounding citations are persisted
on the candidate for traceability.
"""

import json
import logging
import re
import time
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from apps.connectors.capture.registry import build_smithery_context, extract_service_keywords
from apps.connectors.capture.scoring import PageScore
from apps.connectors.enums import AutomationTier, CandidateStatus
from apps.connectors.models import CandidateSource, CaptureCandidate, ConnectorCredential

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 16_000


def extract_candidates(
    credential: ConnectorCredential,
    scored_pages: list[PageScore],
) -> int:
    """
    Run extraction on all scored pages. Returns total candidates created.

    Failures on individual pages are logged and skipped so a single bad page
    cannot abort the entire job.
    """
    from apps.connectors.capture.llm import get_extraction_model
    from apps.connectors.capture.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE

    model = get_extraction_model()
    total_created = 0

    for idx, page_score in enumerate(scored_pages):
        page = page_score.page
        try:
            created = _extract_from_page(
                model,
                credential,
                page,
                page_score.score,
                EXTRACTION_SYSTEM_PROMPT,
                EXTRACTION_USER_TEMPLATE,
            )
            total_created += created
            page.extraction_checksum = page.checksum
            page.save(update_fields=["extraction_checksum", "updated_at"])
            logger.debug("Extracted %d candidates from page %s", created, page.id)
        except Exception:
            logger.error(
                "Extraction failed for page %s (%s, credential=%s)",
                page.id,
                page.title,
                credential.id,
                exc_info=True,
            )

        if idx < len(scored_pages) - 1:
            time.sleep(1.0)

    return total_created


def _extract_from_page(
    model,
    credential: ConnectorCredential,
    page,
    page_score: float,
    system_prompt: str,
    user_template: str,
) -> int:
    content = page.content_md[:MAX_CONTENT_CHARS]

    keywords = extract_service_keywords(page.title, content)
    smithery_block = build_smithery_context(keywords)

    user_msg = user_template.format(
        title=page.title,
        content=content,
        smithery_block=smithery_block,
    )

    llm_result = model.generate(
        system=system_prompt,
        user=user_msg,
        max_tokens=8192,
        grounded=True,
    )
    candidates_data = _parse_json_array(llm_result.text)

    created = 0
    for item in candidates_data:
        if not isinstance(item, dict):
            continue
        try:
            _create_candidate(
                credential,
                page,
                item,
                page_score,
                grounding_sources=llm_result.grounding_sources,
            )
            created += 1
        except Exception:
            logger.warning(
                "Failed to persist candidate '%s' from page %s",
                item.get("title", "?"),
                page.id,
                exc_info=True,
            )

    return created


def _create_candidate(
    credential: ConnectorCredential,
    source_page,
    data: dict[str, Any],
    page_score: float,
    grounding_sources: list[dict] | None = None,
) -> CaptureCandidate:
    title = str(data.get("title", "Untitled Process"))[:500]
    slug = _unique_slug(credential, title)

    tier_raw = str(data.get("automation_tier", "manual_only")).lower()
    try:
        tier = AutomationTier(tier_raw)
    except ValueError:
        tier = AutomationTier.MANUAL_ONLY

    integration_needs = data.get("integration_needs", [])
    if not isinstance(integration_needs, list):
        integration_needs = []

    validated_needs = []
    for need in integration_needs:
        if isinstance(need, dict):
            validated_needs.append(
                {
                    "system": str(need.get("system", "")),
                    "steps_affected": [str(s) for s in need.get("steps_affected", []) if s],
                    "reason": str(need.get("reason", "")),
                    "access_required": str(need.get("access_required", "")),
                    "api_endpoint": need.get("api_endpoint") or None,
                    "mcp_server": need.get("mcp_server") or None,
                    "documentation_url": need.get("documentation_url") or None,
                    "auth_method": need.get("auth_method") or None,
                }
            )

    with transaction.atomic():
        candidate = CaptureCandidate.objects.create(
            credential=credential,
            title=title,
            slug=slug,
            description=str(data.get("description", ""))[:2000],
            content_md=str(data.get("content_md", "")),
            frontmatter_yaml=str(data.get("frontmatter_yaml", "")),
            probability_score=page_score,
            automation_tier=tier,
            automation_reasoning=str(data.get("automation_reasoning", "")),
            integration_needs=validated_needs if tier == AutomationTier.NEEDS_INTEGRATION else [],
            grounding_sources=grounding_sources or [],
            status=CandidateStatus.PENDING,
        )
        CandidateSource.objects.create(candidate=candidate, synced_page=source_page)

    return candidate


def _unique_slug(credential: ConnectorCredential, title: str) -> str:
    import re as _re

    from django.db.models import IntegerField, Max
    from django.db.models.functions import Cast, Substr

    base = slugify(title)[:180] or "process"
    active = CaptureCandidate.objects.filter(credential=credential).exclude(
        status=CandidateStatus.DISMISSED
    )
    if not active.filter(slug=base).exists():
        return base

    prefix = f"{base}-"
    max_n = (
        (
            active.filter(
                slug__startswith=prefix,
                slug__regex=rf"^{_re.escape(base)}-\d+$",
            )
            .annotate(_suffix=Cast(Substr("slug", len(prefix) + 1), IntegerField()))
            .aggregate(m=Max("_suffix"))["m"]
        )
        or 0
    )
    return f"{base}-{max_n + 1}"


def _parse_json_array(text: str) -> list:
    """Extract a JSON array from LLM output that may contain markdown fences."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Strip markdown code fence
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Find bare JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        result = json.loads(match.group(0))
        if isinstance(result, list):
            return result
    logger.warning("No JSON array found in extraction response, returning empty list")
    return []
