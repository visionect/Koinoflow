from django.conf import settings
from django.utils.functional import SimpleLazyObject


def get_task_backend():
    backend_name = getattr(settings, "TASK_BACKEND", "celery")
    if backend_name == "celery":
        from .celery_backend import CeleryBackend

        return CeleryBackend()
    if backend_name == "cloudtasks":
        from .cloud_tasks_backend import CloudTasksBackend

        return CloudTasksBackend()
    if backend_name == "sync":
        from .sync_backend import SyncBackend

        return SyncBackend()

    raise ValueError(f"Unsupported TASK_BACKEND: {backend_name}")


task_backend = SimpleLazyObject(get_task_backend)
