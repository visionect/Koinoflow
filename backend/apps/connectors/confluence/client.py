import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_REFRESH_LOCK_TTL = 60  # seconds


class ConfluenceAuthError(Exception):
    pass


class ConfluenceRateLimitError(Exception):
    pass


class ConfluenceClient:
    def __init__(self, credential) -> None:
        # Import here to avoid circular import at module load
        self._credential = credential
        self._base = f"https://api.atlassian.com/ex/confluence/{credential.cloud_id}/wiki/api/v2"
        self._http = httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── Public API ──────────────────────────────────────────────────────

    async def get_spaces(self) -> AsyncIterator[dict]:
        async for item in self._paginate("/spaces"):
            yield item

    async def get_pages_in_space(self, space_id: str) -> AsyncIterator[dict]:
        async for item in self._paginate(f"/spaces/{space_id}/pages"):
            yield item

    async def get_page(self, page_id: str) -> dict[str, Any]:
        return await self._get(f"/pages/{page_id}", **{"body-format": "storage"})

    # ── Token refresh ────────────────────────────────────────────────────

    async def refresh_if_needed(self) -> None:
        cred = self._credential
        # No refresh token — nothing to do, use token until it expires
        if not cred.refresh_token:
            return

        buffer = timedelta(minutes=5)
        if cred.token_expires_at and cred.token_expires_at - buffer > timezone.now():
            return

        lock_key = f"confluence_token_refresh:{cred.id}"
        if cache.add(lock_key, "1", _REFRESH_LOCK_TTL):
            try:
                await self._do_refresh()
            finally:
                cache.delete(lock_key)
        else:
            # Another worker is refreshing; wait and reload
            await asyncio.sleep(2)
            await sync_to_async(cred.refresh_from_db)()

    async def _do_refresh(self) -> None:
        from apps.connectors.enums import CredentialStatus

        cred = self._credential
        resp = await self._http.post(
            _ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": settings.ATLASSIAN_CLIENT_ID,
                "client_secret": settings.ATLASSIAN_CLIENT_SECRET,
                "refresh_token": cred.get_refresh_token(),
            },
        )
        if resp.status_code != 200:
            cred.status = CredentialStatus.EXPIRED
            await sync_to_async(cred.save)(update_fields=["status", "updated_at"])
            raise ConfluenceAuthError(f"Token refresh failed: {resp.status_code}")

        data = resp.json()
        expires_in = data.get("expires_in", 3600)
        cred.set_access_token(data["access_token"])
        if "refresh_token" in data:
            cred.set_refresh_token(data["refresh_token"])
        cred.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        cred.status = CredentialStatus.ACTIVE
        await sync_to_async(cred.save)(
            update_fields=[
                "access_token",
                "refresh_token",
                "token_expires_at",
                "status",
                "updated_at",
            ]
        )

    # ── Internal ─────────────────────────────────────────────────────────

    async def _paginate(self, path: str, **params) -> AsyncIterator[dict]:
        url: str | None = self._base + path
        while url:
            data = await self._get_url(url, **params)
            for item in data.get("results", []):
                yield item
            next_link = data.get("_links", {}).get("next")
            if next_link:
                # next_link is a relative path like /wiki/api/v2/...
                base_site = f"https://api.atlassian.com/ex/confluence/{self._credential.cloud_id}"
                url = base_site + next_link
            else:
                url = None

    async def _get(self, path: str, **params) -> dict[str, Any]:
        return await self._get_url(self._base + path, **params)

    async def _get_url(self, url: str, **params) -> dict[str, Any]:
        await self.refresh_if_needed()
        token = self._credential.get_access_token()

        backoff = 1
        refreshed_on_401 = False
        for attempt in range(5):
            resp = await self._http.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params or None,
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                logger.warning(
                    "401 from Confluence (attempt %d, token_len=%d, expires_at=%s, url=%s)",
                    attempt,
                    len(token) if token else 0,
                    self._credential.token_expires_at,
                    url,
                )
                if not refreshed_on_401 and self._credential.refresh_token:
                    refreshed_on_401 = True
                    try:
                        await self._do_refresh()
                        token = self._credential.get_access_token()
                        continue
                    except ConfluenceAuthError:
                        pass
                from apps.connectors.enums import CredentialStatus

                self._credential.status = CredentialStatus.EXPIRED
                await sync_to_async(self._credential.save)(update_fields=["status", "updated_at"])
                raise ConfluenceAuthError("Access token rejected (401)")
            if resp.status_code == 429:
                if attempt == 4:
                    raise ConfluenceRateLimitError("Rate limit sustained after retries")
                retry_after = int(resp.headers.get("Retry-After", backoff))
                await asyncio.sleep(retry_after)
                backoff = min(backoff * 2, 32)
                continue
            resp.raise_for_status()

        raise ConfluenceRateLimitError("Exceeded retry budget")


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "client_id": settings.ATLASSIAN_CLIENT_ID,
                "client_secret": settings.ATLASSIAN_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "Token exchange response: token_type=%s, expires_in=%s, scope=%s, has_refresh=%s",
            data.get("token_type"),
            data.get("expires_in"),
            data.get("scope"),
            bool(data.get("refresh_token")),
        )
        return data


async def get_accessible_resources(access_token: str) -> list[dict[str, Any]]:
    """Fetch the list of Atlassian cloud sites the token has access to."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        for resource in data:
            logger.info(
                "Accessible resource: id=%s, url=%s, scopes=%s",
                resource.get("id"),
                resource.get("url"),
                resource.get("scopes", []),
            )
        return data
