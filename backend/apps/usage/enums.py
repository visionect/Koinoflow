from django.db import models


class ClientType(models.TextChoices):
    UNKNOWN = "Unknown", "Unknown"
    MCP = "MCP", "MCP (generic)"
    WEB = "Web", "Web"
    API = "REST API", "REST API"
