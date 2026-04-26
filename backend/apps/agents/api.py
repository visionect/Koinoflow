from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import require_role
from apps.agents.models import Agent, AgentSkillDeployment
from apps.common.throttles import CreateAuthThrottle, MutationThrottle, ReadThrottle
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.models import (
    SYSTEM_KIND_AGENTS,
    Department,
    FeatureFlag,
    Team,
    WorkspaceFeatureFlag,
    create_slug,
    unique_slug,
)
from apps.skills.api import _empty_metadata_dict, _file_entry_from_payload, _version_file_from_entry
from apps.skills.discovery import queue_skill_discovery_embedding
from apps.skills.enums import StatusChoices, VisibilityChoices
from apps.skills.models import Skill, SkillVersion, VersionFile
from apps.usage.models import UsageEvent

router = Router(tags=["agents"])


class AgentOut(Schema):
    id: str
    name: str
    description: str
    token_prefix: str
    masked_token: str
    is_active: bool
    last_used_at: str | None
    created_at: str


class CreatedAgentOut(AgentOut):
    token: str


class AgentListOut(Schema):
    items: list[AgentOut]
    count: int


class CreateAgentIn(Schema):
    name: str
    description: str = ""


class UpdateAgentIn(Schema):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class VersionFileIn(Schema):
    path: str
    content: str | None = None
    content_base64: str | None = None
    file_type: str
    mime_type: str | None = None
    encoding: str | None = None
    size_bytes: int | None = None


class ImportAgentSkillIn(Schema):
    title: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)
    description: str = ""
    content_md: str
    frontmatter_yaml: str = ""
    files: list[VersionFileIn] = []
    deploy_to_all: bool = True
    agent_ids: list[str] = []


class AgentSkillOut(Schema):
    id: str
    title: str
    slug: str
    description: str
    deploy_to_all: bool
    agent_ids: list[str]
    created_at: str
    updated_at: str


class AgentSkillListOut(Schema):
    items: list[AgentSkillOut]
    count: int


class AgentUsageEventOut(Schema):
    id: str
    agent_id: str | None
    agent_name: str | None
    skill_title: str
    skill_slug: str
    version_number: int
    client_id: str
    client_type: str
    tool_name: str
    called_at: str


class AgentUsageListOut(Schema):
    items: list[AgentUsageEventOut]
    count: int


class AgentAnalyticsOut(Schema):
    total_calls: int
    active_agents: int
    skills_touched: int
    by_agent: list[dict]
    by_skill: list[dict]


def _require_agents_feature(workspace):
    if not workspace:
        raise HttpError(403, "No workspace context")
    enabled = WorkspaceFeatureFlag.objects.filter(
        workspace=workspace,
        flag__name="agents",
    ).exists()
    if not enabled:
        raise HttpError(404, "Agents feature is not enabled for this workspace.")


def _agent_out(agent: Agent):
    return {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "token_prefix": agent.token_prefix,
        "masked_token": f"{agent.token_prefix}...",
        "is_active": agent.is_active,
        "last_used_at": agent.last_used_at.isoformat() if agent.last_used_at else None,
        "created_at": agent.created_at.isoformat(),
    }


def _ensure_agents_feature_flag():
    FeatureFlag.objects.get_or_create(name="agents")


def _ensure_agents_department(workspace):
    team = Team.objects.filter(workspace=workspace, system_kind=SYSTEM_KIND_AGENTS).first()
    if team is None:
        team = Team.objects.create(
            workspace=workspace,
            name="Agents",
            system_kind=SYSTEM_KIND_AGENTS,
        )
        create_slug(
            EntityType.TEAM,
            team.id,
            unique_slug(EntityType.TEAM, "agents", scope_workspace=workspace),
            scope_workspace=workspace,
        )

    department = Department.objects.filter(team=team, system_kind=SYSTEM_KIND_AGENTS).first()
    if department is None:
        department = Department.objects.create(
            team=team,
            name="Agents",
            system_kind=SYSTEM_KIND_AGENTS,
        )
        create_slug(
            EntityType.DEPARTMENT,
            department.id,
            unique_slug(EntityType.DEPARTMENT, "agents", scope_team=team),
            scope_team=team,
        )
    return department


