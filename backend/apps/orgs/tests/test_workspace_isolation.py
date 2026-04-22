"""Regression tests for workspace isolation.

Reproduces the multi-tenancy leak that used to happen when
``request.workspace`` was picked via ``Membership.objects.filter(...).first()``
— an arbitrary row that could resolve to the *other* workspace when a user
belonged to more than one. These tests pin the new behaviour:

1. Deterministic fallback (oldest membership by created_at, id).
2. Explicit X-Workspace-Slug header wins.
3. A slug that is not one of the user's workspaces yields no workspace
   (never leaks into a different tenant).
4. An API key scoped to workspace A cannot read/write resources in
   workspace B, even when the user who created the key is a member of
   both.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.middleware import resolve_membership_for_user
from apps.orgs.models import ApiKey, CoreSlug, Membership
from apps.orgs.tests.factories import MembershipFactory, WorkspaceFactory


def _slug_for(workspace):
    return CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=workspace.id).slug


@pytest.mark.django_db
class TestResolveMembership:
    def test_no_memberships_returns_none(self):
        user = UserFactory()
        assert resolve_membership_for_user(user) is None

    def test_single_membership_is_returned(self):
        m = MembershipFactory()
        assert resolve_membership_for_user(m.user) == m

    def test_fallback_picks_oldest_membership(self):
        user = UserFactory()
        older = MembershipFactory(user=user)
        Membership.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        newer = MembershipFactory(user=user)
        Membership.objects.filter(pk=newer.pk).update(created_at=timezone.now() - timedelta(days=1))

        resolved = resolve_membership_for_user(user)
        assert resolved is not None
        assert resolved.pk == older.pk

    def test_fallback_is_stable_across_multiple_calls(self):
        user = UserFactory()
        m1 = MembershipFactory(user=user)
        m2 = MembershipFactory(user=user)
        # Force identical created_at so ordering must fall back to id.
        now = timezone.now()
        Membership.objects.filter(pk__in=[m1.pk, m2.pk]).update(created_at=now)

        first = resolve_membership_for_user(user)
        second = resolve_membership_for_user(user)
        third = resolve_membership_for_user(user)
        assert first.pk == second.pk == third.pk

    def test_explicit_slug_wins_over_fallback(self):
        user = UserFactory()
        first_ws = WorkspaceFactory()
        second_ws = WorkspaceFactory()
        MembershipFactory(user=user, workspace=first_ws)
        target = MembershipFactory(user=user, workspace=second_ws)

        resolved = resolve_membership_for_user(user, _slug_for(second_ws))
        assert resolved.pk == target.pk

    def test_slug_for_unknown_workspace_returns_none(self):
        user = UserFactory()
        MembershipFactory(user=user)
        assert resolve_membership_for_user(user, "does-not-exist") is None

    def test_slug_for_workspace_user_is_not_member_of_returns_none(self):
        user = UserFactory()
        MembershipFactory(user=user)
        outsider_ws = WorkspaceFactory()
        # The slug exists but user is not a member; must not leak across tenant.
        assert resolve_membership_for_user(user, _slug_for(outsider_ws)) is None


@pytest.mark.django_db
class TestMeEndpointWorkspaceHeader:
    def test_default_me_returns_oldest_membership(self):
        user = UserFactory()
        oldest_ws = WorkspaceFactory()
        newest_ws = WorkspaceFactory()
        m_old = MembershipFactory(user=user, workspace=oldest_ws)
        Membership.objects.filter(pk=m_old.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        MembershipFactory(user=user, workspace=newest_ws)

        client = Client()
        client.force_login(user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["workspace_slug"] == _slug_for(oldest_ws)

    def test_x_workspace_slug_header_switches_workspace(self):
        user = UserFactory()
        ws_a = WorkspaceFactory()
        ws_b = WorkspaceFactory()
        MembershipFactory(user=user, workspace=ws_a, role=RoleChoices.ADMIN)
        MembershipFactory(user=user, workspace=ws_b, role=RoleChoices.MEMBER)

        client = Client()
        client.force_login(user)

        resp_a = client.get("/api/v1/auth/me", HTTP_X_WORKSPACE_SLUG=_slug_for(ws_a))
        resp_b = client.get("/api/v1/auth/me", HTTP_X_WORKSPACE_SLUG=_slug_for(ws_b))

        assert resp_a.json()["workspace_slug"] == _slug_for(ws_a)
        assert resp_a.json()["role"] == RoleChoices.ADMIN
        assert resp_b.json()["workspace_slug"] == _slug_for(ws_b)
        assert resp_b.json()["role"] == RoleChoices.MEMBER

    def test_x_workspace_slug_for_foreign_workspace_falls_back_cleanly(self):
        """Passing a slug the user does not belong to must not impersonate
        someone else's tenant; the /me response must reflect "no workspace"."""
        user = UserFactory()
        MembershipFactory(user=user)
        foreign_ws = WorkspaceFactory()

        client = Client()
        client.force_login(user)
        resp = client.get("/api/v1/auth/me", HTTP_X_WORKSPACE_SLUG=_slug_for(foreign_ws))
        assert resp.status_code == 200
        assert resp.json()["workspace_slug"] is None
        assert resp.json()["role"] is None


@pytest.mark.django_db
class TestApiKeyCannotCrossWorkspace:
    """An API key generated in workspace A must scope every request to A,
    even when the creating user is also a member of workspace B."""

    def _issue_key(self, workspace):
        raw, key_hash, prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=workspace,
            key_hash=key_hash,
            key_prefix=prefix,
            label="scoped-key",
        )
        return raw

    def test_api_key_is_pinned_to_its_workspace(self):
        user = UserFactory()
        ws_a = WorkspaceFactory()
        ws_b = WorkspaceFactory()
        MembershipFactory(user=user, workspace=ws_a, role=RoleChoices.ADMIN)
        MembershipFactory(user=user, workspace=ws_b, role=RoleChoices.ADMIN)

        raw = self._issue_key(ws_a)

        client = Client()
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )
        assert resp.status_code == 200
        assert resp.json()["workspace_slug"] == _slug_for(ws_a)
        assert resp.json()["workspace_slug"] != _slug_for(ws_b)

    def test_workspace_header_cannot_override_api_key_workspace(self):
        ws_a = WorkspaceFactory()
        ws_b = WorkspaceFactory()
        raw = self._issue_key(ws_a)

        client = Client()
        # Attacker attempts to pivot a workspace-A key into workspace B.
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
            HTTP_X_WORKSPACE_SLUG=_slug_for(ws_b),
        )
        assert resp.status_code == 200
        # The API-key auth must remain pinned to ws_a regardless of header.
        assert resp.json()["workspace_slug"] == _slug_for(ws_a)
