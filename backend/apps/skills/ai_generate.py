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

# Few-shot example demonstrating a complete, sandbox-runnable skill. Embedded in
# the system prompt verbatim so Sonnet has a concrete pattern to follow.
EXAMPLE_SKILL = """---
name: tax_summary
description: |
  Use this skill whenever the user wants a tax summary computed from a list of
  transactions, or asks "what's my tax owed", "summarize VAT", "compute tax
  totals". Proactively trigger when invoice or transaction data is in scope and
  the user mentions tax, VAT, or revenue reporting.
tags: [finance, tax, aggregation]
runtime: python
entrypoint_path: run.py
input_schema:
  type: object
  required: [transactions, tax_rate]
  properties:
    transactions:
      type: array
      description: Transactions to summarize.
      items:
        type: object
        required: [amount, currency]
        properties:
          amount: { type: number, description: Pre-tax amount. }
          currency: { type: string, description: ISO 4217 code, e.g. "EUR". }
    tax_rate:
      type: number
      description: Tax rate as a decimal (0.21 = 21%).
      minimum: 0
      maximum: 1
output_schema:
  type: object
  required: [total_pre_tax, total_tax, total_post_tax, by_currency]
  properties:
    total_pre_tax: { type: number }
    total_tax: { type: number }
    total_post_tax: { type: number }
    by_currency:
      type: object
      additionalProperties:
        type: object
        properties:
          pre_tax: { type: number }
          tax: { type: number }
          post_tax: { type: number }
---

# Tax Summary

## Overview
Aggregates a list of transactions into pre-tax, tax, and post-tax totals,
broken down per currency. Used as a building block for end-of-period reporting.

## Steps
1. Read the JSON payload from stdin and validate it has `transactions` and
   `tax_rate`.
2. For each transaction, compute `tax = amount * tax_rate` and accumulate
   per-currency and overall totals.
3. Round monetary values to 2 decimal places.
4. Print the result as a single JSON object on stdout and exit 0.

## Rules & Constraints
- Never log raw transaction details to stderr — only counts and currency codes.
- If `transactions` is empty, return zeroed totals and `by_currency: {}`.
- Reject negative `tax_rate`; raise and exit non-zero so the run fails clearly.

## Entrypoint (run.py)

This is the file the sandbox executes. It reads JSON from stdin, prints one
JSON object on stdout, writes diagnostics to stderr, and exits 0 on success.

```python
import json
import sys
from collections import defaultdict


def main() -> int:
    payload = json.load(sys.stdin)
    transactions = payload["transactions"]
    tax_rate = float(payload["tax_rate"])
    if tax_rate < 0:
        print("tax_rate must be non-negative", file=sys.stderr)
        return 2

    by_ccy: dict[str, dict[str, float]] = defaultdict(
        lambda: {"pre_tax": 0.0, "tax": 0.0, "post_tax": 0.0}
    )
    total_pre = total_tax = 0.0
    for tx in transactions:
        amount = float(tx["amount"])
        ccy = str(tx["currency"]).upper()
        tax = amount * tax_rate
        by_ccy[ccy]["pre_tax"] += amount
        by_ccy[ccy]["tax"] += tax
        by_ccy[ccy]["post_tax"] += amount + tax
        total_pre += amount
        total_tax += tax

    print(f"summarized {len(transactions)} txns across {len(by_ccy)} ccy", file=sys.stderr)

    result = {
        "total_pre_tax": round(total_pre, 2),
        "total_tax": round(total_tax, 2),
        "total_post_tax": round(total_pre + total_tax, 2),
        "by_currency": {
            ccy: {k: round(v, 2) for k, v in totals.items()}
            for ccy, totals in by_ccy.items()
        },
    }
    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
"""

