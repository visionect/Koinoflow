"""Tests for admin workspace onboarding API and milestone sync."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application

from apps.accounts.tests.factories import UserFactory
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.models import CoreSlug, WorkspaceOnboarding
from apps.orgs.tests.factories import (
    DepartmentFactory,
    MembershipFactory,
    TeamFactory,
    WorkspaceFactory,
)
from apps.skills.tests.factories import SkillFactory
from apps.usage.models import UsageEvent


def _ws_slug(workspace):
    return CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=workspace.id).slug


def _create_oauth_app(name="Test MCP Client"):
    return Application.objects.create(
        name=name,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://localhost:3000/callback",
    )


def _create_access_token(app, user):
    return AccessToken.objects.create(
        user=user,
        application=app,
        token=f"onb-tok-{AccessToken.objects.count()}",
        expires=timezone.now() + timedelta(hours=1),
        scope="openid",
    )


@pytest.mark.django_db
class TestOnboardingProgress:
    def test_progress_after_create_workspace_is_step_two(self):
        """Workspace creation seeds onboarding row; next step is team (2)."""
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "Onboarding Co", "slug": "onboarding-co"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        slug = resp.json()["slug"]

        resp_prog = client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp_prog.status_code == 200
        data = resp_prog.json()
        assert data["current_step"] == 2
        assert data["steps"][0]["completed"] is True
        assert data["steps"][1]["completed"] is False
        assert data["is_complete"] is False

    def test_agents_team_does_not_count_for_team_milestone(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"][1]["completed"] is False  # team

    def test_team_milestone_advances_progress(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        TeamFactory(workspace=ws, slug="eng-onb")

        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"][1]["completed"] is True
        assert data["current_step"] == 3

    def test_agents_department_does_not_count(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        TeamFactory(workspace=ws, slug="eng-only")
        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        data = resp.json()
        assert data["steps"][2]["completed"] is False

    def test_department_milestone_advances(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        team = TeamFactory(workspace=ws, slug="product-onb")
        DepartmentFactory(team=team, slug="design-onb")

        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"][2]["completed"] is True
        assert data["current_step"] == 4

    def test_skill_milestone_advances(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        team = TeamFactory(workspace=ws, slug="skill-team")
        dept = DepartmentFactory(team=team, slug="skill-dept")
        SkillFactory(department=dept, slug="runbook-one")

        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"][3]["completed"] is True
        assert data["current_step"] == 5

    def test_mcp_connected_milestone(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        team = TeamFactory(workspace=ws, slug="mcp-team")
        dept = DepartmentFactory(team=team, slug="mcp-dept")
        SkillFactory(department=dept, slug="mcp-skill")

        app = _create_oauth_app()
        _create_access_token(app, admin_membership.user)

        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"][4]["completed"] is True
        assert data["current_step"] == 6

    def test_complete_when_usage_logged(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        team = TeamFactory(workspace=ws, slug="usage-team")
        dept = DepartmentFactory(team=team, slug="usage-dept")
        skill = SkillFactory(department=dept, slug="usage-skill")

        app = _create_oauth_app()
        _create_access_token(app, admin_membership.user)

        UsageEvent.objects.create(
            skill=skill,
            version_number=1,
            client_id="c1",
            client_type="Cursor",
            tool_name="read_skill",
        )

        resp = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_complete"] is True
        assert data["steps"][5]["completed"] is True
        assert WorkspaceOnboarding.objects.get(workspace=ws).completed_at is not None

    def test_two_admins_share_workspace_progress(self):
        ws = WorkspaceFactory(slug="shared-ws")
        slug = _ws_slug(ws)
        admin_a = UserFactory()
        admin_b = UserFactory()
        MembershipFactory(user=admin_a, workspace=ws, role=RoleChoices.ADMIN)
        MembershipFactory(user=admin_b, workspace=ws, role=RoleChoices.ADMIN)

        TeamFactory(workspace=ws, slug="shared-team")

        client_a = Client()
        client_a.force_login(admin_a)
        client_b = Client()
        client_b.force_login(admin_b)

        ra = client_a.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        rb = client_b.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert ra.json()["current_step"] == rb.json()["current_step"] == 3

    def test_dismiss_is_per_admin(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _ws_slug(ws)
        other = UserFactory()
        MembershipFactory(user=other, workspace=ws, role=RoleChoices.ADMIN)

        resp_dismiss = auth_client.patch(
            "/api/v1/onboarding/preference",
            data={"dismissed": True},
            content_type="application/json",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp_dismiss.status_code == 200

        resp_me = auth_client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp_me.json()["is_dismissed"] is True

        client_b = Client()
        client_b.force_login(other)
        resp_other = client_b.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp_other.json()["is_dismissed"] is False

    def test_member_cannot_access_progress(self, member_membership):
        ws = member_membership.workspace
        slug = _ws_slug(ws)
        client = Client()
        client.force_login(member_membership.user)
        resp = client.get(
            "/api/v1/onboarding/progress",
            HTTP_X_WORKSPACE_SLUG=slug,
        )
        assert resp.status_code == 403
