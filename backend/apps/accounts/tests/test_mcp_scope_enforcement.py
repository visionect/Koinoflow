"""
Tests for MCP connection scope enforcement on process endpoints.

Verifies that apply_oauth_connection_scope correctly narrows the process
queryset, and that the narrowing can never widen access beyond the user's role.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application

from apps.accounts.models import McpConnectionScope, ScopeType
from apps.accounts.permissions import _apply_membership_scope, apply_oauth_connection_scope
from apps.orgs.enums import RoleChoices
from apps.orgs.tests.factories import DepartmentFactory, MembershipFactory, TeamFactory
from apps.skills.enums import VisibilityChoices
from apps.skills.models import Skill


def _create_app_and_token(user):
    app = Application.objects.create(
        name="Test Client",
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://localhost/callback",
    )
    token = AccessToken.objects.create(
        user=user,
        application=app,
        token=f"tok-{AccessToken.objects.count()}",
        expires=timezone.now() + timedelta(hours=1),
        scope="processes:read",
    )
    return app, token


class _MockRequest:
    """Minimal request-like object for testing permission functions."""

    def __init__(self, *, membership=None, oauth_token=None, workspace=None):
        self.membership = membership
        self.workspace = workspace or (membership.workspace if membership else None)
        if oauth_token:
            self.oauth_token = oauth_token


def _make_process(department, visibility="department", status="published"):
    return Skill.objects.create(
        department=department,
        title=f"Process in {department.name}",
        slug=f"proc-{Skill.objects.count()}",
        status=status,
        visibility=visibility,
    )


@pytest.mark.django_db
class TestApplyOAuthConnectionScope:
    """Unit tests for the apply_oauth_connection_scope function."""

    def test_no_scope_returns_all_for_admin(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        _make_process(dept1)
        _make_process(dept2)

        app, token = _create_app_and_token(membership.user)
        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert result.count() == 2

    def test_team_scope_narrows_admin_to_team(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team1 = TeamFactory(workspace=membership.workspace)
        team2 = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team1)
        dept2 = DepartmentFactory(team=team2)
        p1 = _make_process(dept1)
        _make_process(dept2)

        app, token = _create_app_and_token(membership.user)
        McpConnectionScope.objects.create(
            application=app,
            user=membership.user,
            workspace=membership.workspace,
            scope_type=ScopeType.TEAM,
            team=team1,
        )

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert list(result) == [p1]

    def test_department_scope_narrows_admin_to_department(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        p1 = _make_process(dept1)
        _make_process(dept2)

        app, token = _create_app_and_token(membership.user)
        scope = McpConnectionScope.objects.create(
            application=app,
            user=membership.user,
            workspace=membership.workspace,
            scope_type=ScopeType.DEPARTMENT,
        )
        scope.departments.add(dept1)

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert list(result) == [p1]

    def test_workspace_visible_processes_always_included(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team1 = TeamFactory(workspace=membership.workspace)
        team2 = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team1)
        dept2 = DepartmentFactory(team=team2)
        _make_process(dept1)
        ws_proc = _make_process(dept2, visibility=VisibilityChoices.WORKSPACE)

        app, token = _create_app_and_token(membership.user)
        McpConnectionScope.objects.create(
            application=app,
            user=membership.user,
            workspace=membership.workspace,
            scope_type=ScopeType.TEAM,
            team=team1,
        )

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert ws_proc in result
        assert result.count() == 2

    def test_team_visible_processes_included_for_department_scope(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        _make_process(dept1)
        team_proc = _make_process(dept2, visibility=VisibilityChoices.TEAM)

        app, token = _create_app_and_token(membership.user)
        scope = McpConnectionScope.objects.create(
            application=app,
            user=membership.user,
            workspace=membership.workspace,
            scope_type=ScopeType.DEPARTMENT,
        )
        scope.departments.add(dept1)

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert team_proc in result
        assert result.count() == 2

    def test_scope_cannot_widen_member_access(self):
        """A member scoped to dept1 cannot see dept2 processes even with workspace scope."""
        membership = MembershipFactory(role=RoleChoices.MEMBER)
        team = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        membership.departments.add(dept1)
        membership.team = team
        membership.save()

        p1 = _make_process(dept1)
        _make_process(dept2)

        app, token = _create_app_and_token(membership.user)

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert p1 in result
        assert result.count() == 1

    def test_scope_narrows_team_manager_further(self):
        """A team manager scoped to a specific department sees only that dept."""
        membership = MembershipFactory(role=RoleChoices.TEAM_MANAGER)
        team = TeamFactory(workspace=membership.workspace)
        membership.team = team
        membership.save()

        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        p1 = _make_process(dept1)
        _make_process(dept2)

        app, token = _create_app_and_token(membership.user)
        scope = McpConnectionScope.objects.create(
            application=app,
            user=membership.user,
            workspace=membership.workspace,
            scope_type=ScopeType.DEPARTMENT,
        )
        scope.departments.add(dept1)

        request = _MockRequest(membership=membership, oauth_token=token)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = apply_oauth_connection_scope(request, qs)
        assert p1 in result
        assert result.count() == 1


@pytest.mark.django_db
class TestApplyMembershipScope:
    """Unit tests for role-based filtering on OAuth requests (no connection scope)."""

    def test_admin_sees_all(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        team = TeamFactory(workspace=membership.workspace)
        dept = DepartmentFactory(team=team)
        _make_process(dept)

        request = _MockRequest(membership=membership)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = _apply_membership_scope(request, qs)
        assert result.count() == 1

    def test_team_manager_sees_own_team(self):
        membership = MembershipFactory(role=RoleChoices.TEAM_MANAGER)
        team1 = TeamFactory(workspace=membership.workspace)
        team2 = TeamFactory(workspace=membership.workspace)
        membership.team = team1
        membership.save()

        dept1 = DepartmentFactory(team=team1)
        dept2 = DepartmentFactory(team=team2)
        p1 = _make_process(dept1)
        _make_process(dept2)

        request = _MockRequest(membership=membership)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = _apply_membership_scope(request, qs)
        assert list(result) == [p1]

    def test_member_sees_own_departments(self):
        membership = MembershipFactory(role=RoleChoices.MEMBER)
        team = TeamFactory(workspace=membership.workspace)
        dept1 = DepartmentFactory(team=team)
        dept2 = DepartmentFactory(team=team)
        membership.departments.add(dept1)

        p1 = _make_process(dept1)
        _make_process(dept2)

        request = _MockRequest(membership=membership)
        qs = Skill.objects.filter(department__team__workspace=membership.workspace)
        result = _apply_membership_scope(request, qs)
        assert list(result) == [p1]