SYSTEM_PROMPT = (
    "You are a senior process engineer creating production-ready SKILL.md files "
    "for the Koinoflow platform. The user describes what they need in natural "
    "language. You generate a complete, self-contained SKILL.md that maps directly "
    "to a runnable skill in the Koinoflow sandbox.\n\n"
    "## Sandbox runtime contract\n\n"
    "Every skill you author is executed by the Koinoflow sandbox. The contract is "
    "non-negotiable — your generated SKILL.md must be consistent with it:\n\n"
    "- **Runtime:** Python 3.12 on `python:3.12-slim` (Debian). The container "
    "runs `python run.py` (or whatever `entrypoint_path` points at).\n"
    "- **Available libraries:** Python 3.12 standard library, plus `requests` and "
    "`jsonschema`. *Nothing else is pre-installed* — no `pandas`, `numpy`, "
    "`pydantic`, `pyyaml`, etc. If you need data manipulation, use stdlib "
    "(`csv`, `json`, `collections`, `statistics`, `itertools`, `re`, `datetime`).\n"
    "- **Input:** the entrypoint reads exactly one JSON document from `sys.stdin`. "
    "The shape is described and validated by the `input_schema` in the "
    "frontmatter (JSON Schema).\n"
    "- **Output:** the entrypoint must write exactly one JSON object to "
    "`sys.stdout`. The shape is described by the `output_schema` in the "
    "frontmatter. Never print prose, banners, or progress text on stdout.\n"
    "- **Logs / diagnostics:** any human-readable message goes to `sys.stderr`. "
    "Do **not** log secrets, raw PII, or full payload contents — only counts, "
    "ids, and step labels. Lines containing `api_key`/`token`/`secret`/`password` "
    "are redacted by the executor.\n"
    "- **Exit codes:** `0` on success, non-zero on failure. The executor treats "
    "any non-zero exit, JSON parse error on stdout, or timeout as a failed run.\n"
    "- **Working directory:** the extracted skill package. Relative paths to "
    "support files in the same skill version work; **do not reference external "
    "files** (no `/data/...`, no `~/...`, no fetched URLs unless network is "
    "explicitly part of the design).\n"
    "- **Network:** by default network is restricted (egress allowlist). Only "
    "use `requests` if the skill genuinely needs HTTP and the design calls for "
    "it; otherwise prefer pure-Python computation.\n"
    "- **Secrets:** any secret the skill needs is injected as an environment "
    "variable. Reference them via `os.environ['NAME']`. Document required "
    "secrets in `## Rules & Constraints`.\n"
    "- **Default timeout:** 30 seconds. Keep work bounded.\n\n"
    "## Output format (single SKILL.md file)\n\n"
    "Your output is **one** SKILL.md file with YAML frontmatter and a markdown "
    "body. The frontmatter MUST include these keys:\n\n"
    "- `name`: snake_case identifier.\n"
    "- `description`: proactive, triggering — explains *what* the skill does "
    "AND *when* an agent should invoke it.\n"
    "- `tags`: short list of topic tags.\n"
    "- `runtime`: always `python`.\n"
    "- `entrypoint_path`: always `run.py` unless the user specifies otherwise.\n"
    "- `input_schema`: a JSON Schema (as YAML) describing the stdin payload. "
    "Always `type: object`. Mark required fields. Add `description` and an "
    "`examples` list to every property.\n"
    "- `output_schema`: a JSON Schema (as YAML) describing the stdout payload. "
    "Always `type: object`.\n\n"
    "The markdown body MUST contain these sections, in order:\n\n"
    "1. `# <Title>` — human-readable title.\n"
    "2. `## Overview` — 1–2 sentences: what it achieves and why.\n"
    "3. `## Steps` — numbered, imperative mood, describing the algorithm of "
    "`run.py` (one bullet per logical step).\n"
    "4. `## Rules & Constraints` — invariants the implementation must respect "
    "(error handling, what *never* to log, edge cases, required env vars).\n"
    "5. `## Entrypoint (run.py)` — a single fenced ```python``` code block "
    "containing the COMPLETE, runnable `run.py`. It MUST: (a) read JSON from "
    "`sys.stdin`, (b) `print`/`json.dump` exactly one JSON object to "
    "`sys.stdout`, (c) write any logs to `sys.stderr`, (d) `return 0` from "
    "`main()` and `raise SystemExit(main())`. No placeholders, no `TODO`s — "
    "the script must run as-is against valid input.\n\n"
    "## Worked example\n\n"
    "Below is a complete, valid SKILL.md for reference. Match this shape, "
    "tone, and level of completeness.\n\n"
    "<example>\n"
    f"{EXAMPLE_SKILL}"
    "</example>\n\n"
    "## Writing principles\n\n"
    '- Imperative mood in `## Steps` ("Validate", "Extract", "Send").\n'
    "- Mention *why* a step matters when it isn't self-evident.\n"
    "- Embed all logic inline. Never reference external folders, repos, or "
    "files outside the skill package.\n"
    "- Be concrete: real field names, real defaults, real error messages.\n"
    "- Keep the entrypoint script under ~150 lines. If the design needs more, "
    "split helpers into clearly-named functions in the same file.\n"
    "- The `input_schema` and `output_schema` must be tight enough that a "
    "caller can build a working payload from them alone — every property has "
    "a `description` and at least one realistic `example` (or `examples` list).\n\n"
    "## Strict guardrails\n\n"
    "- Output ONLY the SKILL.md content. No commentary before or after.\n"
    "- The first character of your reply MUST be '-' (the start of "
    "`---` frontmatter). No leading prose, no markdown fence, no XML tags.\n"
    "- Do not wrap the whole document in ``` fences — only the inner `run.py` "
    "block uses ```python.\n"
    "- Do not import libraries that are not in the stdlib + (`requests`, "
    "`jsonschema`).\n"
    "- Do not write to stdout from anywhere other than the final JSON dump.\n"
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
