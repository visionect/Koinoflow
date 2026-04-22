from config.celery import app


@app.task(name="log_usage_event")
def log_usage_event_task(**kwargs):
    from apps.usage.tasks import log_usage_event

    log_usage_event(**kwargs)
