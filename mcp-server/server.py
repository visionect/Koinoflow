import asyncio
import base64
import contextvars
import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api_client import KoinoflowAPIClient, KoinoflowAPIError
from auth import get_protected_resource_metadata, get_www_authenticate_header, introspect_token
from config import (
    ALLOWED_HOSTS,
    ALLOWED_ORIGINS,
    APPROVAL_TOKEN_SECRET,
    APPROVAL_TOKEN_TTL_SECONDS,
    MCP_SERVER_URL,
    SERVER_HOST,
    SERVER_PORT,
)

# ── Per-request auth context (set by middleware) ─────────────────────────

logger = logging.getLogger(__name__)

_MCP_CLIENTS: dict = {}
_clients_path = Path(__file__).parent / "mcp-clients.json"
if _clients_path.exists():
    with open(_clients_path) as f:
        _MCP_CLIENTS = json.load(f)
else:
    # Without this registry every client resolves to the "MCP" fallback in
    # analytics, hiding which tools are actually calling us. Fail loud rather
    # than silently lose attribution.
    logger.warning(
        "mcp-clients.json not found at %s — all client_type values will fall back to 'MCP'",
        _clients_path,
    )

_token_info_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "token_info", default=None
)
_REQUESTED_SCOPES = "skills:read skills:write usage:write"
_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)


class _OAuthMiddleware(BaseHTTPMiddleware):
    """
    Validates OAuth Bearer tokens on MCP requests, serves the Protected
    Resource Metadata endpoint (RFC 9728), and returns proper 401 responses.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path == "/.well-known/oauth-protected-resource":
            metadata = get_protected_resource_metadata()
            return JSONResponse(
                metadata,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "public, max-age=3600",
                },
            )

        if path in ("/healthz", "/"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = (
            auth_header[len("Bearer ") :].strip()
            if auth_header.lower().startswith("bearer ")
            else None
        )

        if not token:
            return Response(
                status_code=401,
                headers={
                    "WWW-Authenticate": get_www_authenticate_header(_REQUESTED_SCOPES),
                },
            )

        token_data = await introspect_token(token)
        if not token_data:
            return Response(
                status_code=401,
                headers={
                    "WWW-Authenticate": get_www_authenticate_header(_REQUESTED_SCOPES),
                },
            )

        _token_info_var.set(token_data)
        response = await call_next(request)
        return response


# ── Transport security ───────────────────────────────────────────────────

allowed_hosts = list(ALLOWED_HOSTS)
allowed_hosts.extend(
    [
        "localhost",
        "127.0.0.1",
        f"localhost:{SERVER_PORT}",
        f"127.0.0.1:{SERVER_PORT}",
    ]
)

allowed_origins = list(ALLOWED_ORIGINS)
# Derive a default allowed origin from the advertised MCP_SERVER_URL so that
# deployments don't have to configure it twice. Browser-based clients must
# originate from the server's own URL (or an explicitly allow-listed one) to
# pass DNS-rebinding / cross-origin checks.
if MCP_SERVER_URL:
    origin = MCP_SERVER_URL.rstrip("/")
    if origin not in allowed_origins:
        allowed_origins.append(origin)
allowed_origins.extend(
    [
        f"http://localhost:{SERVER_PORT}",
        f"http://127.0.0.1:{SERVER_PORT}",
    ]
)

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=allowed_hosts,
    allowed_origins=allowed_origins,
)

# ── FastMCP instance ─────────────────────────────────────────────────────

mcp = FastMCP(
    "Koinoflow",
    instructions=(
        "Koinoflow exposes the organization's approved, versioned operational "
        "skills. Tool choice rule: when the user describes a "
        "task, goal, incident, question, or desired action and no exact skill "
        "slug is known, call discover_skills first. After selecting the best "
        "candidate, call read_skill before giving organization-specific "
        "guidance or executing steps. Do not use list_skills for task "
        "matching; use it only when the user explicitly asks to browse, list, "
        "page through, audit, or debug available skills. Each skill may "
        "include a Koinoflow Context block summarizing risk level, approval "
        "requirements, prerequisites, audience, and retrieval keywords. "
        "propose_skill_update and apply_skill_update are available for "
        "suggesting and publishing new skill versions."
    ),
    transport_security=transport_security,
    stateless_http=True,
)

_NO_AUTH_MSG = "Error: not authenticated. Your MCP client should handle OAuth automatically."


def _get_client() -> KoinoflowAPIClient | None:
    """Build an API client using the authenticated user's context."""
    token_data = _token_info_var.get()
    if not token_data:
        return None
    return KoinoflowAPIClient(token_data=token_data)


