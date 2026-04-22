from collections.abc import Callable

TASK_REGISTRY: dict[str, Callable] = {}


def register_task(name: str):
    def decorator(func):
        TASK_REGISTRY[name] = func
        return func

    return decorator
