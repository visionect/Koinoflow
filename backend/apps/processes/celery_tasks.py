from config.celery import app


@app.task(name="staleness_check")
def staleness_check_task():
    from apps.processes.tasks import staleness_check

    staleness_check()


@app.task(name="index_process_discovery_embedding")
def index_process_discovery_embedding_task(version_id: str, force: bool = False):
    from apps.processes.discovery import index_process_version

    indexed = index_process_version(version_id, force=force)
    return str(indexed.id) if indexed else None
