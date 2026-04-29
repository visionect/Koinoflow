from unittest.mock import MagicMock, patch

from apps.skills import ai_edit


class FakeAnthropic:
    def __init__(self):
        self.kwargs = None

        def vertex_client(**kwargs):
            self.kwargs = kwargs
            return object()

        self.AnthropicVertex = vertex_client

    AnthropicVertex: object


def test_anthropic_vertex_client_uses_configured_service_account(settings):
    settings.VERTEX_CLIENT_PROJECT_ID = "visionect-gce-infra"
    settings.VERTEX_CLIENT_PRIVATE_KEY_ID = "key-id"
    settings.VERTEX_CLIENT_PRIVATE_KEY = (
        "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"
    )
    settings.VERTEX_CLIENT_EMAIL = "vertex@example.iam.gserviceaccount.com"
    settings.VERTEX_CLIENT_ID = "client-id"
    settings.VERTEX_CLIENT_CERT_URL = "https://example.com/cert"

    fake_anthropic = FakeAnthropic()
    credentials = MagicMock(token="sponsored-token")

    with (
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            return_value=credentials,
        ) as mock_from_info,
        patch("google.auth.transport.requests.Request") as mock_request,
    ):
        client = ai_edit._build_anthropic_vertex_client(
            fake_anthropic,
            project="visionect-gce-infra",
            location="global",
        )

    assert client is not None
    assert fake_anthropic.kwargs == {
        "project_id": "visionect-gce-infra",
        "region": "global",
        "access_token": "sponsored-token",
    }
    mock_from_info.assert_called_once()
    credentials.refresh.assert_called_once_with(mock_request.return_value)


def test_resolve_vertex_project_falls_back_to_runtime_project(settings):
    settings.VERTEX_PROJECT_ID = "koinoflow-infra"
    settings.VERTEX_CLIENT_PROJECT_ID = "visionect-gce-infra"
    settings.VERTEX_CLIENT_PRIVATE_KEY_ID = ""

    assert ai_edit._resolve_vertex_project(settings) == "koinoflow-infra"
