"""
Custom token introspection endpoint that includes workspace context.

The MCP server calls this to validate tokens and learn which workspace/user
the token belongs to, avoiding the need to pass user tokens to Django's API.
"""

import base64
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from oauth2_provider.models import AccessToken

from apps.orgs.middleware import resolve_membership_for_user
from apps.orgs.models import CoreSlug, EntityType


def _secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _check_introspect_credentials(request):
    """Verify the calling resource server using configured credentials.

    Uses constant-time comparison on both the Basic and form-posted paths
    to avoid a timing oracle on the introspect client secret.
    """
    client_id = settings.MCP_INTROSPECT_CLIENT_ID
    client_secret = settings.MCP_INTROSPECT_CLIENT_SECRET

    if not client_id or not client_secret:
        return False

    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return False
        parts = decoded.split(":", 1)
        if (
            len(parts) == 2
            and _secrets_equal(parts[0], client_id)
            and _secrets_equal(parts[1], client_secret)
        ):
            return True

    req_id = request.POST.get("client_id", "")
    req_secret = request.POST.get("client_secret", "")
    if _secrets_equal(req_id, client_id) and _secrets_equal(req_secret, client_secret):
        return True

    return False


@csrf_exempt
@require_POST
def introspect_token(request):
    """
    RFC 7662 token introspection with workspace claims.

    POST /oauth/introspect/
    Body: token=<access_token>
    Auth: Basic <MCP_INTROSPECT_CLIENT_ID:MCP_INTROSPECT_CLIENT_SECRET>
    """
    if not _check_introspect_credentials(request):
        return JsonResponse({"error": "invalid_client"}, status=401)

    token_value = request.POST.get("token", "")
    if not token_value:
        return JsonResponse({"active": False})

    try:
        access_token = AccessToken.objects.select_related("user").get(token=token_value)
    except AccessToken.DoesNotExist:
        return JsonResponse({"active": False})

    if access_token.is_expired():
        return JsonResponse({"active": False})

    user = access_token.user
    response = {
        "active": True,
        "scope": access_token.scope,
        "client_id": access_token.application_id and str(access_token.application_id),
        "token_type": "Bearer",
        "exp": int(access_token.expires.timestamp()) if access_token.expires else None,
    }

    if user:
        response["username"] = user.email
        response["sub"] = str(user.id)

        requested_slug = (
            (access_token.extra_data or {}).get("workspace_slug")
            if hasattr(access_token, "extra_data")
            else None
        )
        membership = resolve_membership_for_user(user, requested_slug)
        if membership:
            ws = membership.workspace
            try:
                slug = CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=ws.id).slug
            except CoreSlug.DoesNotExist:
                slug = ""

            response["workspace_id"] = str(ws.id)
            response["workspace_slug"] = slug
            response["role"] = membership.role

    return JsonResponse(response)
