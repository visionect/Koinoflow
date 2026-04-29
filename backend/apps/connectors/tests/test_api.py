import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client as DjangoTestClient
from ninja.testing import TestClient

from apps.connectors.enums import CandidateStatus, CredentialStatus
from apps.connectors.models import ConnectorCredential, SyncedPage
from apps.connectors.tests.factories import (
    CaptureCandidateFactory,
    ConnectorCredentialFactory,
    SyncedPageFactory,
)
from apps.orgs.models import Membership
from apps.orgs.tests.factories import MembershipFactory, WorkspaceFactory
from config.api import api


@pytest.fixture
def client():
    return TestClient(api)


@pytest.fixture
def workspace():
    return WorkspaceFactory()


@pytest.fixture
def admin_user(workspace):
    membership = MembershipFactory(workspace=workspace)
    return membership.user


def _auth_headers(user, workspace):
    return {"user": user, "workspace": workspace}


def _session_request_with_admin_membership(user, workspace):
    request = MagicMock()
    request.user = user
    request.workspace = workspace
    request.membership = Membership.objects.get(user=user, workspace=workspace)
    return request


@pytest.mark.django_db
class TestConfluenceConnect:
    def test_returns_redirect_url(self, admin_user, workspace):
        from apps.connectors.api import confluence_connect

        request = _session_request_with_admin_membership(admin_user, workspace)
        result = confluence_connect(request)
        assert "auth.atlassian.com" in result.redirect_url

    def test_redirect_url_contains_atlassian_host(self, admin_user, workspace):
        from apps.connectors.api import confluence_connect

        request = _session_request_with_admin_membership(admin_user, workspace)
        result = confluence_connect(request)

        assert "auth.atlassian.com" in result.redirect_url
        assert settings.ATLASSIAN_CLIENT_ID in result.redirect_url


@pytest.mark.django_db
class TestConfluenceCallback:
    def test_invalid_state_returns_400(self, client):
        resp = client.get("/v1/connectors/confluence/callback?code=abc&state=bad")
        assert resp.status_code == 400

    def test_expired_state_returns_400(self, client):
        resp = client.get(
            "/v1/connectors/confluence/callback?code=abc&state=some-workspace-id|expirednonce"
        )
        assert resp.status_code == 400

    def test_creates_credential_on_valid_callback(self, admin_user, workspace):
        from apps.connectors.api import confluence_callback

        nonce = "testvalidnonce123"
        cache.set(f"oauth_state:{nonce}", str(workspace.id), 600)

        mock_tokens = {
            "access_token": "at-token",
            "refresh_token": "rt-token",
            "expires_in": 3600,
        }
        mock_resources = [{"id": "cloud-123", "url": "https://test.atlassian.net"}]

        request = MagicMock()
        request.user = admin_user

        results_iter = iter([mock_tokens, mock_resources, "wh-1"])

        def fake_async_to_sync(_async_fn):
            def sync_wrapper(*_a, **_kw):
                return next(results_iter)

            return sync_wrapper

        with (
            patch("apps.connectors.api.async_to_sync", side_effect=fake_async_to_sync),
            patch("tasks.sync_backend.SyncBackend.enqueue") as mock_enqueue,
        ):
            confluence_callback(request, code="authcode", state=f"{workspace.id}|{nonce}")

        cred = ConnectorCredential.objects.get(workspace=workspace, provider="confluence")
        assert cred.cloud_id == "cloud-123"
        assert cred.status == CredentialStatus.ACTIVE
        mock_enqueue.assert_called_once()


@pytest.mark.django_db
class TestListConnectors:
    def test_returns_workspace_credentials_only(self, admin_user, workspace):
        from apps.connectors.api import list_connectors

        cred = ConnectorCredentialFactory(workspace=workspace)
        ConnectorCredentialFactory()  # different workspace

        request = MagicMock()
        request.user = admin_user

        request.workspace = workspace
        result = list_connectors(request)

        assert len(result) == 1
        assert result[0].id == str(cred.id)

    def test_excludes_disconnected(self, admin_user, workspace):
        from apps.connectors.api import list_connectors

        ConnectorCredentialFactory(workspace=workspace, status=CredentialStatus.DISCONNECTED)

        request = MagicMock()
        request.user = admin_user
        request.workspace = workspace
        result = list_connectors(request)

        assert result == []


