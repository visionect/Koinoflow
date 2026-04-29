import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tasks import task_backend
from tasks.registry import TASK_REGISTRY

logger = logging.getLogger(__name__)

ALLOWED_SCHEDULED_TASKS = {
    "staleness_check",
    "confluence_token_refresh_check",
}


@require_POST
def run_scheduled_task(request: HttpRequest, task_name: str):
    """Endpoint for Cloud Scheduler — validates a static Bearer token."""
    token = getattr(settings, "INTERNAL_TASK_TOKEN", "")
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {token}" if token else ""

    if not token or not hmac.compare_digest(auth_header, expected):
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    if task_name not in ALLOWED_SCHEDULED_TASKS:
        return JsonResponse({"detail": "Task not allowed"}, status=404)

    task_backend.enqueue(task_name)
    return JsonResponse({"status": "queued", "task": task_name}, status=202)


@csrf_exempt
@require_POST
def run_task(request: HttpRequest):
    """Endpoint for Cloud Tasks — validates OIDC token or Bearer token."""
    if not _verify_cloud_tasks_auth(request):
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    task_name = body.get("task_name", "")
    kwargs = body.get("kwargs", {})

    if task_name not in TASK_REGISTRY:
        return JsonResponse({"detail": f"Unknown task: {task_name}"}, status=404)

    try:
        TASK_REGISTRY[task_name](**kwargs)
    except Exception:
        logger.exception("Task %s failed", task_name)
        return JsonResponse({"detail": "Task execution failed"}, status=500)

    return JsonResponse({"status": "ok", "task": task_name})


def _verify_cloud_tasks_auth(request: HttpRequest) -> bool:
    """Accept either OIDC token (Cloud Tasks) or Bearer token (scheduler/tests)."""
    auth_header = request.headers.get("Authorization", "")

    # Cloud Tasks sends an OIDC Bearer token signed by Google
    if auth_header.startswith("Bearer ") and _is_oidc_token(auth_header[7:]):
        return _verify_oidc_token(auth_header[7:])

    # Fall back to static internal token (for Cloud Scheduler / curl tests)
    token = getattr(settings, "INTERNAL_TASK_TOKEN", "")
    if token and auth_header:
        expected = f"Bearer {token}"
        return hmac.compare_digest(auth_header, expected)

    return False


def _is_oidc_token(token: str) -> bool:
    """Quick heuristic: OIDC JWTs have 3 dot-separated segments."""
    return token.count(".") == 2


def _verify_oidc_token(token: str) -> bool:
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claim = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=getattr(settings, "CLOUD_TASKS_SERVICE_URL", None),
        )
        expected_sa = getattr(settings, "CLOUD_TASKS_SERVICE_ACCOUNT", "")
        if expected_sa and claim.get("email") != expected_sa:
            raw = claim.get("email", "")
            local, _, domain = raw.partition("@")
            masked = f"{raw[0]}***@{domain}" if domain else "***"
            logger.warning("OIDC email mismatch: %s", masked)
            return False
        return True
    except Exception:
        logger.warning("OIDC token verification failed", exc_info=True)
        return False
