import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, RefreshToken

from apps.accounts.models import McpConnectionScope, ScopeType


def _create_oauth_app(name="Test MCP Client"):
    return Application.objects.create(
        name=name,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://localhost:3000/callback",
    )


def _create_access_token(app, user, scope="processes:read processes:write", expired=False):
    expires = timezone.now() + (timedelta(hours=-1) if expired else timedelta(hours=1))
    return AccessToken.objects.create(
        user=user,
        application=app,
        token=f"test-token-{AccessToken.objects.count()}",
        expires=expires,
        scope=scope,
    )


def _create_refresh_token(app, user, access_token, revoked=False):
    rt = RefreshToken.objects.create(
        user=user,
        application=app,
        token=f"test-refresh-{RefreshToken.objects.count()}",
        access_token=access_token,
    )
    if revoked:
        rt.revoked = timezone.now()
        rt.save(update_fields=["revoked"])
    return rt


@pytest.mark.django_db
class TestListMcpConnections:
    def test_list_returns_connections_for_workspace(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token)

        resp = auth_client.get("/api/v1/mcp/connections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        conn = data["items"][0]
        assert conn["client_name"] == "Test MCP Client"
        assert conn["user"]["email"] == user.email
        assert conn["is_active"] is True

    def test_list_excludes_other_workspace_connections(self, auth_client, admin_membership):
        from apps.accounts.tests.factories import UserFactory
        from apps.orgs.tests.factories import MembershipFactory, WorkspaceFactory

        other_ws = WorkspaceFactory()
        other_user = UserFactory()
        MembershipFactory(user=other_user, workspace=other_ws)

        app = _create_oauth_app(name="Other Workspace Client")
        _create_access_token(app, other_user)

        resp = auth_client.get("/api/v1/mcp/connections")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_admin_only(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.get("/api/v1/mcp/connections")
        assert resp.status_code == 403

    def test_expired_refresh_shows_inactive(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token, revoked=True)

        resp = auth_client.get("/api/v1/mcp/connections")
        assert resp.status_code == 200
        conn = resp.json()["items"][0]
        assert conn["is_active"] is False


@pytest.mark.django_db
class TestRevokeMcpConnection:
    def test_revoke_deletes_app_and_tokens(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token)

        resp = auth_client.delete(f"/api/v1/mcp/connections/{app.id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        assert not Application.objects.filter(id=app.id).exists()
        assert not AccessToken.objects.filter(application=app).exists()

    def test_revoke_404_for_other_workspace(self, auth_client, admin_membership):
        from apps.accounts.tests.factories import UserFactory
        from apps.orgs.tests.factories import MembershipFactory, WorkspaceFactory

        other_ws = WorkspaceFactory()
        other_user = UserFactory()
        MembershipFactory(user=other_user, workspace=other_ws)

        app = _create_oauth_app()
        _create_access_token(app, other_user)

        resp = auth_client.delete(f"/api/v1/mcp/connections/{app.id}")
        assert resp.status_code == 404

    def test_revoke_404_for_nonexistent(self, auth_client, admin_membership):
        resp = auth_client.delete("/api/v1/mcp/connections/99999")
        assert resp.status_code == 404

    def test_revoke_admin_only(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        app = _create_oauth_app()
        resp = client.delete(f"/api/v1/mcp/connections/{app.id}")
        assert resp.status_code == 403

    def test_revoke_deletes_scope(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token)

        McpConnectionScope.objects.create(
            application=app,
            user=user,
            workspace=admin_membership.workspace,
            scope_type=ScopeType.WORKSPACE,
        )

        resp = auth_client.delete(f"/api/v1/mcp/connections/{app.id}")
        assert resp.status_code == 200
        assert McpConnectionScope.objects.count() == 0


@pytest.mark.django_db
class TestListMcpConnectionsWithScope:
    def test_list_includes_scope_info(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token)

        team = TeamFactory(workspace=admin_membership.workspace)
        McpConnectionScope.objects.create(
            application=app,
            user=user,
            workspace=admin_membership.workspace,
            scope_type=ScopeType.TEAM,
            team=team,
        )

        resp = auth_client.get("/api/v1/mcp/connections")
        assert resp.status_code == 200
        conn = resp.json()["items"][0]
        assert conn["connection_scope"] is not None
        assert conn["connection_scope"]["scope_type"] == "team"
        assert conn["connection_scope"]["team_name"] == team.name

    def test_list_returns_null_scope_when_not_set(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        token = _create_access_token(app, user)
        _create_refresh_token(app, user, token)

        resp = auth_client.get("/api/v1/mcp/connections")
        conn = resp.json()["items"][0]
        assert conn["connection_scope"] is None


@pytest.mark.django_db
class TestGetConnectionScope:
    def test_get_scope_default(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        resp = auth_client.get(f"/api/v1/mcp/connections/{app.id}/scope")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "workspace"
        assert data["team_id"] is None
        assert data["department_ids"] == []

    def test_get_scope_with_team(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team = TeamFactory(workspace=admin_membership.workspace)
        McpConnectionScope.objects.create(
            application=app,
            user=user,
            workspace=admin_membership.workspace,
            scope_type=ScopeType.TEAM,
            team=team,
        )

        resp = auth_client.get(f"/api/v1/mcp/connections/{app.id}/scope")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "team"
        assert data["team_id"] == str(team.id)
        assert data["team_name"] == team.name

    def test_get_scope_with_departments(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import DepartmentFactory, TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team = TeamFactory(workspace=admin_membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)

        scope = McpConnectionScope.objects.create(
            application=app,
            user=user,
            workspace=admin_membership.workspace,
            scope_type=ScopeType.DEPARTMENT,
        )
        scope.departments.set([dept1, dept2])

        resp = auth_client.get(f"/api/v1/mcp/connections/{app.id}/scope")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "department"
        assert set(data["department_ids"]) == {str(dept1.id), str(dept2.id)}
        assert len(data["departments"]) == 2

    def test_get_scope_admin_only(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        app = _create_oauth_app()
        resp = client.get(f"/api/v1/mcp/connections/{app.id}/scope")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestUpdateConnectionScope:
    def test_set_team_scope(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team = TeamFactory(workspace=admin_membership.workspace)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "team", "team_id": str(team.id)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "team"
        assert data["team_id"] == str(team.id)
        assert data["team_name"] == team.name

        scope = McpConnectionScope.objects.get(application=app)
        assert scope.scope_type == ScopeType.TEAM
        assert scope.team_id == team.id

    def test_set_department_scope(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import DepartmentFactory, TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team = TeamFactory(workspace=admin_membership.workspace)
        dept = DepartmentFactory(team=team)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "department", "department_ids": [str(dept.id)]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "department"
        assert data["department_ids"] == [str(dept.id)]
        assert len(data["departments"]) == 1
        assert data["departments"][0]["name"] == dept.name

    def test_reset_to_workspace_scope(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team = TeamFactory(workspace=admin_membership.workspace)
        McpConnectionScope.objects.create(
            application=app,
            user=user,
            workspace=admin_membership.workspace,
            scope_type=ScopeType.TEAM,
            team=team,
        )

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "workspace"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "workspace"
        assert data["team_id"] is None
        assert data["department_ids"] == []

    def test_team_scope_requires_team_id(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "team"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_department_scope_requires_department_ids(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "department", "department_ids": []}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_team_must_belong_to_workspace(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import TeamFactory, WorkspaceFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        other_ws = WorkspaceFactory()
        other_team = TeamFactory(workspace=other_ws)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "team", "team_id": str(other_team.id)}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_departments_must_belong_to_workspace(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import DepartmentFactory, TeamFactory, WorkspaceFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        other_ws = WorkspaceFactory()
        other_team = TeamFactory(workspace=other_ws)
        other_dept = DepartmentFactory(team=other_team)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "department", "department_ids": [str(other_dept.id)]}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_scope_type(self, auth_client, admin_membership):
        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "galaxy"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_update_scope_admin_only(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        app = _create_oauth_app()
        resp = client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "workspace"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_update_scope_idempotent(self, auth_client, admin_membership):
        """Updating scope twice should update, not create a duplicate."""
        from apps.orgs.tests.factories import TeamFactory

        user = admin_membership.user
        app = _create_oauth_app()
        _create_access_token(app, user)

        team1 = TeamFactory(workspace=admin_membership.workspace)
        team2 = TeamFactory(workspace=admin_membership.workspace)

        auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "team", "team_id": str(team1.id)}),
            content_type="application/json",
        )
        resp = auth_client.patch(
            f"/api/v1/mcp/connections/{app.id}/scope",
            data=json.dumps({"scope_type": "team", "team_id": str(team2.id)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert McpConnectionScope.objects.filter(application=app).count() == 1
        assert resp.json()["team_id"] == str(team2.id)