def _has_scope(scope: str) -> bool:
    token_data = _token_info_var.get() or {}
    scopes = {s for s in token_data.get("scope", "").split() if s}
    return scope in scopes


def _mcp_client_type(ctx: Context) -> str:
    """Resolve clientInfo.name from the MCP initialize handshake to a ClientType value."""
    try:
        params = ctx.request_context.session.client_params
        if params and params.clientInfo:
            record = _MCP_CLIENTS.get(params.clientInfo.name)
            if record:
                return record["title"]
    except Exception:
        pass
    return "MCP"


def _mcp_client_id(ctx: Context) -> str:
    """Return 'name/version' from clientInfo, falling back to 'mcp-remote'."""
    try:
        params = ctx.request_context.session.client_params
        if params and params.clientInfo:
            name = params.clientInfo.name
            version = params.clientInfo.version
            return f"{name}/{version}" if version else name
    except Exception:
        pass
    return "mcp-remote"


def _to_raw_markdown(frontmatter: str, content: str) -> str:
    if frontmatter:
        return f"---\n{frontmatter}\n---\n\n{content}"
    return content


_RISK_LEVEL_GUIDANCE = {
    "low": "Low risk — normal caution.",
    "medium": "Medium risk — confirm destructive actions before executing.",
    "high": "**High risk** — confirm each destructive step with the user before executing.",
    "critical": (
        "**Critical risk** — do not execute any step without explicit per-step user "
        "confirmation. Escalate on ambiguity."
    ),
}


def _build_koinoflow_context_block(metadata: dict | None) -> str:
    """Render a Koinoflow Context block from normalized metadata.

    Returns an empty string if metadata is None, empty, or all fields are unset.
    """
    if not isinstance(metadata, dict):
        return ""

    keywords = metadata.get("retrieval_keywords") or []
    risk_level = metadata.get("risk_level")
    requires_approval = bool(metadata.get("requires_human_approval"))
    prerequisites = metadata.get("prerequisites") or []
    audience = metadata.get("audience") or []

    if not any([keywords, risk_level, requires_approval, prerequisites, audience]):
        return ""

    lines = ["> **Koinoflow Context**"]
    if risk_level:
        guidance = _RISK_LEVEL_GUIDANCE.get(risk_level, "")
        lines.append(f"> - Risk level: **{risk_level}**" + (f" — {guidance}" if guidance else ""))
    if requires_approval:
        lines.append(
            "> - **Requires human approval** before execution — confirm the plan with "
            "the user before taking any step."
        )
    if prerequisites:
        joined = ", ".join(f"`{p}`" for p in prerequisites)
        lines.append(f"> - Prerequisites: read {joined} first")
    if audience:
        lines.append(f"> - Audience: {', '.join(audience)}")
    if keywords:
        lines.append(f"> - Retrieval keywords: {', '.join(keywords)}")
    return "\n".join(lines)


