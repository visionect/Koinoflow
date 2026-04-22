"""
Two-phase extraction pipeline orchestrator.

Called from the Celery task. Manages ExtractionJob lifecycle (status
transitions, counters, error recording) and delegates to scoring.py and
extraction.py for the actual LLM work.
"""

import logging
from uuid import UUID

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_extraction(credential_id: UUID, job_id: UUID) -> None:
    """
    Execute the full two-phase extraction pipeline for a credential.

    Phase 1 — Scoring: lightweight model scores each unprocessed SyncedPage.
    Phase 2 — Extraction: flagship model extracts candidates from high-scoring pages.

    ExtractionJob status is updated throughout so the frontend can poll progress.
    Unrecoverable errors set job.status = 'failed' and re-raise so the Celery
    task can apply its retry policy.
    """
    from apps.connectors.capture.extraction import extract_candidates
    from apps.connectors.capture.scoring import score_pages
    from apps.connectors.models import ConnectorCredential, ExtractionJob, SyncedPage

    try:
        job = ExtractionJob.objects.get(id=job_id)
        credential = ConnectorCredential.objects.get(id=credential_id)
    except Exception:
        logger.error(
            "run_extraction: ExtractionJob %s or credential %s not found",
            job_id,
            credential_id,
        )
        return

    job.status = "running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])

    try:
        # Incremental: only pages where checksum != extraction_checksum
        pages = list(
            SyncedPage.objects.filter(credential=credential)
            .exclude(extraction_checksum=F("checksum"))
            .order_by("-last_synced_at")
        )

        logger.info(
            "ExtractionJob %s: found %d pages needing (re-)extraction",
            job_id,
            len(pages),
        )

        if not pages:
            job.status = "completed"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at", "updated_at"])
            return

        # Phase 1
        scored = score_pages(pages)

        job.pages_scored = len(pages)
        job.save(update_fields=["pages_scored", "updated_at"])

        logger.info(
            "ExtractionJob %s: %d/%d pages above scoring threshold",
            job_id,
            len(scored),
            len(pages),
        )

        # Phase 2
        created = extract_candidates(credential, scored) if scored else 0

        job.pages_extracted = len(scored)
        job.candidates_created = created
        job.status = "completed"
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "pages_extracted",
                "candidates_created",
                "status",
                "finished_at",
                "updated_at",
            ]
        )

        logger.info(
            "ExtractionJob %s completed: pages_scored=%d pages_extracted=%d candidates_created=%d",
            job_id,
            len(pages),
            len(scored),
            created,
        )

    except Exception as exc:
        logger.error("ExtractionJob %s failed", job_id, exc_info=True)
        job.status = "failed"
        job.error_message = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        raise
