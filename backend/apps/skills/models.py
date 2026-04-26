from django.contrib.postgres.indexes import GinIndex
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
