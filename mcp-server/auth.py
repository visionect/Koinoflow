"""
OAuth 2.1 Resource Server authentication for the MCP server.

Handles:
- Token introspection against the Django authorization server (RFC 7662)
- Protected Resource Metadata (RFC 9728)
- 401 responses with WWW-Authenticate headers
"""

import time

import httpx

from config import (
    AUTHORIZATION_SERVER_URL,
    MCP_SERVER_URL,
    OAUTH_INTROSPECT_CLIENT_ID,
    OAUTH_INTROSPECT_CLIENT_SECRET,
    OAUTH_INTROSPECT_URL,
    logger,
)

_TOKEN_CACHE: dict[str, tuple[dict, float]] = {}
# Short TTL: revocations propagate from Django to MCP within ``_CACHE_TTL``
# seconds. Keeping this low is the only lever we have (DOT's introspection
# endpoint has no push mechanism) so we tune it for "revoke within ~5s" at
# the cost of a handful more introspect round-trips per active session.
_CACHE_TTL = 5


def get_protected_resource_metadata() -> dict:
    """RFC 9728 Protected Resource Metadata document."""
    return {
        "resource": MCP_SERVER_URL,
        "authorization_servers": [AUTHORIZATION_SERVER_URL],
        "scopes_supported": ["processes:read", "processes:write", "usage:write"],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{AUTHORIZATION_SERVER_URL}/api/docs",
    }


def get_www_authenticate_header(scope: str = "") -> str:
    """Build the WWW-Authenticate header for 401 responses."""
    prm_url = f"{MCP_SERVER_URL}/.well-known/oauth-protected-resource"
    parts = [f'Bearer resource_metadata="{prm_url}"']
    if scope:
        parts.append(f'scope="{scope}"')
    return ", ".join(parts)


async def introspect_token(token: str) -> dict | None:
    """
    Validate a Bearer token via the Django introspect endpoint.

    Returns the introspection response dict if active, or None if invalid/expired.
    Results are cached for _CACHE_TTL seconds.
    """
    now = time.time()
    cached = _TOKEN_CACHE.get(token)
    if cached:
        data, ts = cached
        token_exp = data.get("exp", float("inf"))
        if now - ts < _CACHE_TTL and now < token_exp:
            return data if data.get("active") else None

    if not OAUTH_INTROSPECT_CLIENT_ID or not OAUTH_INTROSPECT_CLIENT_SECRET:
        logger.error("MCP_INTROSPECT_CLIENT_ID/SECRET not configured")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_INTROSPECT_URL,
                data={"token": token},
                auth=(OAUTH_INTROSPECT_CLIENT_ID, OAUTH_INTROSPECT_CLIENT_SECRET),
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.warning("Token introspection request failed", exc_info=True)
        return None

    if response.status_code != 200:
        logger.warning("Introspection returned %d: %s", response.status_code, response.text)
        return None

    data = response.json()
    if data.get("active"):
        data["_raw_token"] = token
    _TOKEN_CACHE[token] = (data, now)

    if len(_TOKEN_CACHE) > 1000:
        expired = [
            k
            for k, (d, ts) in _TOKEN_CACHE.items()
            if now - ts > _CACHE_TTL or now >= d.get("exp", float("inf"))
        ]
        if not expired:
            # All entries are still fresh; evict the oldest 25 % to bound growth.
            sorted_keys = sorted(_TOKEN_CACHE, key=lambda k: _TOKEN_CACHE[k][1])
            expired = sorted_keys[: max(1, len(sorted_keys) // 4)]
        for k in expired:
            _TOKEN_CACHE.pop(k, None)

    return data if data.get("active") else None