@pytest.mark.django_db
class TestDisconnect:
    def test_sets_status_disconnected(self, admin_user, workspace):
        from apps.connectors.api import disconnect_connector

        cred = ConnectorCredentialFactory(workspace=workspace)

        request = _session_request_with_admin_membership(admin_user, workspace)
        disconnect_connector(request, credential_id=cred.id)

        cred.refresh_from_db()
        assert cred.status == CredentialStatus.DISCONNECTED
        assert cred.access_token == ""
        assert cred.refresh_token == ""


WEBHOOK_TEST_SECRET = "test-webhook-secret"


@pytest.mark.django_db
class TestWebhook:
    @pytest.fixture(autouse=True)
    def _set_webhook_secret(self, settings):
        settings.ATLASSIAN_WEBHOOK_SECRET = WEBHOOK_TEST_SECRET

    def _make_signature(self, payload: bytes) -> str:
        sig = hmac.new(WEBHOOK_TEST_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def test_valid_signature_processes_event(self, workspace):
        from apps.connectors.api import confluence_webhook

        cred = ConnectorCredentialFactory(workspace=workspace, cloud_id="cloud-xyz")

        payload = json.dumps(
            {
                "webhookEvent": "page_updated",
                "page": {"id": "987"},
                "baseUrl": cred.site_url,
            }
        ).encode()

        request = MagicMock()
        request.body = payload
        request.headers = {"X-Hub-Signature": self._make_signature(payload)}

        with (
            patch("tasks.sync_backend.SyncBackend.enqueue") as mock_enqueue,
            patch("apps.connectors.api._extract_cloud_id", return_value="cloud-xyz"),
        ):
            result = confluence_webhook(request)

        assert result == {"ok": True}
        mock_enqueue.assert_called_once_with(
            "confluence_sync_page",
            credential_id=str(cred.id),
            page_id="987",
        )

    def test_invalid_signature_returns_403(self, workspace):
        from ninja.errors import HttpError

        from apps.connectors.api import confluence_webhook

        payload = b'{"webhookEvent": "page_updated"}'
        request = MagicMock()
        request.body = payload
        request.headers = {"X-Hub-Signature": "sha256=invalidsignature"}

        with pytest.raises(HttpError) as exc_info:
            confluence_webhook(request)

        assert exc_info.value.status_code == 403

    def test_page_removed_deletes_synced_page(self, workspace):
        from apps.connectors.api import confluence_webhook

        cred = ConnectorCredentialFactory(workspace=workspace, cloud_id="cloud-del")
        page = SyncedPageFactory(credential=cred, external_id="page-to-delete")

        payload = json.dumps(
            {
                "webhookEvent": "page_removed",
                "page": {"id": "page-to-delete"},
                "baseUrl": cred.site_url,
            }
        ).encode()

        request = MagicMock()
        request.body = payload
        request.headers = {"X-Hub-Signature": self._make_signature(payload)}

        with patch("apps.connectors.api._extract_cloud_id", return_value="cloud-del"):
            confluence_webhook(request)

        assert not SyncedPage.objects.filter(id=page.id).exists()


@pytest.mark.django_db
class TestCaptureStats:
    def test_capture_stats_no_connector(self, admin_membership):
        client = DjangoTestClient()
        client.force_login(admin_membership.user)

        resp = client.get("/api/v1/connectors/capture-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_connector"] is False
        assert data["synced_pages"] == 0
        assert data["candidates_extracted"] == 0
        assert data["candidates_promoted"] == 0

    def test_capture_stats_with_data(self, admin_membership):
        ws = admin_membership.workspace
        cred = ConnectorCredentialFactory(workspace=ws)

        SyncedPageFactory(credential=cred, external_id="p1")
        SyncedPageFactory(credential=cred, external_id="p2")
        SyncedPageFactory(credential=cred, external_id="p3")

        CaptureCandidateFactory(credential=cred, slug="c1", status=CandidateStatus.PENDING)
        CaptureCandidateFactory(credential=cred, slug="c2", status=CandidateStatus.PROMOTED)
        CaptureCandidateFactory(credential=cred, slug="c3", status=CandidateStatus.DISMISSED)

        client = DjangoTestClient()
        client.force_login(admin_membership.user)

        resp = client.get("/api/v1/connectors/capture-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_connector"] is True
        assert data["synced_pages"] == 3
        assert data["candidates_extracted"] == 2  # excludes dismissed
        assert data["candidates_promoted"] == 1
