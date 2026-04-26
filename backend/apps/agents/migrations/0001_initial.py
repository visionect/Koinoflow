import django.db.models.deletion
import uuid
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("orgs", "0005_agents_system_spaces"),
        ("skills", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("token_prefix", models.CharField(max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agents",
                        to="orgs.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "agent",
                "indexes": [
                    models.Index(fields=["workspace", "is_active"], name="idx_agent_ws_active"),
                    models.Index(fields=["token_hash", "is_active"], name="idx_agent_token_active"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AgentSkillDeployment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deploy_to_all", models.BooleanField(default=False)),
                (
                    "agent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skill_deployments",
                        to="agents.agent",
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_deployments",
                        to="skills.skill",
                    ),
                ),
            ],
            options={
                "db_table": "agent_skill_deployment",
                "indexes": [
                    models.Index(fields=["skill", "deploy_to_all"], name="idx_agent_deploy_skill_all"),
                    models.Index(fields=["agent"], name="idx_agent_deploy_agent"),
                ],
                "constraints": [
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
                ],
            },
        ),
    ]
