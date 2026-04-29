from django.contrib.postgres.indexes import GinIndex
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from pgvector.django import HnswIndex, VectorField

from apps.common.models import BaseModel
from apps.skills.enums import StatusChoices, VisibilityChoices


class Skill(BaseModel):
    department = models.ForeignKey(
        "orgs.Department",
        on_delete=models.CASCADE,
        related_name="skills",
    )
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_skills",
    )
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.DRAFT,
    )
    visibility = models.CharField(
        max_length=20,
        choices=VisibilityChoices.choices,
        default=VisibilityChoices.DEPARTMENT,
    )
    shared_with = models.ManyToManyField(
        "orgs.Department",
        blank=True,
        related_name="shared_skills",
    )
    current_version = models.OneToOneField(
        "SkillVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    execution_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "skill"
        constraints = [
            models.UniqueConstraint(
                fields=["department", "slug"],
                name="uq_skill_dept_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["department", "status"],
                name="idx_skill_dept_status",
            ),
            models.Index(
                fields=["status", "-updated_at"],
                name="idx_skill_status_updated",
            ),
            models.Index(
                fields=["slug"],
                name="idx_skill_slug",
            ),
            models.Index(
                fields=["-updated_at"],
                name="idx_skill_updated_at",
            ),
            models.Index(
                fields=["execution_enabled"],
                name="idx_skill_exec_enabled",
                condition=Q(execution_enabled=True),
            ),
            GinIndex(
                fields=["title", "description"],
                name="idx_skill_search_trgm",
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            ),
            models.Index(
                fields=["visibility"],
                name="idx_skill_visibility",
                condition=Q(visibility__in=["team", "workspace"]),
            ),
        ]

    def __str__(self):
        return self.title


class SkillVersion(BaseModel):
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    authored_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="authored_versions",
    )
    version_number = models.PositiveIntegerField()
    content_md = models.TextField()
    frontmatter_yaml = models.TextField(blank=True, default="")
    change_summary = models.CharField(max_length=500, blank=True, default="")
    koinoflow_metadata = models.JSONField(default=dict, blank=True)
    reverted_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revert_children",
    )

    class Meta:
        db_table = "skill_version"
        constraints = [
            models.UniqueConstraint(
                fields=["skill", "version_number"],
                name="uq_version_skill_number",
            ),
        ]
        ordering = ["-version_number"]
        indexes = [
            models.Index(
                fields=["skill", "-version_number"],
                name="idx_version_latest",
            ),
        ]

    def __str__(self):
        return f"{self.skill.title} v{self.version_number}"


