import pytest
from django.test import Client

from apps.orgs.models import ApiKey


@pytest.mark.django_db
class TestCreateApiKey:
    def test_create_api_key_returns_raw_key(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/api-keys",
            data={"label": "My Key"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "My Key"
        assert data["raw_key"].startswith("kf_")
        assert "key_prefix" in data
        assert ApiKey.objects.filter(workspace=admin_membership.workspace).count() == 1


@pytest.mark.django_db
class TestListApiKeys:
    def test_list_api_keys_hides_raw_key(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="Test Key",
        )

        resp = auth_client.get("/api/v1/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
        assert "raw_key" not in data["items"][0]
        assert data["items"][0]["key_prefix"] == key_prefix

    def test_list_api_keys_admin_only(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.get("/api/v1/api-keys")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestRevokeApiKey:
    def test_revoke_api_key(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        raw_key, key_hash, key_prefix = ApiKey.generate()
        api_key = ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="To Revoke",
        )

        resp = auth_client.delete(f"/api/v1/api-keys/{api_key.id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        api_key.refresh_from_db()
        assert api_key.is_active is False
