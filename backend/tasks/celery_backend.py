from config.celery import app as celery_app

from .base import TaskBackend


class CeleryBackend(TaskBackend):
    def enqueue(self, task_name: str, **kwargs) -> None:
        celery_app.send_task(task_name, kwargs=kwargs)
