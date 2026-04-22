import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import BaseModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "user"

    def __str__(self):
        return self.email


class ScopeType(models.TextChoices):
    WORKSPACE = "workspace"
    TEAM = "team"
    DEPARTMENT = "department"


class McpConnectionScope(BaseModel):
    """
    Voluntary scope narrowing for an MCP OAuth connection.

    Can only restrict visibility below the user's role-level access, never widen it.
    When scope_type is 'workspace', no narrowing is applied.
    """

    application = models.OneToOneField(
        "oauth2_provider.Application",
        on_delete=models.CASCADE,
        related_name="mcp_scope",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mcp_scopes",
    )
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="mcp_connection_scopes",
    )
    scope_type = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.WORKSPACE,
    )
    team = models.ForeignKey(
        "orgs.Team",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="mcp_connection_scopes",
    )
    departments = models.ManyToManyField(
        "orgs.Department",
        blank=True,
        related_name="mcp_connection_scopes",
    )

    class Meta:
        db_table = "mcp_connection_scope"
        constraints = [
            models.UniqueConstraint(
                fields=["application", "user", "workspace"],
                name="uq_mcp_scope_app_user_ws",
            ),
        ]

    def __str__(self):
        if self.scope_type == ScopeType.TEAM:
            return f"MCP scope: team={self.team_id}"
        if self.scope_type == ScopeType.DEPARTMENT:
            return "MCP scope: departments"
        return "MCP scope: workspace"
