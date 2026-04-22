import json
import logging

from django.conf import settings
from google.cloud import tasks_v2

from .base import TaskBackend

logger = logging.getLogger(__name__)


class CloudTasksBackend(TaskBackend):
    def __init__(self):
        self._client = tasks_v2.CloudTasksClient()
        self._parent = self._client.queue_path(
            settings.CLOUD_TASKS_PROJECT,
            settings.CLOUD_TASKS_LOCATION,
            settings.CLOUD_TASKS_QUEUE,
        )

    def enqueue(self, task_name: str, **kwargs) -> None:
        payload = json.dumps({"task_name": task_name, "kwargs": kwargs}).encode()
        url = f"{settings.CLOUD_TASKS_SERVICE_URL}/api/internal/tasks/run"

        task: dict = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": payload,
            }
        }

        sa_email = getattr(settings, "CLOUD_TASKS_SERVICE_ACCOUNT", "")
        if sa_email:
            task["http_request"]["oidc_token"] = {
                "service_account_email": sa_email,
                "audience": settings.CLOUD_TASKS_SERVICE_URL,
            }

        self._client.create_task(parent=self._parent, task=task)
        logger.info("Enqueued Cloud Task: %s", task_name)
