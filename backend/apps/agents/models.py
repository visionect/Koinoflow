import hashlib
import secrets

from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


class Agent(BaseModel):
    workspace = models.ForeignKey(
        "orgs.Workspace",
        on_delete=models.CASCADE,
        related_name="agents",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=12)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent"
        indexes = [
            models.Index(fields=["workspace", "is_active"], name="idx_agent_ws_active"),
            models.Index(fields=["token_hash", "is_active"], name="idx_agent_token_active"),
        ]

    def __str__(self):
        return f"{self.workspace.name} / {self.name}"

    @staticmethod
    def generate_token():
        raw_token = f"ag_{secrets.token_urlsafe(32)}"
        return raw_token, Agent.hash_token(raw_token), raw_token[:10]

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()


class AgentSkillDeployment(BaseModel):
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.CASCADE,
        related_name="agent_deployments",
    )
    agent = models.ForeignKey(
        Agent,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="skill_deployments",
    )
    deploy_to_all = models.BooleanField(default=False)

    class Meta:
        db_table = "agent_skill_deployment"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(deploy_to_all=True, agent__isnull=True)
                    | Q(deploy_to_all=False, agent__isnull=False)
                ),
                name="ck_agent_deploy_target",
            ),
            models.UniqueConstraint(
                fields=["skill"],
                condition=Q(deploy_to_all=True),
                name="uq_agent_deploy_all_skill",
            ),
            models.UniqueConstraint(
                fields=["skill", "agent"],
                condition=Q(agent__isnull=False),
                name="uq_agent_deploy_skill_agent",
            ),
        ]
        indexes = [
            models.Index(fields=["skill", "deploy_to_all"], name="idx_agent_deploy_skill_all"),
            models.Index(fields=["agent"], name="idx_agent_deploy_agent"),
        ]

    def __str__(self):
        if self.deploy_to_all:
            return f"{self.skill.slug} -> all agents"
        return f"{self.skill.slug} -> {self.agent_id}"
