"""Workspace onboarding milestones and progress for admin guided setup."""

from __future__ import annotations

from django.utils import timezone
from oauth2_provider.models import AccessToken

from apps.orgs.models import (
    SYSTEM_KIND_AGENTS,
    AdminOnboardingPreference,
    Department,
    Team,
    Workspace,
    WorkspaceOnboarding,
)
from apps.skills.enums import StatusChoices
from apps.skills.models import Skill
from apps.usage.models import UsageEvent

# (step, key, title, description, cta_path)
ONBOARDING_STEPS: list[tuple[int, str, str, str, str]] = [
    (
        1,
        "workspace",
        "Create a workspace",
        "Your workspace is the shared home for teams, skills, and AI integrations.",
        "/onboarding",
    ),
    (
        2,
        "team",
        "Create a team",
        "Teams group the people and knowledge areas that own your operational skills.",
        "/teams",
    ),
    (
        3,
        "department",
        "Create a department",
        "Departments keep skills scoped to the people who maintain them.",
        "/teams",
    ),
    (
        4,
        "skill",
        "Publish a skill",
        (
            "Draft and publish a skill so people and AI clients can read it. "
            "You can also make skills executable or deploy them to agents later."
        ),
        "/skills",
    ),
    (
        5,
        "mcp_client",
        "Connect an AI client",
        (
            "Connect Cursor, Claude, or another MCP client so it can discover your skills. "
            "You can also set up dedicated agents from the Agents page."
        ),
        "/settings/mcp",
    ),
    (
        6,
        "skill_read",
        "Read a skill from the client",
        "A logged read confirms your workspace is working end to end.",
        "/usage",
    ),
]


def sync_onboarding_state(workspace: Workspace) -> WorkspaceOnboarding:
    """Stamp milestone timestamps from actual DB state (idempotent)."""
    ob, _ = WorkspaceOnboarding.objects.get_or_create(workspace=workspace)
    if ob.completed_at is not None:
        return ob
    now = timezone.now()
    changed = False

    if ob.workspace_created_at is None:
        ob.workspace_created_at = workspace.created_at
        changed = True

    if ob.team_created_at is None:
        has_team = (
            Team.objects.filter(workspace=workspace)
            .exclude(system_kind=SYSTEM_KIND_AGENTS)
            .exists()
        )
        if has_team:
            ob.team_created_at = now
            changed = True

    if ob.department_created_at is None:
        has_dept = (
            Department.objects.filter(team__workspace=workspace)
            .exclude(system_kind=SYSTEM_KIND_AGENTS)
            .exists()
        )
        if has_dept:
            ob.department_created_at = now
            changed = True

    if ob.skill_created_at is None:
        has_skill = Skill.objects.filter(
            department__team__workspace=workspace,
            department__system_kind="",
            status=StatusChoices.PUBLISHED,
        ).exists()
        if has_skill:
            ob.skill_created_at = now
            changed = True

    if ob.mcp_connected_at is None:
        has_token = AccessToken.objects.filter(
            user__memberships__workspace=workspace,
        ).exists()
        if has_token:
            ob.mcp_connected_at = now
            changed = True

    if ob.skill_read_at is None:
        has_usage = UsageEvent.objects.filter(
            skill__department__team__workspace=workspace,
        ).exists()
        if has_usage:
            ob.skill_read_at = now
            changed = True

    if ob.completed_at is None and ob.skill_read_at is not None:
        ob.completed_at = now
        changed = True

    if changed:
        ob.save()

    return ob


def _milestone_times(ob: WorkspaceOnboarding) -> list:
    return [
        ob.workspace_created_at,
        ob.team_created_at,
        ob.department_created_at,
        ob.skill_created_at,
        ob.mcp_connected_at,
        ob.skill_read_at,
    ]


def build_onboarding_progress(ob: WorkspaceOnboarding, user) -> dict:
    """Serialize onboarding steps and dismissal for the API."""
    milestones = _milestone_times(ob)
    steps_out = []
    for step_num, key, title, description, cta_path in ONBOARDING_STEPS:
        idx = step_num - 1
        completed = milestones[idx] is not None
        steps_out.append(
            {
                "step": step_num,
                "key": key,
                "title": title,
                "description": description,
                "completed": completed,
                "cta_path": cta_path,
            }
        )

    current_step = 6
    for s in steps_out:
        if not s["completed"]:
            current_step = s["step"]
            break

    is_complete = ob.skill_read_at is not None

    pref = AdminOnboardingPreference.objects.filter(workspace=ob.workspace, user=user).first()
    is_dismissed = pref.dismissed_at is not None if pref else False

    return {
        "steps": steps_out,
        "current_step": current_step,
        "is_complete": is_complete,
        "is_dismissed": is_dismissed,
    }
