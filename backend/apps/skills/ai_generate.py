"""
AI-assisted skill generation from scratch using Claude Sonnet 4.6 on Vertex AI.

Provides streaming generation of a complete SKILL.md (frontmatter + content) from
a user's natural-language description, with per-workspace daily rate limiting.
"""

import json
import logging
import re
import secrets
from collections.abc import Iterator
from typing import Any

from django.conf import settings
from django.utils.text import slugify

from apps.connectors.capture.llm import (
    VERTEX_AUTH_SCOPE,
    _resolve_vertex_project,
    _vertex_service_account_info,
)
from apps.skills.constants import AI_FILE_EDIT_LIMIT_PER_HOUR, AI_SKILL_GENERATION_LIMIT_PER_DAY
from apps.skills.models import AIUsageLog

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 16384

SYSTEM_PROMPT = (
    "You are a senior process engineer creating production-ready SKILL.md files "
    "for the Koinoflow platform. The user will describe what they need in natural "
    "language. You will generate a complete, self-contained SKILL.md file.\n\n"
    "## Output format\n\n"
    "Your output must be a single SKILL.md file with this exact structure:\n\n"
    "```\n"
    "---\n"
    "name: <slug-style-identifier>\n"
    "description: <proactive, triggering description — explains what the process "
    'does AND when to use it. Be specific. Example: "Use this process whenever X '
    "happens or Y is requested. Proactively trigger this if the user's context "
    'implies Z.">\n'
    "tags: [<comma-separated tags>]\n"
    "---\n\n"
    "# <Process Title>\n\n"
    "## Overview\n"
    "<1-2 sentence summary of what this process achieves and why it matters>\n\n"
    "## Steps\n\n"
    '1. <Step 1 — imperative mood, e.g. "Validate the input against...">\n'
    "2. <Step 2>\n"
    "...\n\n"
    "## Rules & Constraints\n"
    "- <Rule or constraint that an executor must never violate>\n\n"
    "## Reference Material\n"
    "### <Topic A>\n"
    "<Relevant data, lookup tables, decision trees, or embedded scripts>\n\n"
    "### Output Template\n"
    "<Exact format the executor should produce, using code blocks or markdown tables>\n"
    "```\n\n"
    "## Writing principles\n\n"
    '- Use imperative mood for all steps ("Validate", "Extract", "Send" — not '
    '"You should validate").\n'
    "- Include *why* a step matters whenever it is not self-evident.\n"
    "- Embed any scripts, regex patterns, or decision logic inline as code blocks.\n"
    "- Every output template must be concrete and complete — no placeholders.\n"
    "- Remove filler. Every sentence must contribute to accuracy or execution.\n"
    "- The description must be proactive: tell an AI agent *when* to invoke this "
    "process automatically.\n\n"
    "## Strict guardrails\n\n"
    "- Output ONLY the SKILL.md content. No commentary before or after.\n"
    "- Do not suggest test prompts or mention iteration.\n"
    "- Do not reference external folders, scripts, or files — embed everything.\n"
    "- The output must be a single, standalone file ready for production use.\n"
    "- Do NOT wrap the output in ``` fences. The first character of your reply "
    "must be '-' (from the '---' frontmatter delimiter).\n"
)


def _build_user_prompt(instruction: str) -> str:
    return (
        f"Create a SKILL.md based on the following description:\n\n"
        f"{instruction.strip()}\n\n"
        f"Output the complete SKILL.md file. No fences, no prose."
    )


def _draft_slug_from_instruction(instruction: str) -> str:
    """Slug shown in the UI while streaming. Final slug is parsed from the
    generated frontmatter on the client; this is just a stable placeholder."""
    base = slugify(instruction)[:40].strip("-") or "ai-skill"
    suffix = secrets.token_hex(2)
    return re.sub(r"-+", "-", f"draft-{base}-{suffix}")


def _sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _vertex_service_account_access_token() -> str | None:
    credentials_info = _vertex_service_account_info(settings)
    if credentials_info is None:
        return None

    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=[VERTEX_AUTH_SCOPE]
    )
    credentials.refresh(Request())
    return str(credentials.token) if credentials.token else None