class SkillDiscoveryEmbedding(BaseModel):
    version = models.OneToOneField(
        SkillVersion,
        on_delete=models.CASCADE,
        related_name="discovery_embedding",
    )
    embedding = VectorField(dimensions=768)
    embedding_model = models.CharField(max_length=100)
    embedding_dimensions = models.PositiveSmallIntegerField(default=768)
    content_hash = models.CharField(max_length=64)
    indexed_text = models.TextField()
    indexed_at = models.DateTimeField()

    class Meta:
        db_table = "skill_discovery_embedding"
        indexes = [
            models.Index(
                fields=["embedding_model", "embedding_dimensions"],
                name="idx_skill_disc_model_dims",
            ),
            models.Index(fields=["content_hash"], name="idx_skill_disc_hash"),
            HnswIndex(
                name="idx_skill_disc_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.version} discovery embedding"


class SkillExecutionSpec(BaseModel):
    class RuntimeChoices(models.TextChoices):
        PYTHON = "python", "Python"

    class LatencyClassChoices(models.TextChoices):
        STANDARD = "standard", "Standard"
        INTERACTIVE = "interactive", "Interactive"
        ASYNC = "async", "Async"

    class NetworkPolicyChoices(models.TextChoices):
        EGRESS_ALLOWLIST = "egress_allowlist", "Egress allowlist"
        NONE = "none", "No network"

    class SecretScopeChoices(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        USER = "user", "User"
        PLATFORM = "platform", "Platform"

    skill = models.OneToOneField(
        Skill,
        on_delete=models.CASCADE,
        related_name="execution_spec",
    )
    version = models.ForeignKey(
        SkillVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execution_specs",
    )
    runtime = models.CharField(
        max_length=20,
        choices=RuntimeChoices.choices,
        default=RuntimeChoices.PYTHON,
    )
    latency_class = models.CharField(
        max_length=20,
        choices=LatencyClassChoices.choices,
        default=LatencyClassChoices.STANDARD,
    )
    entrypoint_path = models.CharField(max_length=500, default="run.py")
    input_schema = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    secrets_scope = models.CharField(
        max_length=50,
        choices=SecretScopeChoices.choices,
        default=SecretScopeChoices.WORKSPACE,
    )
    network_policy = models.CharField(
        max_length=50,
        choices=NetworkPolicyChoices.choices,
        default=NetworkPolicyChoices.EGRESS_ALLOWLIST,
    )
    allowed_egress = models.JSONField(default=list, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    memory_mb = models.PositiveIntegerField(default=512)
    max_output_bytes_inline = models.PositiveIntegerField(default=32768)
    max_runs_per_day = models.PositiveIntegerField(default=100)
    max_concurrent_runs = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "skill_execution_spec"
        indexes = [
            models.Index(fields=["skill"], name="idx_skill_exec_spec_skill"),
            models.Index(fields=["version"], name="idx_skill_exec_spec_version"),
        ]

    def __str__(self):
        return f"{self.skill.slug} execution spec"


class SkillExecutionRun(BaseModel):
    class StatusChoices(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        TIMEOUT = "timeout", "Timeout"
        CANCELLED = "cancelled", "Cancelled"

    class CallerTypeChoices(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent"
        API_KEY = "api_key", "API key"
        OAUTH = "oauth", "OAuth"

    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="skill_execution_runs",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="execution_runs",
    )
    version = models.ForeignKey(
        SkillVersion,
        on_delete=models.SET_NULL,
        null=True,
        related_name="execution_runs",
    )
    spec = models.ForeignKey(
        SkillExecutionSpec,
        on_delete=models.SET_NULL,
        null=True,
        related_name="runs",
    )
    department = models.ForeignKey(
        "orgs.Department",
        on_delete=models.SET_NULL,
        null=True,
        related_name="skill_execution_runs",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="skill_execution_runs",
    )
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="skill_execution_runs",
    )
    caller_type = models.CharField(max_length=20, choices=CallerTypeChoices.choices)
    status = models.CharField(
        max_length=30,
        choices=StatusChoices.choices,
        default=StatusChoices.QUEUED,
    )
    inputs = models.JSONField(default=dict, blank=True)
    input_hash = models.CharField(max_length=64)
    output = models.JSONField(null=True, blank=True)
    output_uri = models.CharField(max_length=1000, blank=True, default="")
    logs_uri = models.CharField(max_length=1000, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    external_job_name = models.CharField(max_length=255, blank=True, default="")
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_skill_execution_runs",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    secrets_fetched_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    resource_usage = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "skill_execution_run"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "-created_at"], name="idx_exec_run_ws_created"),
            models.Index(fields=["skill", "-created_at"], name="idx_exec_run_skill_created"),
            models.Index(fields=["status", "-created_at"], name="idx_exec_run_status_created"),
            models.Index(fields=["agent", "-created_at"], name="idx_exec_run_agent_created"),
            models.Index(fields=["user", "-created_at"], name="idx_exec_run_user_created"),
        ]

    def __str__(self):
        return f"{self.skill.slug} run {self.id} ({self.status})"


class SkillExecutionQuotaCounter(BaseModel):
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="skill_execution_quota_counters",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="execution_quota_counters",
    )
    day = models.DateField()
    run_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "skill_execution_quota_counter"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "skill", "day"],
                name="uq_exec_quota_ws_skill_day",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "day"], name="idx_exec_quota_ws_day"),
            models.Index(fields=["skill", "day"], name="idx_exec_quota_skill_day"),
        ]

    def __str__(self):
        return f"{self.skill.slug} executions on {self.day}: {self.run_count}"


ENV_NAME_RE = RegexValidator(
    regex=r"^[A-Z][A-Z0-9_]{0,63}$",
    message="Secret names must look like environment variable names (e.g. OPENAI_API_KEY).",
)


