"""
Streaming AI-assisted file edits for the sandbox debugger's mini IDE.

Sends the current file (and an optional context bundle: skill description,
input schema, recent run logs/error) to Claude on Vertex AI and streams a
token-by-token rewrite back to the browser as Server-Sent Events.

The model is instructed to emit ONLY the new file content — no prose, no
markdown fences. The frontend renders the stream live in a side preview so
the developer can see the rewrite take shape and accept it when ready.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from django.conf import settings

from apps.connectors.capture.llm import (
    VERTEX_AUTH_SCOPE,
    _resolve_vertex_project,
    _vertex_service_account_info,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 8192
SYSTEM_PROMPT = (
    "You are a senior Python engineer pair-programming inside a sandboxed skill "
    "execution environment. You receive a single file from a user's skill, plus "
    "an instruction for how to change it. You may also receive: the skill's "
    "description, its declared input schema, and the most recent failed run's "
    "stderr / error.\n\n"
    "Rewrite the file to satisfy the instruction.\n\n"
    "ENTRYPOINT CONTRACT — non-negotiable:\n"
    "If the file you are editing is the skill entrypoint, the output MUST contain "
    'a working `if __name__ == "__main__":` block that:\n'
    "  1. Reads a JSON object from stdin:  data = json.load(sys.stdin)\n"
    "  2. Does useful work with those inputs.\n"
    "  3. Writes a JSON object to stdout as its final statement:  "
    "json.dump(result, sys.stdout)\n"
    "  4. Writes progress and diagnostic information to stderr.\n"
    "If the entrypoint contract is already present, preserve it. "
    "If it is missing or broken, add or fix it unconditionally — even if the "
    "instruction does not mention it. A skill that does not write JSON to stdout "
    "produces no output and every token spent generating it is wasted.\n\n"
    "CRITICAL — stdout/stderr separation (this is the #1 cause of skill failures):\n"
    "  - stdout MUST contain ONLY a single valid JSON object. Nothing else.\n"
    "  - NEVER use print() to write to stdout for any reason other than the final "
    "JSON output. The executor parses the ENTIRE stdout as JSON — any extra text "
    "will cause a parse error and the skill will fail.\n"
    "  - For debugging, logging, or progress messages, ALWAYS use stderr instead:\n"
    '      import sys; print("debug info", file=sys.stderr)\n'
    "    or:\n"
    '      import sys; sys.stderr.write("debug info\\n")\n'
    '  - NEVER use print("hello world") or any bare print() in the entrypoint — '
    "this writes to stdout and breaks the executor.\n"
    "  - If you need to log something, write to stderr. Always.\n\n"
    "Keep imports tidy; remove any you stop using.\n\n"
    "OUTPUT RULES — read carefully:\n"
    "1. Output ONLY the complete new file contents. Nothing else.\n"
    "2. Do NOT wrap the output in ``` fences.\n"
    "3. Do NOT prefix or suffix any commentary, explanation, or markdown.\n"
    "4. The first character of your reply must be the first character of the "
    "new file (e.g., 'i' for 'import …', '#' for a shebang, etc.).\n"
)


def _build_user_prompt(
    *,
    file_path: str,
    file_type: str,
    file_content: str,
    instruction: str,
    skill_description: str | None,
    input_schema: dict | None,
    recent_error: str | None,
    recent_logs: str | None,
    entrypoint_path: str | None,
) -> str:
    parts: list[str] = []
    if skill_description:
        parts.append(f"# Skill description\n{skill_description.strip()}\n")
    if input_schema:
        parts.append(f"# Input schema\n```json\n{json.dumps(input_schema, indent=2)}\n```\n")
    if entrypoint_path:
        if file_path == entrypoint_path:
            parts.append(
                f"# Entrypoint\nThis file IS the skill entrypoint (`{entrypoint_path}`). "
                'It must contain a working `if __name__ == "__main__":` block that reads '
                "JSON from stdin and writes a JSON object to stdout.\n"
            )
        else:
            parts.append(
                f"# Entrypoint\nThe skill entrypoint is `{entrypoint_path}` (not this file). "
                "Ensure your edits do not break any module-level API that the entrypoint "
                "depends on.\n"
            )
    if recent_error:
        parts.append(f"# Most recent error\n```\n{recent_error.strip()}\n```\n")
    if recent_logs:
        # Only the last ~4 KB of logs to keep the prompt small
        snippet = recent_logs[-4096:]
        parts.append(f"# Most recent stderr / logs (tail)\n```\n{snippet}\n```\n")
    parts.append(
        f"# File to edit: `{file_path}` ({file_type})\n```{file_type or ''}\n{file_content}\n```\n"
    )
    parts.append(f"# Instruction\n{instruction.strip()}\n")
    parts.append(
        "# Your reply\nOutput the complete new contents of the file above. No fences, no prose."
    )
    return "\n".join(parts)


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


def stream_ai_edit(
    *,
    file_path: str,
    file_type: str,
    file_content: str,
    instruction: str,
    skill_description: str | None = None,
    input_schema: dict | None = None,
    recent_error: str | None = None,
    recent_logs: str | None = None,
    entrypoint_path: str | None = None,
    model: str | None = None,
) -> Iterator[bytes]:
    """Yield SSE-encoded events as the model streams the rewrite."""
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

    chosen_model = (model or getattr(settings, "SKILL_AI_EDIT_MODEL", DEFAULT_MODEL)).strip()
    if not chosen_model:
        chosen_model = DEFAULT_MODEL

    user_prompt = _build_user_prompt(
        file_path=file_path,
        file_type=file_type,
        file_content=file_content,
        instruction=instruction,
        skill_description=skill_description,
        input_schema=input_schema,
        recent_error=recent_error,
        recent_logs=recent_logs,
        entrypoint_path=entrypoint_path,
    )

    yield _sse(
        "start",
        {
            "model": chosen_model,
            "file_path": file_path,
            "instruction": instruction,
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
            for chunk in stream.text_stream:
                if not chunk:
                    continue
                yield _sse("delta", {"text": chunk})
            final_message = stream.get_final_message()
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
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("AI edit stream failed: %s", exc)
        yield _sse("error", {"message": f"AI edit failed: {exc}"})
