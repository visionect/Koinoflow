from django.db import models


class ProviderChoices(models.TextChoices):
    CONFLUENCE = "confluence", "Confluence"


class CredentialStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    ERROR = "error", "Error"
    DISCONNECTED = "disconnected", "Disconnected"


class SyncJobType(models.TextChoices):
    FULL = "full", "Full"
    INCREMENTAL = "incremental", "Incremental"


class SyncJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class AutomationTier(models.TextChoices):
    READY = "ready", "Ready to automate"
    NEEDS_INTEGRATION = "needs_integration", "Needs integration"
    MANUAL_ONLY = "manual_only", "Manual only"


class CandidateStatus(models.TextChoices):
    PENDING = "pending", "Pending review"
    PROMOTED = "promoted", "Promoted to process"
    DISMISSED = "dismissed", "Dismissed"
