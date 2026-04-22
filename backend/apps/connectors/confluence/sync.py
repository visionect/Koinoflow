import logging
from uuid import UUID

from django.utils import timezone

from apps.connectors.confluence.client import ConfluenceClient
from apps.connectors.confluence.parser import parse_storage_to_markdown
from apps.connectors.enums import SyncJobStatus
from apps.connectors.models import ConnectorCredential, SyncedPage, SyncJob

logger = logging.getLogger(__name__)


async def full_sync(credential_id: UUID, job_id: UUID) -> None:
    credential = await _aget_credential(credential_id)
    job = await _aget_job(job_id)

    job.status = SyncJobStatus.RUNNING
    job.started_at = timezone.now()
    await _asave_job(job, ["status", "started_at", "updated_at"])

    client = ConfluenceClient(credential)
    allowed = set(credential.allowed_spaces) if credential.allowed_spaces else None
    try:
        async with _Closing(client):
            async for space in client.get_spaces():
                space_id = str(space["id"])
                space_key = space.get("key", "")
                if allowed and space_key not in allowed:
                    continue
                async for page_stub in client.get_pages_in_space(space_id):
                    job.pages_scanned += 1
                    updated = await _sync_page_data(
                        client, credential, str(page_stub["id"]), space_key
                    )
                    if updated:
                        job.pages_updated += 1

        job.status = SyncJobStatus.COMPLETED
        job.finished_at = timezone.now()
        await _asave_job(
            job, ["status", "pages_scanned", "pages_updated", "finished_at", "updated_at"]
        )

    except Exception as exc:
        logger.exception("full_sync failed for credential %s", credential_id)
        job.status = SyncJobStatus.FAILED
        job.error_message = f"{type(exc).__name__}: sync failed"
        job.finished_at = timezone.now()
        await _asave_job(job, ["status", "error_message", "finished_at", "updated_at"])
        raise


async def sync_single_page(credential_id: UUID, page_id: str) -> None:
    credential = await _aget_credential(credential_id)
    client = ConfluenceClient(credential)
    async with _Closing(client):
        await _sync_page_data(client, credential, page_id, space_key="")


async def _sync_page_data(
    client: ConfluenceClient,
    credential: ConnectorCredential,
    page_id: str,
    space_key: str,
) -> bool:
    """Fetch one page, parse it, upsert SyncedPage. Returns True if content changed."""
    from asgiref.sync import sync_to_async

    page = await client.get_page(page_id)
    body = page.get("body", {}).get("storage", {}).get("value", "")
    checksum = SyncedPage.compute_checksum(body)

    get_page = sync_to_async(
        lambda: SyncedPage.objects.filter(credential=credential, external_id=page_id).first()
    )
    existing = await get_page()

    if existing and existing.checksum == checksum:
        return False

    content_md = parse_storage_to_markdown(body)
    title = page.get("title", "")
    site = credential.site_url.rstrip("/")
    external_url = f"{site}/wiki/spaces/{space_key}/pages/{page_id}"

    save_page = sync_to_async(SyncedPage.objects.update_or_create)
    await save_page(
        credential=credential,
        external_id=page_id,
        defaults={
            "title": title,
            "content_md": content_md,
            "checksum": checksum,
            "external_url": external_url,
            "space_key": space_key or (existing.space_key if existing else ""),
            "last_synced_at": timezone.now(),
        },
    )
    return True


# ── Async DB helpers (Django ORM is sync by default) ─────────────────────

from asgiref.sync import sync_to_async as _s2a  # noqa: E402


async def _aget_credential(credential_id: UUID) -> ConnectorCredential:
    get = _s2a(ConnectorCredential.objects.get)
    return await get(id=credential_id)


async def _aget_job(job_id: UUID) -> SyncJob:
    get = _s2a(SyncJob.objects.get)
    return await get(id=job_id)


async def _asave_job(job: SyncJob, fields: list[str]) -> None:
    save = _s2a(job.save)
    await save(update_fields=fields)


class _Closing:
    def __init__(self, client: ConfluenceClient) -> None:
        self._client = client

    async def __aenter__(self) -> ConfluenceClient:
        return self._client

    async def __aexit__(self, *_) -> None:
        await self._client.aclose()
