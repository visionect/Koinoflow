import hashlib
import secrets

from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.common.models import BaseModel
from apps.orgs.enums import EntityType, InvitationStatus, RoleChoices


class Workspace(BaseModel):
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "workspace"

    def __str__(self):
        return self.name


class Membership(BaseModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.MEMBER,
    )
    team = models.ForeignKey(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="team_memberships",
    )
    departments = models.ManyToManyField(
        "Department",
        blank=True,
        related_name="department_memberships",
    )

    class Meta:
        db_table = "membership"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "workspace"],
                name="uq_membership_user_workspace",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "role"], name="idx_membership_ws_role"),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.workspace.name} ({self.role})"


class Team(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "team"
        indexes = [
            models.Index(fields=["workspace", "name"], name="idx_team_ws_name"),
        ]

    def __str__(self):
        return f"{self.workspace.name} / {self.name}"


class Department(BaseModel):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_departments",
    )

    class Meta:
        db_table = "department"
        indexes = [
            models.Index(fields=["team", "name"], name="idx_department_team_name"),
        ]

    def __str__(self):
        return f"{self.team.name} / {self.name}"


# ── CoreSlug ────────────────────────────────────────────────────────────


class CoreSlug(BaseModel):
    entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    entity_id = models.UUIDField()
    slug = models.SlugField(max_length=100)
    scope_workspace = models.ForeignKey(
        Workspace,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="core_slugs",
    )
    scope_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="core_slugs",
    )

    class Meta:
        db_table = "core_slug"
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "entity_id"],
                name="uq_coreslug_entity",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(entity_type=EntityType.WORKSPACE),
                name="uq_slug_workspace",
            ),
            models.UniqueConstraint(
                fields=["scope_workspace", "slug"],
                condition=Q(entity_type=EntityType.TEAM),
                name="uq_slug_team",
            ),
            models.UniqueConstraint(
                fields=["scope_team", "slug"],
                condition=Q(entity_type=EntityType.DEPARTMENT),
                name="uq_slug_dept",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        entity_type=EntityType.WORKSPACE,
                        scope_workspace__isnull=True,
                        scope_team__isnull=True,
                    )
                    | Q(
                        entity_type=EntityType.TEAM,
                        scope_workspace__isnull=False,
                        scope_team__isnull=True,
                    )
                    | Q(
                        entity_type=EntityType.DEPARTMENT,
                        scope_workspace__isnull=True,
                        scope_team__isnull=False,
                    )
                ),
                name="ck_coreslug_scope_fks",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type", "slug"], name="idx_coreslug_type_slug"),
            models.Index(fields=["entity_type", "entity_id"], name="idx_coreslug_entity_lookup"),
            models.Index(fields=["entity_id"], name="idx_coreslug_entity_id"),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.slug}"


# ── CoreSlug helpers ────────────────────────────────────────────────────


def resolve_slug(entity_type: str, slug: str, **scope):
    """
    Look up an entity UUID by slug.

    Usage:
        resolve_slug("workspace", "acme-corp")
        resolve_slug("team", "engineering", scope_workspace=workspace)
        resolve_slug("department", "frontend", scope_team=team)
    """
    return CoreSlug.objects.get(entity_type=entity_type, slug=slug, **scope)


def unique_slug(entity_type: str, slug: str, **scope):
    """
    Return ``slug`` if available, otherwise append -{n} where n is one
    higher than the largest existing numeric suffix.
    """
    import re

    from django.db.models import IntegerField, Max
    from django.db.models.functions import Cast, Substr

    if not CoreSlug.objects.filter(entity_type=entity_type, slug=slug, **scope).exists():
        return slug

    prefix = f"{slug}-"
    max_n = (
        (
            CoreSlug.objects.filter(
                entity_type=entity_type,
                slug__startswith=prefix,
                slug__regex=rf"^{re.escape(slug)}-\d+$",
                **scope,
            )
            .annotate(
                _suffix=Cast(
                    Substr("slug", len(prefix) + 1),
                    IntegerField(),
                )
            )
            .aggregate(m=Max("_suffix"))["m"]
        )
        or 0
    )
    return f"{slug}-{max_n + 1}"