class SkillSecretDeclaration(BaseModel):
    class ScopeChoices(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        USER = "user", "User"
        PLATFORM = "platform", "Platform"

    spec = models.ForeignKey(
        SkillExecutionSpec,
        on_delete=models.CASCADE,
        related_name="secret_refs",
    )
    name = models.CharField(max_length=64, validators=[ENV_NAME_RE])
    scope = models.CharField(
        max_length=20,
        choices=ScopeChoices.choices,
        default=ScopeChoices.WORKSPACE,
    )
    required = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "skill_secret_declaration"
        constraints = [
            models.UniqueConstraint(
                fields=["spec", "name"],
                name="uq_skill_secret_decl_spec_name",
            )
        ]
        indexes = [
            models.Index(fields=["spec"], name="idx_secret_decl_spec"),
            models.Index(fields=["name"], name="idx_secret_decl_name"),
        ]

    def __str__(self):
        return f"{self.spec.skill.slug} secret {self.name}"


class SkillSecretValue(BaseModel):
    class ScopeChoices(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        USER = "user", "User"
        PLATFORM = "platform", "Platform"

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="secret_values",
    )
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="skill_secret_values",
    )
    name = models.CharField(max_length=64, validators=[ENV_NAME_RE])
    scope = models.CharField(
        max_length=20,
        choices=ScopeChoices.choices,
        default=ScopeChoices.WORKSPACE,
    )
    wrapped_dek = models.BinaryField(default=b"")
    ciphertext = models.BinaryField(default=b"")
    kms_key_version = models.CharField(max_length=255, blank=True, default="")
    last_set_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="set_skill_secret_values",
    )

    class Meta:
        db_table = "skill_secret_value"
        constraints = [
            models.UniqueConstraint(
                fields=["skill", "workspace", "name", "scope"],
                name="uq_skill_secret_value_scope",
            )
        ]
        indexes = [
            models.Index(fields=["skill", "workspace"], name="idx_secret_value_skill_ws"),
            models.Index(fields=["name"], name="idx_secret_value_name"),
        ]

    def __str__(self):
        return f"{self.skill.slug}/{self.workspace_id}/{self.name}"


class SkillSecretAccessLog(BaseModel):
    run = models.ForeignKey(
        SkillExecutionRun,
        on_delete=models.CASCADE,
        related_name="secret_access_logs",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="secret_access_logs",
    )
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="skill_secret_access_logs",
    )
    name = models.CharField(max_length=64, validators=[ENV_NAME_RE])
    granted = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "skill_secret_access_log"
        indexes = [
            models.Index(fields=["run"], name="idx_secret_log_run"),
            models.Index(fields=["workspace", "-created_at"], name="idx_secret_log_ws_created"),
            models.Index(fields=["skill", "-created_at"], name="idx_secret_log_skill_created"),
        ]

    def __str__(self):
        status = "granted" if self.granted else "denied"
        return f"{self.run_id}/{self.name}/{status}"


class FileTypeChoices(models.TextChoices):
    PYTHON = "python"
    MARKDOWN = "markdown"
    HTML = "html"
    YAML = "yaml"
    JSON = "json"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    SHELL = "shell"
    IMAGE = "image"
    PDF = "pdf"
    BINARY = "binary"
    TEXT = "text"
    OTHER = "other"


class VersionFile(BaseModel):
    version = models.ForeignKey(
        SkillVersion,
        on_delete=models.CASCADE,
        related_name="files",
    )
    path = models.CharField(max_length=500)
    content = models.TextField(default="")
    content_bytes = models.BinaryField(default=b"", blank=True)
    file_type = models.CharField(
        max_length=50,
        choices=FileTypeChoices.choices,
        default=FileTypeChoices.TEXT,
    )
    mime_type = models.CharField(max_length=100, blank=True, default="text/plain")
    encoding = models.CharField(max_length=20, blank=True, default="utf-8")
    sha256 = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "version_file"
        constraints = [
            models.UniqueConstraint(
                fields=["version", "path"],
                name="uq_version_file_path",
            ),
        ]
        indexes = []

    def __str__(self):
        return f"{self.version} — {self.path}"
