import hashlib
import hmac
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_WEBHOOK_EVENTS = ["page_created", "page_updated", "page_removed"]


async def register_webhook(cloud_id: str, access_token: str, callback_url: str) -> str:
    """Register Confluence page webhooks. Returns the webhook ID."""
    url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api/webhook"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "url": callback_url,
                "events": _WEBHOOK_EVENTS,
                "secret": settings.ATLASSIAN_WEBHOOK_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("id", ""))


async def deregister_webhook(cloud_id: str, access_token: str, webhook_id: str) -> None:
    """Best-effort webhook deregistration. Errors are swallowed."""
    if not webhook_id:
        return
    url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api/webhook/{webhook_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except Exception:
        logger.warning("Failed to deregister Confluence webhook %s", webhook_id, exc_info=True)


def verify_webhook_signature(payload: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 signature from Atlassian webhook request."""
    if not settings.ATLASSIAN_WEBHOOK_SECRET:
        logger.error("ATLASSIAN_WEBHOOK_SECRET is not configured; rejecting webhook")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = signature_header[len("sha256=") :]
    secret = settings.ATLASSIAN_WEBHOOK_SECRET.encode()
    computed = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected)
