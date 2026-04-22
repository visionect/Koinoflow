from abc import ABC, abstractmethod


class TaskBackend(ABC):
    @abstractmethod
    def enqueue(self, task_name: str, **kwargs) -> None: ...
