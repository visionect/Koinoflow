"""
Smithery MCP Registry client.

Used to enrich extraction prompts with pointers to existing MCP servers that
match the integration needs discovered in a Confluence page. This gives the
LLM concrete, verifiable server options rather than having to speculate.

All network I/O is synchronous (httpx) because this runs inside a Celery worker.
A missing or empty API key degrades gracefully — no context is injected.

Results are cached in Redis (the project's existing cache backend) for
SMITHERY_CACHE_TTL_SECONDS (default: 24 h). Errors are never cached so
transient failures are retried on the next extraction run.
"""

import logging

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)

_REGISTRY_BASE = "https://registry.smithery.ai"
_PAGE_SIZE = 5
_REQUEST_TIMEOUT = 8  # seconds
_CACHE_KEY_PREFIX = "smithery:q:"
_DEFAULT_CACHE_TTL = 86_400  # 24 hours


def extract_service_keywords(title: str, content: str) -> list[str]:
    """
    Derive search keywords from page title and content.

    Looks for well-known service names and tools in the text rather than doing
    any NLP — cheap and good enough for registry lookups.
    """
    text = f"{title} {content[:3000]}".lower()

    candidates = [
        "github",
        "gitlab",
        "jira",
        "confluence",
        "slack",
        "notion",
        "linear",
        "asana",
        "trello",
        "salesforce",
        "hubspot",
        "zendesk",
        "pagerduty",
        "datadog",
        "sentry",
        "aws",
        "gcp",
        "azure",
        "kubernetes",
        "docker",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "elasticsearch",
        "snowflake",
        "bigquery",
        "stripe",
        "twilio",
        "sendgrid",
        "zapier",
        "airtable",
        "google sheets",
        "google drive",
        "google calendar",
        "outlook",
        "teams",
        "zoom",
        "figma",
        "vercel",
        "netlify",
        "heroku",
        "terraform",
        "ansible",
    ]
    return [kw for kw in candidates if kw in text]


def search_mcp_servers(query: str, api_key: str = "") -> list[dict]:
    """
    Query the Smithery registry for MCP servers matching *query*.

    Results are cached in Redis for SMITHERY_CACHE_TTL_SECONDS. On any network
    or API error the cache is not written and an empty list is returned so the
    next extraction run will retry.

    Returns a list of dicts with keys: qualifiedName, displayName, description, homepage.
    """
    from django.conf import settings

    ttl: int = getattr(settings, "SMITHERY_CACHE_TTL_SECONDS", _DEFAULT_CACHE_TTL)
    cache_key = f"{_CACHE_KEY_PREFIX}{query}"

    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug("Smithery cache hit for query=%r (%d servers)", query, len(cached))
        return cached

    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    params = {"q": query, "pageSize": str(_PAGE_SIZE)}
    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.get(f"{_REGISTRY_BASE}/servers", params=params, headers=headers)
            response.raise_for_status()
            servers: list[dict] = response.json().get("servers", [])

        cache.set(cache_key, servers, timeout=ttl)
        logger.debug(
            "Smithery cache set for query=%r (%d servers, ttl=%ds)", query, len(servers), ttl
        )
        return servers
    except Exception:
        logger.debug("Smithery registry lookup failed for query=%r", query, exc_info=True)
        return []


def build_smithery_context(keywords: list[str]) -> str:
    """
    Search for each keyword and return a Markdown block listing relevant MCP servers.

    Returns an empty string when no keywords are provided or no results are found,
    so the calling code can skip the injection entirely.
    """
    from django.conf import settings

    api_key: str = getattr(settings, "SMITHERY_API_KEY", "")

    if not keywords:
        return ""

    seen_names: set[str] = set()
    entries: list[str] = []

    for keyword in keywords[:6]:  # cap to avoid too many requests
        for server in search_mcp_servers(keyword, api_key=api_key):
            name = server.get("qualifiedName") or server.get("displayName", "")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            display = server.get("displayName", name)
            description = server.get("description", "").strip()
            homepage = server.get("homepage", "")
            line = f"- **{display}** (`{name}`)"
            if description:
                line += f": {description}"
            if homepage:
                line += f" — {homepage}"
            entries.append(line)

    if not entries:
        return ""

    lines = [
        "### Available MCP servers from the Smithery registry",
        "",
        "When classifying integration_needs, prefer these verified MCP servers"
        " over generic descriptions:",
        "",
        *entries,
    ]
    return "\n".join(lines)