def _agent_skill_out(skill: Skill):
    deployments = list(skill.agent_deployments.select_related("agent"))
    deploy_to_all = any(d.deploy_to_all for d in deployments)
    return {
        "id": str(skill.id),
        "title": skill.title,
        "slug": skill.slug,
        "description": skill.description,
        "deploy_to_all": deploy_to_all,
        "agent_ids": [str(d.agent_id) for d in deployments if d.agent_id],
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


def _agent_usage_out(event: UsageEvent):
    return {
        "id": str(event.id),
        "agent_id": str(event.agent_id) if event.agent_id else None,
        "agent_name": event.agent.name if event.agent_id else None,
        "skill_title": event.skill.title,
        "skill_slug": event.skill.slug,
        "version_number": event.version_number,
        "client_id": event.client_id,
        "client_type": event.client_type,
        "tool_name": event.tool_name,
        "called_at": event.called_at.isoformat(),
    }


@router.get("/agents", response=AgentListOut, auth=api_or_session, throttle=[ReadThrottle()])
@require_role(RoleChoices.ADMIN)
def list_agents(request, limit: int = 50, offset: int = 0):
    _require_agents_feature(request.workspace)
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = Agent.objects.filter(workspace=request.workspace).order_by("name")
    count = qs.count()
    return {"items": [_agent_out(a) for a in qs[offset : offset + limit]], "count": count}


@router.post(
    "/agents",
    response={201: CreatedAgentOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN)
def create_agent(request, payload: CreateAgentIn):
    _ensure_agents_feature_flag()
    _require_agents_feature(request.workspace)
    raw_token, token_hash, token_prefix = Agent.generate_token()
    agent = Agent.objects.create(
        workspace=request.workspace,
        name=payload.name,
        description=payload.description,
        token_hash=token_hash,
        token_prefix=token_prefix,
    )
    data = _agent_out(agent)
    data["token"] = raw_token
    return Status(201, data)


@router.patch(
    "/agents/{agent_id}/settings",
    response=AgentOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def update_agent(request, agent_id: str, payload: UpdateAgentIn):
    _require_agents_feature(request.workspace)
    try:
        agent = Agent.objects.get(id=agent_id, workspace=request.workspace)
    except Agent.DoesNotExist:
        raise HttpError(404, "Agent not found")

    update_fields = ["updated_at"]
    if payload.name is not None:
        agent.name = payload.name
        update_fields.append("name")
    if payload.description is not None:
        agent.description = payload.description
        update_fields.append("description")
    if payload.is_active is not None:
        agent.is_active = payload.is_active
        update_fields.append("is_active")
    agent.save(update_fields=update_fields)
    return _agent_out(agent)


@router.post(
    "/agents/{agent_id}/rotate-token",
    response=CreatedAgentOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def rotate_agent_token(request, agent_id: str):
    _require_agents_feature(request.workspace)
    try:
        agent = Agent.objects.get(id=agent_id, workspace=request.workspace)
    except Agent.DoesNotExist:
        raise HttpError(404, "Agent not found")
    raw_token, token_hash, token_prefix = Agent.generate_token()
    agent.token_hash = token_hash
    agent.token_prefix = token_prefix
    agent.save(update_fields=["token_hash", "token_prefix", "updated_at"])
    data = _agent_out(agent)
    data["token"] = raw_token
    return data


@router.get(
    "/agents/skills",
    response=AgentSkillListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_agent_skills(request, limit: int = 50, offset: int = 0):
    _require_agents_feature(request.workspace)
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        Skill.objects.filter(
            department__team__workspace=request.workspace,
            department__system_kind=SYSTEM_KIND_AGENTS,
        )
        .prefetch_related("agent_deployments")
        .order_by("-updated_at")
    )
    count = qs.count()
    return {
        "items": [_agent_skill_out(skill) for skill in qs[offset : offset + limit]],
        "count": count,
    }


@router.post(
    "/agents/skills/import",
    response={201: AgentSkillOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN)
def import_agent_skill(request, payload: ImportAgentSkillIn):
    _require_agents_feature(request.workspace)
    if not payload.deploy_to_all and not payload.agent_ids:
        raise HttpError(400, "Select at least one agent or deploy to all agents.")

    agents = []
    if payload.agent_ids:
        agents = list(
            Agent.objects.filter(
                id__in=payload.agent_ids,
                workspace=request.workspace,
                is_active=True,
            )
        )
        if len(agents) != len(set(payload.agent_ids)):
            raise HttpError(400, "One or more agent IDs are invalid")

    department = _ensure_agents_department(request.workspace)
    with transaction.atomic():
        if Skill.objects.filter(department=department, slug=payload.slug).exists():
            raise HttpError(409, "Agent skill slug already exists")
        skill = Skill.objects.create(
            department=department,
            title=payload.title,
            slug=payload.slug,
            description=payload.description,
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.DEPARTMENT,
        )
        version = SkillVersion.objects.create(
            skill=skill,
            version_number=1,
            content_md=payload.content_md,
            frontmatter_yaml=payload.frontmatter_yaml,
            change_summary="Imported from Agents",
            authored_by=request.user if request.user.is_authenticated else None,
            koinoflow_metadata=_empty_metadata_dict(),
        )
        file_rows = [
            _version_file_from_entry(version, _file_entry_from_payload(file.model_dump()))
            for file in payload.files
        ]
        if file_rows:
            VersionFile.objects.bulk_create(file_rows)

        skill.current_version = version
        skill.last_reviewed_at = timezone.now()
        skill.save(update_fields=["current_version", "last_reviewed_at", "updated_at"])

        if payload.deploy_to_all:
            AgentSkillDeployment.objects.create(skill=skill, deploy_to_all=True)
        else:
            AgentSkillDeployment.objects.bulk_create(
                [AgentSkillDeployment(skill=skill, agent=agent) for agent in agents]
            )

    queue_skill_discovery_embedding(str(version.id), force=True)
    skill = Skill.objects.prefetch_related("agent_deployments").get(id=skill.id)
    return Status(201, _agent_skill_out(skill))


@router.get(
    "/agents/usage",
    response=AgentUsageListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_agent_usage(
    request,
    agent_id: str | None = None,
    days: int = 30,
    limit: int = 50,
    offset: int = 0,
):
    _require_agents_feature(request.workspace)
    days = max(1, min(days, 365))
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    since = timezone.now() - timedelta(days=days)
    qs = (
        UsageEvent.objects.filter(
            skill__department__team__workspace=request.workspace,
            skill__department__system_kind=SYSTEM_KIND_AGENTS,
            called_at__gte=since,
        )
        .select_related("skill", "agent")
        .order_by("-called_at")
    )
    if agent_id:
        qs = qs.filter(agent_id=agent_id)
    count = qs.count()
    return {"items": [_agent_usage_out(e) for e in qs[offset : offset + limit]], "count": count}


@router.get(
    "/agents/analytics",
    response=AgentAnalyticsOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def agent_analytics(request, days: int = 30):
    _require_agents_feature(request.workspace)
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)
    qs = UsageEvent.objects.filter(
        skill__department__team__workspace=request.workspace,
        skill__department__system_kind=SYSTEM_KIND_AGENTS,
        called_at__gte=since,
    )
    total_calls = qs.count()
    by_agent = list(
        qs.values("agent_id", "agent__name").annotate(count=Count("id")).order_by("-count")[:10]
    )
    by_skill = list(
        qs.values("skill_id", "skill__slug", "skill__title")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    return {
        "total_calls": total_calls,
        "active_agents": qs.values("agent_id").exclude(agent_id=None).distinct().count(),
        "skills_touched": qs.values("skill_id").distinct().count(),
        "by_agent": [
            {
                "agent_id": str(row["agent_id"]) if row["agent_id"] else None,
                "agent_name": row["agent__name"] or "Unknown agent",
                "count": row["count"],
            }
            for row in by_agent
        ],
        "by_skill": [
            {
                "skill_id": str(row["skill_id"]),
                "skill_slug": row["skill__slug"],
                "skill_title": row["skill__title"],
                "count": row["count"],
            }
            for row in by_skill
        ],
    }
