from config.celery import app


@app.task(name="staleness_check")
def staleness_check_task():
    from apps.skills.tasks import staleness_check

    staleness_check()


@app.task(name="index_skill_discovery_embedding")
def index_skill_discovery_embedding_task(version_id: str, force: bool = False):
    from apps.skills.discovery import index_skill_version

    indexed = index_skill_version(version_id, force=force)
    return str(indexed.id) if indexed else None
