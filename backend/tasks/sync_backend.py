from .base import TaskBackend
from .registry import TASK_REGISTRY


class SyncBackend(TaskBackend):
    def enqueue(self, task_name: str, **kwargs) -> None:
        func = TASK_REGISTRY[task_name]
        func(**kwargs)
