"""
OAuth 2.1 endpoints that django-oauth-toolkit does not provide out of the box:
- RFC 8414  Authorization Server Metadata
- RFC 7591  Dynamic Client Registration (simplified)
- Custom AuthorizationView with branded consent screen

Dynamic Client Registration hardening notes:
- Client IP is derived from the left-most ``X-Forwarded-For`` entry because
  the Google HTTPS LB prepends the real client IP there; ``REMOTE_ADDR`` is
  the LB's private front-end IP and yields a single shared rate-limit key
  for the whole internet.
- ``redirect_uris`` must be validated *before* the Application is persisted:
  DOT's ``ALLOWED_REDIRECT_URI_SCHEMES`` includes bare ``http`` so we enforce
  the RFC 8252 "http is only for loopback" rule ourselves. Other schemes
  (``cursor://``, ``vscode://``) are accepted for native app callbacks.
- ``client_name`` is sanitised to block spoofing known first-party clients
  ("Claude Desktop", "Cursor", …) on the branded consent screen.
"""

import ipaddress
import json
import logging
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from oauth2_provider.models import Application
from oauth2_provider.views import AuthorizationView

logger = logging.getLogger(__name__)


_DCR_RATE_LIMIT_PER_IP_PER_HOUR = 10
_DCR_GLOBAL_RATE_LIMIT_PER_HOUR = 200
_ALLOWED_URI_SCHEMES = {"https", "cursor", "vscode"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_PROTECTED_CLIENT_NAMES = {
    "claude desktop",
    "claude",
    "cursor",
    "vscode",
    "mcp inspector",
    "koinoflow",
    "koinoflow-internal",
}


class KoinoflowAuthorizationView(AuthorizationView):
    """
    Override DOT's AuthorizationView to use a branded consent screen.

    We do NOT intercept the post-authorization 302 redirect — OAuth clients
    (MCP tools like Claude, Cursor, etc.) need the immediate redirect back to
    their callback URL so they can exchange the code for a token.  Rendering
    an interstitial HTML page breaks that expectation and leaves the user
    staring at the client's own callback page instead.
    """

    template_name = "oauth2_provider/authorize.html"


def _base_url():
    return settings.APP_BASE_URL.rstrip("/")


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR", "unknown")


def _validate_redirect_uri(uri: str) -> str | None:
    """Return an error description or None if the URI is acceptable."""
    if not isinstance(uri, str) or not uri:
        return "redirect_uri must be a non-empty string"
    if len(uri) > 2048:
        return "redirect_uri is too long"
    if "#" in uri:
        return "redirect_uri must not contain a fragment"

    try:
        parts = urlsplit(uri)
    except ValueError:
        return "redirect_uri is not a valid URI"

    scheme = (parts.scheme or "").lower()
    if scheme == "http":
        host = (parts.hostname or "").lower()
        if host not in _LOOPBACK_HOSTS:
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                return "http redirect_uris are only allowed for loopback addresses"
            if not ip.is_loopback:
                return "http redirect_uris are only allowed for loopback addresses"
        return None

    if scheme in _ALLOWED_URI_SCHEMES:
        if scheme == "https" and not (parts.hostname or ""):
            return "https redirect_uri must include a host"
        return None

    return f"redirect_uri scheme '{scheme}' is not allowed"


def _sanitise_client_name(raw: str | None) -> str:
    name = (raw or "MCP Client").strip()
    if not name:
        name = "MCP Client"
    if len(name) > 120:
        name = name[:120]
    if name.lower() in _PROTECTED_CLIENT_NAMES:
        name = f"{name} (unverified)"
    return name


@require_GET
def authorization_server_metadata(request):
    """RFC 8414 — /.well-known/oauth-authorization-server"""
    base = _base_url()
    scopes = settings.OAUTH2_PROVIDER.get("SCOPES", {})

    metadata = {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize/",
        "token_endpoint": f"{base}/oauth/token/",
        "revocation_endpoint": f"{base}/oauth/revoke_token/",
        "introspection_endpoint": f"{base}/oauth/introspect/",
        "registration_endpoint": f"{base}/oauth/register",
        "scopes_supported": list(scopes.keys()),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none",
        ],
        "code_challenge_methods_supported": ["S256"],
        "service_documentation": f"{base}/api/docs",
    }

    response = JsonResponse(metadata)
    response["Access-Control-Allow-Origin"] = "*"
    response["Cache-Control"] = "public, max-age=3600"
    return response


