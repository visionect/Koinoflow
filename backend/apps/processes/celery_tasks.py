from config.celery import app


@app.task(name="staleness_check")
def staleness_check_task():
    from apps.processes.tasks import staleness_check

    staleness_check()