def create_slug(entity_type: str, entity_id, slug: str, **scope):
    """
    Create a CoreSlug row for a new entity.

    Usage:
        create_slug("workspace", ws.id, "acme-corp")
        create_slug("team", team.id, "engineering", scope_workspace=workspace)
        create_slug("department", dept.id, "frontend", scope_team=team)
    """
    return CoreSlug.objects.create(
        entity_type=entity_type,
        entity_id=entity_id,
        slug=slug,
        **scope,
    )


# ── ProcessAuditRule ────────────────────────────────────────────────────


class SkillAuditRule(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="audit_rules",
    )
    period_days = models.PositiveIntegerField()

    class Meta:
        db_table = "skill_audit_rule"

    def __str__(self):
        return f"Audit every {self.period_days} days"


class StalenessAlertRule(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="staleness_alert_rules",
    )
    period_days = models.PositiveIntegerField()
    notify_admins = models.BooleanField(default=True)
    notify_team_managers = models.BooleanField(default=False)
    notify_skill_owner = models.BooleanField(default=True)

    class Meta:
        db_table = "staleness_alert_rule"

    def __str__(self):
        return f"Staleness alert every {self.period_days} days"


# ── CoreSettings ────────────────────────────────────────────────────────


class CoreSettings(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="settings",
    )

    require_review_before_publish = models.BooleanField(null=True, default=None)
    enable_version_history = models.BooleanField(null=True, default=None)
    enable_api_access = models.BooleanField(null=True, default=None)
    require_change_summary = models.BooleanField(null=True, default=None)
    allow_agent_skill_updates = models.BooleanField(null=True, default=None)
    skill_audit = models.ForeignKey(
        SkillAuditRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="settings",
    )
    staleness_alert = models.ForeignKey(
        StalenessAlertRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="settings",
    )

    class Meta:
        db_table = "core_settings"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=Q(team__isnull=True, department__isnull=True),
                name="uq_settings_workspace",
            ),
            models.UniqueConstraint(
                fields=["workspace", "team"],
                condition=Q(department__isnull=True, team__isnull=False),
                name="uq_settings_team",
            ),
            models.UniqueConstraint(
                fields=["workspace", "team", "department"],
                condition=Q(department__isnull=False),
                name="uq_settings_department",
            ),
            models.CheckConstraint(
                condition=Q(department__isnull=True) | Q(team__isnull=False),
                name="ck_settings_dept_requires_team",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace"], name="idx_settings_workspace"),
            models.Index(fields=["workspace", "team"], name="idx_settings_ws_team"),
            models.Index(
                fields=["workspace", "team", "department"],
                name="idx_settings_ws_team_dept",
            ),
        ]

    def __str__(self):
        parts = [f"ws={self.workspace_id}"]
        if self.team_id:
            parts.append(f"team={self.team_id}")
        if self.department_id:
            parts.append(f"dept={self.department_id}")
        return f"Settings({', '.join(parts)})"


SETTINGS_FIELDS = [
    "require_review_before_publish",
    "enable_version_history",
    "enable_api_access",
    "require_change_summary",
    "allow_agent_skill_updates",
]

FK_SETTINGS_FIELDS = [
    "skill_audit",
    "staleness_alert",
]


