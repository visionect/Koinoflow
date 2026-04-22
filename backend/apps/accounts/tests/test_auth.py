from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.models import ApiKey
from apps.orgs.tests.factories import CoreSettingsFactory, MembershipFactory, WorkspaceFactory


@pytest.mark.django_db
class TestMeEndpoint:
    def test_me_unauthenticated(self):
        client = Client()
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated_no_workspace(self):
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == user.email
        assert data["workspace_slug"] is None
        assert data["role"] is None

    def test_me_authenticated_with_workspace(self):
        membership = MembershipFactory(role=RoleChoices.ADMIN)
        client = Client()
        client.force_login(membership.user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == membership.user.email
        from apps.orgs.models import CoreSlug

        expected_slug = CoreSlug.objects.get(
            entity_type=EntityType.WORKSPACE, entity_id=membership.workspace.id
        ).slug
        assert data["workspace_slug"] == expected_slug
        assert data["role"] == RoleChoices.ADMIN


@pytest.mark.django_db
class TestApiKeyAuth:
    def _make_key(self, workspace=None, **overrides):
        ws = workspace or WorkspaceFactory()
        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test-key",
            **overrides,
        )
        return raw_key, ws

    def test_api_key_auth_valid(self):
        raw_key, ws = self._make_key()
        client = Client()
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        from apps.orgs.models import CoreSlug

        expected_slug = CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=ws.id).slug
        assert data["workspace_slug"] == expected_slug
        assert data["user"] is None

    def test_api_key_auth_expired(self):
        raw_key, _ = self._make_key(expires_at=timezone.now() - timedelta(hours=1))
        client = Client()
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 401

    def test_api_key_auth_revoked(self):
        raw_key, _ = self._make_key(is_active=False)
        client = Client()
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 401

    def test_api_key_auth_invalid(self):
        client = Client()
        resp = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION="Bearer kf_completely_wrong_key",
        )
        assert resp.status_code == 401

    def test_api_key_sets_workspace_on_request(self, api_client):
        """After API key auth, request.workspace is the key's workspace."""
        ws = WorkspaceFactory()
        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="ws-check",
        )
        resp = api_client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 200
        from apps.orgs.models import CoreSlug

        expected = CoreSlug.objects.get(entity_type=EntityType.WORKSPACE, entity_id=ws.id).slug
        assert resp.json()["workspace_slug"] == expected

    def test_api_key_rejected_when_workspace_api_access_disabled(self):
        ws = WorkspaceFactory()
        CoreSettingsFactory(workspace=ws, team=None, department=None, enable_api_access=False)
        raw_key, _ = self._make_key(workspace=ws)
        client = Client()
        resp = client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        assert resp.status_code == 401

    def test_api_key_allowed_when_workspace_api_access_enabled(self):
        ws = WorkspaceFactory()
        CoreSettingsFactory(workspace=ws, team=None, department=None, enable_api_access=True)
        raw_key, _ = self._make_key(workspace=ws)
        client = Client()
        resp = client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        assert resp.status_code == 200

    def test_api_key_allowed_when_no_workspace_settings_exist(self):
        raw_key, _ = self._make_key()
        client = Client()
        resp = client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        assert resp.status_code == 200
