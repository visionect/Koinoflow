from uuid import UUID

from asgiref.sync import async_to_sync

from tasks.registry import register_task


def run_full_sync(credential_id: UUID, job_id: UUID) -> None:
    from apps.connectors.confluence.sync import full_sync

    async_to_sync(full_sync)(credential_id, job_id)


def run_sync_page(credential_id: UUID, page_id: str) -> None:
    from apps.connectors.confluence.sync import sync_single_page

    async_to_sync(sync_single_page)(credential_id, page_id)


def run_token_refresh_check() -> None:
    """Pre-emptively refresh tokens expiring within 10 minutes."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.connectors.confluence.client import ConfluenceClient
    from apps.connectors.enums import CredentialStatus, ProviderChoices
    from apps.connectors.models import ConnectorCredential

    threshold = timezone.now() + timedelta(minutes=10)
    expiring = ConnectorCredential.objects.filter(
        provider=ProviderChoices.CONFLUENCE,
        status=CredentialStatus.ACTIVE,
        token_expires_at__lt=threshold,
    )
    for credential in expiring:
        try:
            client = ConfluenceClient(credential)
            async_to_sync(client.refresh_if_needed)()
            async_to_sync(client.aclose)()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Token refresh failed for credential %s", credential.id, exc_info=True
            )


@register_task("confluence_full_sync")
def confluence_full_sync_registered(credential_id: str, job_id: str) -> None:
    run_full_sync(UUID(credential_id), UUID(job_id))


@register_task("confluence_sync_page")
def confluence_sync_page_registered(credential_id: str, page_id: str) -> None:
    run_sync_page(UUID(credential_id), page_id)


@register_task("confluence_token_refresh_check")
def confluence_token_refresh_check_registered() -> None:
    run_token_refresh_check()


@register_task("capture_extract_processes")
def capture_extract_processes_registered(credential_id: str, job_id: str) -> None:
    from apps.connectors.capture.pipeline import run_extraction

    run_extraction(UUID(credential_id), UUID(job_id))
