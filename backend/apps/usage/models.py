import uuid

from django.db import models

from apps.usage.enums import ClientType


class UsageEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process = models.ForeignKey(
        "processes.Process",
        on_delete=models.CASCADE,
        related_name="usage_events",
    )
    version_number = models.PositiveIntegerField()
    client_id = models.CharField(max_length=255, default="unknown")
    client_type = models.CharField(max_length=100, default=ClientType.UNKNOWN)
    tool_name = models.CharField(max_length=100, blank=True, default="")
    called_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usage_event"
        ordering = ["-called_at"]
        indexes = [
            models.Index(fields=["process", "-called_at"]),
            models.Index(fields=["called_at"]),
            models.Index(
                fields=["process", "client_type"],
                name="idx_usage_process_client_type",
            ),
        ]

    def __str__(self):
        return f"{self.process.title} called by {self.client_type} at {self.called_at}"