def _check_dcr_rate_limit(request):
    """Cache-based rate limit: 10 registrations per real client IP per hour.

    Also enforces a soft global ceiling to blunt distributed brute-force
    registrations without a WAF in front.
    """
    ip = _client_ip(request)
    per_ip_key = f"dcr_ratelimit:v2:{ip}"
    per_ip = cache.get(per_ip_key, 0)
    if per_ip >= _DCR_RATE_LIMIT_PER_IP_PER_HOUR:
        return JsonResponse(
            {"error": "rate_limit_exceeded", "error_description": "Too many registrations"},
            status=429,
        )

    global_key = "dcr_ratelimit:v2:_global"
    global_count = cache.get(global_key, 0)
    if global_count >= _DCR_GLOBAL_RATE_LIMIT_PER_HOUR:
        return JsonResponse(
            {
                "error": "rate_limit_exceeded",
                "error_description": "Registration temporarily unavailable",
            },
            status=429,
        )

    cache.set(per_ip_key, per_ip + 1, timeout=3600)
    cache.set(global_key, global_count + 1, timeout=3600)
    return None


@csrf_exempt
@require_POST
def dynamic_client_registration(request):
    """
    RFC 7591 — Dynamic Client Registration (simplified).

    MCP clients (Claude Desktop, Cursor, etc.) POST metadata to register
    and receive a client_id + client_secret they can use for the OAuth flow.
    """
    rate_limit_response = _check_dcr_rate_limit(request)
    if rate_limit_response:
        return rate_limit_response

    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "invalid_client_metadata", "error_description": "Invalid JSON"},
            status=400,
        )
    if not isinstance(body, dict):
        return JsonResponse(
            {"error": "invalid_client_metadata", "error_description": "Body must be an object"},
            status=400,
        )

    client_name = _sanitise_client_name(body.get("client_name"))
    redirect_uris = body.get("redirect_uris", [])
    grant_types = body.get("grant_types", ["authorization_code"])
    response_types = body.get("response_types", ["code"])
    token_endpoint_auth_method = body.get("token_endpoint_auth_method", "client_secret_post")
    scope = body.get("scope", "")

    if not redirect_uris:
        return JsonResponse(
            {
                "error": "invalid_client_metadata",
                "error_description": "redirect_uris is required",
            },
            status=400,
        )
    if not isinstance(redirect_uris, list):
        redirect_uris = [redirect_uris]
    if len(redirect_uris) > 10:
        return JsonResponse(
            {
                "error": "invalid_client_metadata",
                "error_description": "too many redirect_uris (max 10)",
            },
            status=400,
        )

    seen: set[str] = set()
    normalised: list[str] = []
    for uri in redirect_uris:
        err = _validate_redirect_uri(uri)
        if err:
            return JsonResponse(
                {"error": "invalid_redirect_uri", "error_description": err},
                status=400,
            )
        if uri in seen:
            continue
        seen.add(uri)
        normalised.append(uri)
    redirect_uris = normalised

    if token_endpoint_auth_method not in {
        "client_secret_post",
        "client_secret_basic",
        "none",
    }:
        return JsonResponse(
            {
                "error": "invalid_client_metadata",
                "error_description": "unsupported token_endpoint_auth_method",
            },
            status=400,
        )

    is_public = token_endpoint_auth_method == "none"
    client_secret = None if is_public else secrets.token_urlsafe(48)

    app = Application(
        name=client_name,
        client_type=(Application.CLIENT_PUBLIC if is_public else Application.CLIENT_CONFIDENTIAL),
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=" ".join(redirect_uris),
    )

    if client_secret:
        app.client_secret = client_secret

    app.save()

    logger.info(
        "dcr_register client_id=%s name=%r public=%s ip=%s redirect_count=%d",
        app.client_id,
        client_name,
        is_public,
        _client_ip(request),
        len(redirect_uris),
    )

    response_data = {
        "client_id": app.client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": token_endpoint_auth_method,
        "scope": scope or " ".join(settings.OAUTH2_PROVIDER.get("DEFAULT_SCOPES", [])),
    }

    if client_secret:
        response_data["client_secret"] = client_secret

    response = JsonResponse(response_data, status=201)
    response["Cache-Control"] = "no-store"
    return response