def _format_discovery_results(data: dict, query: str) -> str:
    items = data.get("items", [])
    if not items:
        status = data.get("embedding_status", "unavailable")
        return f"No skill matches found for `{query}`. (embedding status: {status})"

    status = data.get("embedding_status", "unavailable")
    lines = [
        f"Top {len(items)} skill matches for `{query}` (embedding status: {status}):",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        line = f"{idx}. **{item['title']}** (`{item['slug']}`) [score: {item.get('score', 0):.2f}]"
        org = " / ".join(
            part for part in (item.get("team_name"), item.get("department_name")) if part
        )
        if org:
            line += f" — {org}"
        if item.get("current_version_number"):
            line += f" [v{item['current_version_number']}]"
        if item.get("risk_level"):
            line += f" [risk: {item['risk_level']}]"
        if item.get("requires_human_approval"):
            line += " [needs approval]"
        if not item.get("indexed", False):
            line += " [not semantically indexed]"
        lines.append(line)
        reasons = item.get("match_reasons") or []
        if reasons:
            lines.append(f"   Reasons: {', '.join(reasons)}")
        snippet = item.get("snippet")
        if snippet:
            lines.append(f"   Snippet: {snippet}")
    lines.append("")
    lines.append("Call read_skill with the best matching slug before executing the skill.")
    return "\n".join(lines)


def _parse_raw_markdown(raw_markdown: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(raw_markdown.strip())
    if not match:
        return "", raw_markdown.strip()
    return match.group(1).strip(), match.group(2).strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _issue_approval_token(
    *,
    slug: str,
    proposed_markdown: str,
    change_summary: str,
    token_data: dict,
) -> tuple[str, int]:
    now = int(time.time())
    expires_at = now + APPROVAL_TOKEN_TTL_SECONDS
    payload = {
        "slug": slug,
        "proposed_hash": _content_hash(proposed_markdown),
        "change_summary_hash": _content_hash(change_summary),
        "sub": token_data.get("sub", ""),
        "workspace_id": token_data.get("workspace_id", ""),
        "iat": now,
        "exp": expires_at,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_encoded = _b64url_encode(payload_json)
    signature = hmac.new(
        APPROVAL_TOKEN_SECRET.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{payload_encoded}.{signature}", expires_at


def _validate_approval_token(
    *,
    approval_token: str,
    slug: str,
    proposed_markdown: str,
    change_summary: str,
    token_data: dict,
) -> str | None:
    try:
        payload_encoded, signature = approval_token.split(".", 1)
    except ValueError:
        return "Invalid approval token format."

    expected_signature = hmac.new(
        APPROVAL_TOKEN_SECRET.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return "Approval token signature is invalid."

    try:
        payload = json.loads(_b64url_decode(payload_encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return "Approval token payload is invalid."

    if int(time.time()) > int(payload.get("exp", 0)):
        return "Approval token expired. Request approval again."
    if payload.get("slug") != slug:
        return "Approval token does not match the skill slug."
    if payload.get("proposed_hash") != _content_hash(proposed_markdown):
        return "Approval token does not match the proposed markdown."
    if payload.get("change_summary_hash") != _content_hash(change_summary):
        return "Approval token does not match the change summary."
    if payload.get("sub") and payload.get("sub") != token_data.get("sub"):
        return "Approval token does not belong to the current user."
    if payload.get("workspace_id") and payload.get("workspace_id") != token_data.get(
        "workspace_id"
    ):
        return "Approval token does not belong to the current workspace."
    return None


def _refinement_suggestions(markdown: str) -> list[str]:
    suggestions: list[str] = []
    content = markdown.strip()
    lowered = content.lower()
    if "## " not in content:
        suggestions.append("Add section headings so agents and humans can navigate steps quickly.")
    if not re.search(r"^\s*(?:\d+\.|-)\s+\S+", content, re.MULTILINE):
        suggestions.append("Use numbered or bulleted action steps for executable instructions.")
    if "prerequisite" not in lowered and "requirements" not in lowered:
        suggestions.append(
            "Include a prerequisites section with required access, tools, and dependencies."
        )
    if "owner" not in lowered and "responsible" not in lowered:
        suggestions.append("Identify an owner or responsible role for each critical step.")
    if "rollback" not in lowered and "failure" not in lowered and "incident" not in lowered:
        suggestions.append(
            "Document rollback/failure handling so the process is safe under errors."
        )
    if not suggestions:
        suggestions.append(
            "The skill is structured. Consider adding measurable success criteria for each outcome."
        )
    return suggestions


# ── Tools ────────────────────────────────────────────────────────────────


@mcp.tool(
    annotations=ToolAnnotations(title="Read skill", readOnlyHint=True),
)
async def read_skill(
    slug: str,
    ctx: Context,
    version: int | None = None,
    include_files: bool = True,
) -> str:
    """Load the full approved Koinoflow process for a specific slug.

    Use this when a matching process slug is known (directly from the user or
    from discover_skills/list_skills). For task-based user requests,
    discover_skills should usually be called before this tool unless the
    slug is already known. Returns the Markdown process with YAML frontmatter
    and, when present, a Koinoflow Context block summarizing the process's risk
    level, approval requirements, prerequisites, audience, and retrieval
    keywords. A listing of support files is appended by default.

    Args:
        slug: The process slug (e.g., "deploy-to-production")
        version: Optional specific version number to retrieve
        include_files: If true, append a listing of support files to the response
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG
    try:
        data = await client.get_skill(slug, version)
    except KoinoflowAPIError as e:
        return f"Error fetching skill: {e}"

    version_data = data.get("current_version") or data

    asyncio.create_task(
        client.log_usage(
            skill_id=data.get("id", ""),
            version_number=version_data.get("version_number", 0),
            client_id=_mcp_client_id(ctx),
            client_type=_mcp_client_type(ctx),
            tool_name="read_skill",
        )
    )

    content = version_data.get("content_md", "")
    frontmatter = version_data.get("frontmatter_yaml", "")
    metadata = version_data.get("koinoflow_metadata") or {}
    context_block = _build_koinoflow_context_block(metadata)

    body = f"{context_block}\n\n{content}" if context_block else content
    result = f"---\n{frontmatter}\n---\n\n{body}" if frontmatter else body

    if include_files:
        files = version_data.get("files", [])
        lines = [f"\n\n---\n## Support Files ({len(files)} files)"]
        for f in files:
            size_kb = round(f.get("size_bytes", 0) / 1024, 1)
            mime = f.get("mime_type") or f.get("file_type", "text")
            lines.append(f"- {f['path']} ({mime}, {size_kb} KB)")
        result += "\n".join(lines)

    return result


@mcp.tool(
    annotations=ToolAnnotations(title="Read skill file", readOnlyHint=True),
)
async def read_skill_file(
    slug: str,
    file_path: str,
    ctx: Context,
    version: int | None = None,
) -> str:
    """Read the contents of a support file attached to a Koinoflow process.

    Returns the raw contents of scripts, references, or other support files
    bundled with a process version. Support file paths for a process are
    listed at the end of the read_skill response.

    Args:
        slug: The process slug (e.g., "deploy-to-production")
        file_path: Path of the file within the process (e.g., "scripts/run.py")
        version: Optional specific version number to retrieve the file from
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG

    if version is None:
        try:
            data = await client.get_skill(slug, None)
            version_data = data.get("current_version") or data
            version = version_data.get("version_number")
        except KoinoflowAPIError as e:
            return f"Error fetching skill: {e}"

    if version is None:
        return "Error: could not determine version number"

    try:
        file_data = await client.get_skill_file(slug, version, file_path)
    except KoinoflowAPIError as e:
        return f"Error fetching file: {e}"

    content = file_data.get("content")
    content_base64 = file_data.get("content_base64")
    file_type = file_data.get("file_type", "text")
    mime_type = file_data.get("mime_type", "text/plain")
    encoding = file_data.get("encoding", "utf-8")
    size_bytes = file_data.get("size_bytes", 0)

    if isinstance(content, str):
        header = f"# {file_path} ({file_type}, {mime_type}, {size_bytes} bytes)\n\n"
        return header + content

    return json.dumps(
        {
            "path": file_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "encoding": encoding,
            "size_bytes": size_bytes,
            "content_base64": content_base64,
        },
        indent=2,
    )


@mcp.tool(
    annotations=ToolAnnotations(title="Discover skills", readOnlyHint=True),
)
async def discover_skills(
    query: str,
    department: str | None = None,
    team: str | None = None,
    limit: int = 10,
) -> str:
    """Find the most relevant Koinoflow processes for a natural-language task.

    Default discovery tool for user intent. Use this before read_skill when
    the user describes what they want to do and the exact process slug is
    unknown. Results are ranked with semantic embeddings plus keyword and
    metadata matches. Do not use list_skills first for task matching.

    Args:
        query: Natural-language task or question to match against processes
        department: Optional department slug to narrow discovery
        team: Optional team slug to narrow discovery
        limit: Max ranked candidates to return (1–25, default 10)
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG
    try:
        data = await client.discover_skills(
            query=query,
            department=department,
            team=team,
            limit=min(max(limit, 1), 25),
        )
    except KoinoflowAPIError as e:
        return f"Error discovering skills: {e}"
    return _format_discovery_results(data, query)


@mcp.tool(
    annotations=ToolAnnotations(title="List skills", readOnlyHint=True),
)
async def list_skills(
    department: str | None = None,
    team: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """List the Koinoflow processes available in the organization.

    Use this only to browse, enumerate, page through, audit, or debug available
    processes. Do not use this for natural-language task matching; call
    discover_skills instead, then read_skill for the selected slug.
    Returns each process's title, slug, description, current version number,
    and — when set — risk level, approval requirement, and retrieval
    keywords. Results can be filtered by department and/or team slug. The
    matching slug can then be passed to read_skill to load the full
    approved instructions.

    Args:
        department: Optional department slug to filter by
        team: Optional team slug to filter by
        search: Optional keyword search across title and description
        limit: Max results to return (1–100, default 100)
        offset: Pagination offset for fetching subsequent pages
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG
    try:
        data = await client.list_skills(
            department=department,
            team=team,
            search=search,
            limit=min(max(limit, 1), 100),
            offset=offset,
        )
    except KoinoflowAPIError as e:
        return f"Error listing skills: {e}"

    items = data.get("items", [])
    total = data.get("count", len(items))
    if not items:
        return "No skills found."

    lines = []
    for p in items:
        line = f"- **{p['title']}** (`{p['slug']}`)"
        if p.get("description"):
            line += f" — {p['description']}"
        line += f" [v{p.get('current_version_number', '?')}]"
        risk = p.get("risk_level")
        if risk:
            line += f" [risk: {risk}]"
        if p.get("requires_human_approval"):
            line += " [needs approval]"
        keywords = p.get("retrieval_keywords") or []
        if keywords:
            line += f" (keywords: {', '.join(keywords)})"
        lines.append(line)

    header = f"Showing {offset + 1}–{offset + len(items)} of {total} skills"
    if offset + len(items) < total:
        header += f" (use offset={offset + len(items)} to fetch more)"
    return header + ":\n\n" + "\n".join(lines)


@mcp.tool(
    annotations=ToolAnnotations(title="Propose skill update", readOnlyHint=True),
)
async def propose_skill_update(
    slug: str,
    proposed_markdown: str,
    change_summary: str,
    version: int | None = None,
) -> str:
    """Preview a proposed update to a Koinoflow process without publishing it.

    Requires the "Allow agent process updates" setting to be enabled in
    Koinoflow Settings (Settings → Allow agent process updates). Use this
    tool to evolve a process after changes have been made to a standard
    procedure and the improved version should be recorded.

    Compares the proposed Markdown against the current process version and
    returns: the current Markdown, the proposed Markdown, the change summary,
    automated refinement suggestions, and a short-lived HMAC-signed approval
    token. The returned approval token is required as an input to
    apply_skill_update; no change is persisted by this tool.
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG
    try:
        settings = await client.get_effective_settings()
    except KoinoflowAPIError:
        settings = {}
    if settings.get("allow_agent_skill_updates") is not True:
        return (
            "Agent skill updates are not enabled for this workspace. "
            "An admin must turn on 'Allow agent skill updates' in Koinoflow "
            "Settings before propose_skill_update or apply_skill_update "
            "can be used."
        )
    try:
        data = await client.get_skill(slug, version)
    except KoinoflowAPIError as e:
        return f"Error fetching skill: {e}"

    version_data = data.get("current_version") or data
    current_markdown = _to_raw_markdown(
        version_data.get("frontmatter_yaml", ""),
        version_data.get("content_md", ""),
    )
    token_data = _token_info_var.get() or {}
    approval_token, expires_at = _issue_approval_token(
        slug=slug,
        proposed_markdown=proposed_markdown,
        change_summary=change_summary,
        token_data=token_data,
    )
    response = {
        "skill_slug": slug,
        "current_markdown": current_markdown,
        "proposed_markdown": proposed_markdown,
        "change_summary": change_summary,
        "refinement_suggestions": _refinement_suggestions(proposed_markdown),
        "approval_token": approval_token,
        "approval_expires_at_epoch": expires_at,
        "requires_user_approval": True,
        "approval_instruction": (
            "The apply_skill_update tool requires explicit user approval of "
            "these exact changes before it is invoked."
        ),
    }
    return json.dumps(response, indent=2)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Apply skill update",
        readOnlyHint=False,
        destructiveHint=True,
    ),
)
async def apply_skill_update(
    slug: str,
    proposed_markdown: str,
    change_summary: str,
    approval_token: str,
) -> str:
    """Publish a new version of a Koinoflow process.

    Requires the "Allow agent process updates" setting to be enabled in
    Koinoflow Settings and the `processes:write` OAuth scope.

    Creates a new process version from the supplied Markdown and change
    summary. Requires the approval_token returned by propose_skill_update
    for the same slug, markdown, and change summary; the token is HMAC-signed
    and short-lived.
    """
    client = _get_client()
    if not client:
        return _NO_AUTH_MSG
    if not _has_scope("skills:write"):
        return "Error applying process update: missing required scope `skills:write`."

    token_data = _token_info_var.get() or {}
    token_error = _validate_approval_token(
        approval_token=approval_token,
        slug=slug,
        proposed_markdown=proposed_markdown,
        change_summary=change_summary,
        token_data=token_data,
    )
    if token_error:
        return f"Error applying skill update: {token_error}"

    frontmatter_yaml, content_md = _parse_raw_markdown(proposed_markdown)
    try:
        version_data = await client.create_skill_version(
            slug,
            content_md=content_md,
            frontmatter_yaml=frontmatter_yaml,
            change_summary=change_summary,
        )
    except KoinoflowAPIError as e:
        return f"Error applying skill update: {e}"

    response = {
        "status": "updated",
        "skill_slug": slug,
        "new_version_id": version_data.get("id"),
        "new_version_number": version_data.get("version_number"),
    }
    return json.dumps(response, indent=2)


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> None:
    app = mcp.streamable_http_app()
    app.add_middleware(_OAuthMiddleware)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