def get_effective_settings(workspace_id, team_id=None, department_id=None):
    """
    Resolve settings with most-specific-wins inheritance.

    Boolean fields: first non-None wins (dept -> team -> workspace).
    FK fields (like skill_audit): first non-null FK wins, returned as
    the related object (or None).
    """
    filters = Q(workspace_id=workspace_id, team__isnull=True, department__isnull=True)
    if team_id:
        filters |= Q(workspace_id=workspace_id, team_id=team_id, department__isnull=True)
    if department_id:
        filters |= Q(workspace_id=workspace_id, team_id=team_id, department_id=department_id)

    rows = list(CoreSettings.objects.filter(filters).select_related(*FK_SETTINGS_FIELDS))

    dept_row = next((r for r in rows if r.department_id is not None), None)
    team_row = next((r for r in rows if r.team_id is not None and r.department_id is None), None)
    ws_row = next((r for r in rows if r.team_id is None and r.department_id is None), None)

    result = {}
    for field in SETTINGS_FIELDS:
        val = None
        for row in (dept_row, team_row, ws_row):
            if row is not None:
                v = getattr(row, field)
                if v is not None:
                    val = v
                    break
        result[field] = val

    for field in FK_SETTINGS_FIELDS:
        val = None
        fk_id_field = f"{field}_id"
        for row in (dept_row, team_row, ws_row):
            if row is not None and getattr(row, fk_id_field) is not None:
                val = getattr(row, field)
                break
        result[field] = val

    return result


# ── CoreSlug cleanup signals ─────────────────────────────────────────────


@receiver(post_delete, sender=Workspace)
def _cleanup_workspace_slug(sender, instance, **kwargs):
    CoreSlug.objects.filter(entity_type=EntityType.WORKSPACE, entity_id=instance.id).delete()


@receiver(post_delete, sender=Team)
def _cleanup_team_slug(sender, instance, **kwargs):
    CoreSlug.objects.filter(entity_type=EntityType.TEAM, entity_id=instance.id).delete()


@receiver(post_delete, sender=Department)
def _cleanup_department_slug(sender, instance, **kwargs):
    CoreSlug.objects.filter(entity_type=EntityType.DEPARTMENT, entity_id=instance.id).delete()


# ── PendingInvitation ────────────────────────────────────────────────────


class PendingInvitation(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    departments = models.ManyToManyField(
        Department,
        blank=True,
    )
    invited_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "pending_invitation"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "email"],
                condition=Q(status=InvitationStatus.PENDING),
                name="uq_pending_invite_per_workspace",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "status"], name="idx_invitation_ws_status"),
        ]

    def __str__(self):
        return f"Invite {self.email} -> {self.workspace.name} ({self.status})"

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)


# ── FeatureFlag ─────────────────────────────────────────────────────────


class FeatureFlag(BaseModel):
    name = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "feature_flag"

    def __str__(self):
        return self.name


class WorkspaceFeatureFlag(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="feature_flags",
    )
    flag = models.ForeignKey(
        FeatureFlag,
        on_delete=models.CASCADE,
        related_name="workspace_assignments",
    )

    class Meta:
        db_table = "workspace_feature_flag"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "flag"],
                name="uq_workspace_feature_flag",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace"], name="idx_wff_workspace"),
        ]

    def __str__(self):
        return f"{self.workspace.name} → {self.flag.name}"


# ── ApiKey ──────────────────────────────────────────────────────────────


class ApiKey(BaseModel):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
    )
    key_hash = models.CharField(max_length=64, unique=True)
    key_prefix = models.CharField(max_length=10)
    label = models.CharField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.ADMIN,
    )
    team = models.ForeignKey(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="api_keys",
    )
    departments = models.ManyToManyField(
        "Department",
        blank=True,
        related_name="api_key_departments",
    )

    class Meta:
        db_table = "api_key"
        indexes = [
            models.Index(
                fields=["key_hash", "is_active"],
                name="idx_apikey_hash_active",
            ),
            models.Index(
                fields=["workspace", "-created_at"],
                name="idx_apikey_ws_created",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.key_prefix}...)"

    @staticmethod
    def generate():
        raw_key = f"kf_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:10]
        return raw_key, key_hash, key_prefix

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()