def _build_anthropic_vertex_client(anthropic: Any, *, project: str, location: str):
    client_kwargs: dict[str, Any] = {
        "project_id": project,
        "region": location,
    }
    access_token = _vertex_service_account_access_token()
    if access_token:
        client_kwargs["access_token"] = access_token
    return anthropic.AnthropicVertex(**client_kwargs)


def check_rate_limit(workspace) -> dict[str, Any]:
    """Check if the workspace has exceeded AI usage limits.

    Returns a dict with 'allowed' (bool) and 'remaining' (int) keys.
    Raises ValueError if the limit is exceeded.
    """
    daily_remaining = AIUsageLog.get_remaining_daily(
        workspace, AIUsageLog.UsageType.SKILL_GENERATION, AI_SKILL_GENERATION_LIMIT_PER_DAY
    )
    hourly_remaining = AIUsageLog.get_remaining_hourly(
        workspace, AIUsageLog.UsageType.SKILL_GENERATION, AI_FILE_EDIT_LIMIT_PER_HOUR
    )

    if daily_remaining <= 0:
        return {
            "allowed": False,
            "remaining": 0,
            "reason": f"Daily limit reached ({AI_SKILL_GENERATION_LIMIT_PER_DAY} skills per day).",
        }

    if hourly_remaining <= 0:
        return {
            "allowed": False,
            "remaining": 0,
            "reason": f"Hourly limit reached ({AI_FILE_EDIT_LIMIT_PER_HOUR} skills per hour).",
        }

    return {
        "allowed": True,
        "remaining": min(daily_remaining, hourly_remaining),
    }


def record_usage(workspace, user) -> int:
    """Record an AI usage event and return remaining count."""
    AIUsageLog.record_usage(workspace, user, AIUsageLog.UsageType.SKILL_GENERATION)
    return AIUsageLog.get_remaining_daily(
        workspace, AIUsageLog.UsageType.SKILL_GENERATION, AI_SKILL_GENERATION_LIMIT_PER_DAY
    )


def stream_ai_generate(
    *,
    instruction: str,
    workspace,
    user=None,
    model: str | None = None,
) -> Iterator[bytes]:
    """Yield SSE-encoded events as the model streams the SKILL.md generation."""
    # Check rate limit first
    limit_status = check_rate_limit(workspace)
    if not limit_status["allowed"]:
        yield _sse("error", {"message": limit_status["reason"]})
        return

    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        yield _sse("error", {"message": "anthropic SDK is not installed"})
        return

    project = _resolve_vertex_project(settings)
    location = getattr(settings, "VERTEX_LOCATION", "global")
    if not project:
        yield _sse(
            "error",
            {"message": "Vertex AI is not configured (missing VERTEX project id)"},
        )
        return

    chosen_model = (model or getattr(settings, "SKILL_AI_GENERATE_MODEL", DEFAULT_MODEL)).strip()
    if not chosen_model:
        chosen_model = DEFAULT_MODEL

    user_prompt = _build_user_prompt(instruction)

    yield _sse(
        "start",
        {
            "model": chosen_model,
            "skill_slug": _draft_slug_from_instruction(instruction),
            "instruction": instruction,
            "remaining": limit_status["remaining"],
        },
    )

    try:
        client = _build_anthropic_vertex_client(anthropic, project=project, location=location)
        with client.messages.stream(
            model=chosen_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt,
                        }
                    ],
                }
            ],
        ) as stream:
            for chunk in stream.text.stream:
                if not chunk:
                    continue
                yield _sse("delta", {"text": chunk})
            final_message = stream.get_final_message()

        # Record usage after successful generation
        remaining = record_usage(workspace, user)

        usage = getattr(final_message, "usage", None)
        usage_dict: dict[str, Any] = {}
        if usage is not None:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                value = getattr(usage, key, None)
                if value is not None:
                    usage_dict[key] = value

        yield _sse(
            "done",
            {
                "stop_reason": getattr(final_message, "stop_reason", None),
                "model": chosen_model,
                "usage": usage_dict,
                "remaining": remaining,
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("AI generate stream failed: %s", exc)
        yield _sse("error", {"message": f"AI generation failed: {exc}"})
