from config.celery import app


@app.task(name="capture_extract_processes", bind=True, max_retries=2)
def capture_extract_processes_task(self, credential_id: str, job_id: str) -> None:
    from uuid import UUID

    from apps.connectors.capture.pipeline import run_extraction

    try:
        run_extraction(UUID(credential_id), UUID(job_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@app.task(name="confluence_full_sync", bind=True, max_retries=3)
def confluence_full_sync_task(self, credential_id: str, job_id: str) -> None:
    from uuid import UUID

    from apps.connectors.tasks import run_full_sync

    try:
        run_full_sync(UUID(credential_id), UUID(job_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@app.task(name="confluence_sync_page", bind=True, max_retries=3)
def confluence_sync_page_task(self, credential_id: str, page_id: str) -> None:
    from uuid import UUID

    from apps.connectors.tasks import run_sync_page

    try:
        run_sync_page(UUID(credential_id), page_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@app.task(name="confluence_token_refresh_check")
def confluence_token_refresh_check_task() -> None:
    from apps.connectors.tasks import run_token_refresh_check

    run_token_refresh_check()
