"""
Phase 1 — Page scoring.

Scores each SyncedPage with a lightweight LLM to estimate the probability
that the page describes an operational process. Pages scoring below
SCORE_THRESHOLD are filtered out before the more expensive extraction phase.

Scoring runs concurrently using a thread pool since each call is independent
and the LLM SDK is synchronous.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NamedTuple

from apps.connectors.models import SyncedPage

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.3
MAX_CONTENT_CHARS = 4_000
MAX_WORKERS = 2


class PageScore(NamedTuple):
    page: SyncedPage
    score: float
    reason: str


def score_pages(pages: list[SyncedPage]) -> list[PageScore]:
    """
    Score all pages with the lightweight model.

    Returns only pages whose score meets SCORE_THRESHOLD, ordered by score
    descending (highest confidence first for extraction).
    """
    from apps.connectors.capture.llm import get_scoring_model
    from apps.connectors.capture.prompts import SCORING_SYSTEM_PROMPT, SCORING_USER_TEMPLATE

    model = get_scoring_model()
    results: list[PageScore] = []

    def score_one(page: SyncedPage) -> PageScore:
        content_preview = page.content_md[:MAX_CONTENT_CHARS]
        user_msg = SCORING_USER_TEMPLATE.format(
            title=page.title,
            content=content_preview,
        )
        try:
            result = model.generate(
                system=SCORING_SYSTEM_PROMPT,
                user=user_msg,
                max_tokens=1024,
            )
            data = _parse_json_object(result.text)
            score = max(0.0, min(1.0, float(data.get("score", 0.0))))
            reason = str(data.get("reason", ""))
            return PageScore(page=page, score=score, reason=reason)
        except Exception:
            logger.warning("Scoring failed for page %s (%s)", page.id, page.title, exc_info=True)
            return PageScore(page=page, score=0.0, reason="scoring_error")

    all_scores: list[PageScore] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(score_one, page): page for page in pages}
        for future in as_completed(futures):
            all_scores.append(future.result())

    _persist_scores(all_scores)

    results = [ps for ps in all_scores if ps.score >= SCORE_THRESHOLD]
    results.sort(key=lambda r: r.score, reverse=True)
    logger.info(
        "Scored %d pages, %d above threshold %.1f", len(pages), len(results), SCORE_THRESHOLD
    )
    return results


def _persist_scores(scores: list[PageScore]) -> None:
    """Bulk-update last_score on each SyncedPage."""
    for ps in scores:
        ps.page.last_score = ps.score
    SyncedPage.objects.bulk_update([ps.page for ps in scores], ["last_score"])


def _parse_json_object(text: str) -> dict:
    """Extract a JSON object from LLM output that may contain markdown fences
    or be truncated mid-response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Find bare JSON object
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    # Truncated JSON — try to repair by closing open strings and braces
    repaired = _repair_truncated_json(text)
    if repaired is not None:
        return repaired
    raise ValueError(f"No JSON object found in LLM response: {text[:300]!r}")


def _repair_truncated_json(text: str) -> dict | None:
    """Best-effort repair of truncated JSON like '{"score": 0.8, "reason'."""
    match = re.search(r"\{", text)
    if not match:
        return None
    fragment = text[match.start() :]
    # Close any trailing open string, then close the object
    for suffix in ["}", '"}', '""}', '":""}']:
        try:
            return json.loads(fragment + suffix)
        except json.JSONDecodeError:
            continue
    # Last resort: regex out a score value
    score_match = re.search(r'"score"\s*:\s*([\d.]+)', fragment)
    if score_match:
        try:
            return {"score": float(score_match.group(1)), "reason": "truncated_response"}
        except ValueError:
            pass
    return None
