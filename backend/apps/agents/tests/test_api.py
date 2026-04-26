import pytest

from apps.agents.models import Agent
from apps.orgs.models import (
    SYSTEM_KIND_AGENTS,
    Department,
    FeatureFlag,
    Team,
    WorkspaceFeatureFlag,
)
from apps.usage.models import UsageEvent


def enable_agents(workspace):
    flag, _ = FeatureFlag.objects.get_or_create(name="agents")
    WorkspaceFeatureFlag.objects.get_or_create(workspace=workspace, flag=flag)


@pytest.mark.django_db
class TestAgentsApi:
    def test_agents_feature_flag_required(self, auth_client):
        resp = auth_client.get("/api/v1/agents")
        assert resp.status_code == 404

    def test_create_agent_returns_token_once_and_list_masks_it(self, auth_client, admin_membership):
        enable_agents(admin_membership.workspace)

        resp = auth_client.post(
            "/api/v1/agents",
            data={"name": "Docs bot", "description": "Indexes docs"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token"].startswith("ag_")
        assert data["masked_token"] == f"{data['token_prefix']}..."

        list_resp = auth_client.get("/api/v1/agents")
        assert list_resp.status_code == 200
        listed = list_resp.json()["items"][0]
        assert "token" not in listed
        assert listed["masked_token"] == f"{data['token_prefix']}..."

    def test_imported_agent_skill_is_hidden_from_people_and_available_to_agent(
        self,
        auth_client,
        admin_membership,
    ):
        enable_agents(admin_membership.workspace)
        create_resp = auth_client.post(
            "/api/v1/agents",
            data={"name": "Runtime agent"},
            content_type="application/json",
        )
        token = create_resp.json()["token"]
        agent_id = create_resp.json()["id"]

        import_resp = auth_client.post(
            "/api/v1/agents/skills/import",
            data={
                "title": "Agent Deploy",
                "slug": "agent-deploy",
                "description": "Only agents can see this.",
                "content_md": "# Agent Deploy\n\nRun the deployment.",
                "frontmatter_yaml": "name: Agent Deploy",
                "deploy_to_all": False,
                "agent_ids": [agent_id],
            },
            content_type="application/json",
        )
        assert import_resp.status_code == 201

        hidden_team = Team.objects.get(
            workspace=admin_membership.workspace,
            system_kind=SYSTEM_KIND_AGENTS,
        )
        Department.objects.get(team=hidden_team, system_kind=SYSTEM_KIND_AGENTS)

        people_resp = auth_client.get("/api/v1/skills")
        assert people_resp.status_code == 200
        assert people_resp.json()["count"] == 0

        agent_resp = auth_client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert agent_resp.status_code == 200
        assert agent_resp.json()["count"] == 1
        assert agent_resp.json()["items"][0]["slug"] == "agent-deploy"

    def test_agent_usage_is_separate_from_people_usage(self, auth_client, admin_membership):
        enable_agents(admin_membership.workspace)
        agent_resp = auth_client.post(
            "/api/v1/agents",
            data={"name": "Usage agent"},
            content_type="application/json",
        )
        token = agent_resp.json()["token"]

        import_resp = auth_client.post(
            "/api/v1/agents/skills/import",
            data={
                "title": "Agent Usage",
                "slug": "agent-usage",
                "content_md": "# Agent Usage",
                "deploy_to_all": True,
                "agent_ids": [],
            },
            content_type="application/json",
        )
        skill_id = import_resp.json()["id"]

        log_resp = auth_client.post(
            "/api/v1/usage",
            data={
                "skill_id": skill_id,
                "version_number": 1,
                "client_id": "agent-runtime",
                "client_type": "MCP",
                "tool_name": "get_skill",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert log_resp.status_code == 200
        event = UsageEvent.objects.get()
        assert event.agent == Agent.objects.get(id=agent_resp.json()["id"])
        assert event.client_type == "Agent"

        people_usage = auth_client.get("/api/v1/usage")
        assert people_usage.status_code == 200
        assert people_usage.json()["count"] == 0

        agent_usage = auth_client.get("/api/v1/agents/usage")
        assert agent_usage.status_code == 200
        assert agent_usage.json()["count"] == 1
