import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.connectors.enums import (
    AutomationTier,
    CandidateStatus,
    CredentialStatus,
    ProviderChoices,
    SyncJobStatus,
    SyncJobType,
)


def _fernet() -> Fernet:
    return Fernet(settings.CONNECTOR_ENCRYPTION_KEY.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


class ConnectorCredential(BaseModel):
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="connector_credentials",
    )
    provider = models.CharField(max_length=50, choices=ProviderChoices.choices)
    cloud_id = models.CharField(max_length=100, blank=True)
    site_url = models.CharField(max_length=255, blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=CredentialStatus.choices,
        default=CredentialStatus.ACTIVE,
    )
    connected_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connected_credentials",
    )
    webhook_id = models.CharField(max_length=100, blank=True)
    allowed_spaces = models.JSONField(
        default=list,
        blank=True,
        help_text="Space keys to sync. Empty list means all spaces.",
    )

    class Meta:
        db_table = "connector_credential"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "provider"],
                condition=models.Q(status__in=["active", "expired", "error"]),
                name="uq_credential_workspace_provider_active",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace", "provider", "status"],
                name="idx_cred_ws_prov_status",
            ),
        ]

    def __str__(self):
        return f"{self.provider} @ {self.workspace.name} ({self.status})"

    def get_access_token(self) -> str:
        return decrypt_token(self.access_token)

    def get_refresh_token(self) -> str:
        return decrypt_token(self.refresh_token)

    def set_access_token(self, plaintext: str) -> None:
        self.access_token = encrypt_token(plaintext)

    def set_refresh_token(self, plaintext: str) -> None:
        self.refresh_token = encrypt_token(plaintext)


class SyncJob(BaseModel):
    credential = models.ForeignKey(
        ConnectorCredential,
        on_delete=models.CASCADE,
        related_name="sync_jobs",
    )
    job_type = models.CharField(max_length=20, choices=SyncJobType.choices)
    status = models.CharField(
        max_length=20,
        choices=SyncJobStatus.choices,
        default=SyncJobStatus.PENDING,
    )
    pages_scanned = models.PositiveIntegerField(default=0)
    pages_updated = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sync_job"
        indexes = [
            models.Index(
                fields=["credential", "-created_at"],
                name="idx_syncjob_credential_created",
            ),
        ]

    def __str__(self):
        return f"{self.credential} {self.job_type} ({self.status})"


class SyncedPage(BaseModel):
    credential = models.ForeignKey(
        ConnectorCredential,
        on_delete=models.CASCADE,
        related_name="synced_pages",
    )
    external_id = models.CharField(max_length=255)
    external_url = models.URLField(max_length=1000, blank=True)
    space_key = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=500)
    content_md = models.TextField()
    checksum = models.CharField(max_length=64)
    last_synced_at = models.DateTimeField()

    class Meta:
        db_table = "synced_page"
        constraints = [
            models.UniqueConstraint(
                fields=["credential", "external_id"],
                name="uq_synced_page_credential_external_id",
            )
        ]
        indexes = [
            models.Index(
                fields=["credential", "space_key"],
                name="idx_syncedpage_cred_space",
            ),
            models.Index(
                fields=["credential", "-last_synced_at"],
                name="idx_syncedpage_cred_synced",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.credential.provider})"

    last_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Most recent scoring-phase probability (0.0–1.0).",
    )
    extraction_checksum = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "Checksum at time of last AI extraction. "
            "Differs from checksum when page has changed since extraction."
        ),
    )

    @staticmethod
    def compute_checksum(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()


class ExtractionJob(BaseModel):
    credential = models.ForeignKey(
        ConnectorCredential,
        on_delete=models.CASCADE,
        related_name="extraction_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=SyncJobStatus.choices,
        default=SyncJobStatus.PENDING,
    )
    pages_scored = models.PositiveIntegerField(default=0)
    pages_extracted = models.PositiveIntegerField(default=0)
    candidates_created = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "extraction_job"
        indexes = [
            models.Index(
                fields=["credential", "-created_at"],
                name="idx_extjob_cred_created",
            ),
        ]

    def __str__(self):
        return f"ExtractionJob {self.credential} ({self.status})"


class CaptureCandidate(BaseModel):
    credential = models.ForeignKey(
        ConnectorCredential,
        on_delete=models.CASCADE,
        related_name="capture_candidates",
    )
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    content_md = models.TextField()
    frontmatter_yaml = models.TextField(blank=True)
    probability_score = models.FloatField(default=0.0)
    automation_tier = models.CharField(
        max_length=20,
        choices=AutomationTier.choices,
        default=AutomationTier.MANUAL_ONLY,
    )
    automation_reasoning = models.TextField(blank=True)
    integration_needs = models.JSONField(default=list)
    grounding_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="Web sources cited by the LLM during grounded extraction (uri, title).",
    )
    status = models.CharField(
        max_length=20,
        choices=CandidateStatus.choices,
        default=CandidateStatus.PENDING,
    )
    promoted_skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capture_candidates",
    )

    class Meta:
        db_table = "capture_candidate"
        indexes = [
            models.Index(
                fields=["credential", "status", "-created_at"],
                name="idx_cand_cred_status_created",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["credential", "slug"],
                condition=~models.Q(status="dismissed"),
                name="uq_candidate_credential_slug_active",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class CandidateSource(BaseModel):
    candidate = models.ForeignKey(
        CaptureCandidate,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    synced_page = models.ForeignKey(
        SyncedPage,
        on_delete=models.CASCADE,
        related_name="candidate_sources",
    )

    class Meta:
        db_table = "candidate_source"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "synced_page"],
                name="uq_candidate_source",
            ),
        ]

    def __str__(self):
        return f"{self.candidate} <- {self.synced_page}"
