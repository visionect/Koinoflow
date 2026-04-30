"""Unit tests for the secret_vault module.

Tests parse_vault_ref, resolve_vault_ref, _resolve_env, and
_resolve_gcp_sm in isolation (no Django database required).
"""

import pytest
from ninja.errors import HttpError

from apps.skills.secret_vault import (
    KNOWN_SCHEMES,
    _parse_gcp_sm_path,
    _resolve_env,
    parse_vault_ref,
    resolve_vault_ref,
)


class TestParseVaultRef:
    def test_parses_gcp_sm_reference(self):
        ref = parse_vault_ref("gcp-sm://my-project/my-secret")
        assert ref.scheme == "gcp-sm"
        assert ref.path == "my-project/my-secret"

    def test_parses_env_reference(self):
        ref = parse_vault_ref("env://MY_VAR")
        assert ref.scheme == "env"
        assert ref.path == "MY_VAR"

    def test_rejects_empty_string(self):
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("")
        assert exc_info.value.status_code == 400

    def test_rejects_whitespace_only(self):
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("   ")
        assert exc_info.value.status_code == 400

    def test_rejects_none(self):
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref(None)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 400

    def test_rejects_missing_scheme(self):
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("just-a-path")
        assert exc_info.value.status_code == 400
        assert "scheme://path" in exc_info.value.message.lower()

    def test_rejects_uppercase_scheme(self):
        """Schemes must start with a lowercase letter per the regex."""
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("GCP-SM://project/secret")
        assert exc_info.value.status_code == 400

    def test_rejects_unsupported_scheme(self):
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("vault://some/path")
        assert exc_info.value.status_code == 400
        assert "gcp-sm" in exc_info.value.message
        assert "env" in exc_info.value.message

    def test_rejects_scheme_ending_with_digit(self):
        """Regex requires scheme to start with [a-z] then [a-z0-9-]*."""
        with pytest.raises(HttpError) as exc_info:
            parse_vault_ref("1http://host")
        assert exc_info.value.status_code == 400

    def test_strips_leading_trailing_whitespace(self):
        ref = parse_vault_ref("  gcp-sm://project/secret  ")
        assert ref.scheme == "gcp-sm"
        assert ref.path == "project/secret"

    def test_known_schemes_are_complete(self):
        assert set(KNOWN_SCHEMES) == {"env", "gcp-sm"}


class TestResolveVaultRef:
    def test_resolve_env_success(self, monkeypatch):
        monkeypatch.setenv("TEST_SECRET_KEY", "the-actual-value")
        value = resolve_vault_ref("env://TEST_SECRET_KEY")
        assert value == "the-actual-value"

    def test_resolve_env_missing_raises(self):
        with pytest.raises(HttpError) as exc_info:
            resolve_vault_ref("env://THIS_VAR_DOES_NOT_EXIST_AT_ALL")
        assert exc_info.value.status_code == 502
        assert "not set on the executor" in exc_info.value.message

    def test_resolve_env_invalid_name_raises(self):
        """Env var names in vault refs must match ^[A-Z][A-Z0-9_]*$."""
        with pytest.raises(HttpError) as exc_info:
            resolve_vault_ref("env://invalid-name-with-dashes")
        assert exc_info.value.status_code == 400
        assert "Invalid env-var name" in exc_info.value.message

    def test_resolve_gcp_sm_integration(self, monkeypatch):
        """Integration-style test: mock the GCP client entirely."""
        import sys

        mock_payload = type("MockPayload", (), {"data": b"secret-from-gcp"})()
        mock_response = type("MockResponse", (), {"payload": mock_payload})()
        mock_client = type(
            "MockClient",
            (),
            {"access_secret_version": staticmethod(lambda request: mock_response)},
        )

        mock_sm = type("MockSM", (), {"SecretManagerServiceClient": mock_client})()
        mock_google_cloud = type("MockCloud", (), {"secretmanager": mock_sm})()
        mock_google = type("MockGoogle", (), {"cloud": mock_google_cloud})()

        monkeypatch.setitem(sys.modules, "google", mock_google)
        monkeypatch.setitem(sys.modules, "google.cloud", mock_google_cloud)
        monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", mock_sm)

        value = resolve_vault_ref("gcp-sm://my-project/my-secret")
        assert value == "secret-from-gcp"

    def test_resolve_unsupported_scheme_raises(self, monkeypatch):
        monkeypatch.setattr("apps.skills.secret_vault.KNOWN_SCHEMES", ("env",))

        with pytest.raises(HttpError) as exc_info:
            resolve_vault_ref("gcp-sm://project/secret")
        assert exc_info.value.status_code == 400
        assert "gcp-sm" in exc_info.value.message


class TestParseGcpSmPath:
    def test_parses_basic_path(self):
        project, secret_id, version = _parse_gcp_sm_path("my-project/my-secret")
        assert project == "my-project"
        assert secret_id == "my-secret"
        assert version == "latest"

    def test_parses_path_with_version(self):
        project, secret_id, version = _parse_gcp_sm_path("my-project/my-secret@5")
        assert project == "my-project"
        assert secret_id == "my-secret"
        assert version == "5"

    def test_rejects_missing_project(self):
        with pytest.raises(HttpError) as exc_info:
            _parse_gcp_sm_path("/my-secret")
        assert exc_info.value.status_code == 400

    def test_rejects_missing_secret(self):
        with pytest.raises(HttpError) as exc_info:
            _parse_gcp_sm_path("my-project/")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_string(self):
        with pytest.raises(HttpError) as exc_info:
            _parse_gcp_sm_path("")
        assert exc_info.value.status_code == 400

    def test_rejects_single_segment(self):
        with pytest.raises(HttpError) as exc_info:
            _parse_gcp_sm_path("my-project")
        assert exc_info.value.status_code == 400

    def test_version_after_double_at_uses_last(self):
        """If path contains multiple @, rsplit takes the last one."""
        project, secret_id, version = _parse_gcp_sm_path("proj/my-secret@1@2")
        assert secret_id == "my-secret@1"
        assert version == "2"


class TestResolveEnv:
    def test_returns_value_for_existing_var(self, monkeypatch):
        monkeypatch.setenv("DEEP_NESTED_VAR", "deep-value")
        assert _resolve_env("DEEP_NESTED_VAR") == "deep-value"

    def test_returns_empty_string_var(self, monkeypatch):
        """An env var set to empty string is a valid value."""
        monkeypatch.setenv("EMPTY_VAR", "")
        assert _resolve_env("EMPTY_VAR") == ""

    def test_rejects_lowercase_var_name(self):
        with pytest.raises(HttpError) as exc_info:
            _resolve_env("lowercase_name")
        assert exc_info.value.status_code == 400

    def test_rejects_var_starting_with_digit(self):
        with pytest.raises(HttpError) as exc_info:
            _resolve_env("1BAD_VAR")
        assert exc_info.value.status_code == 400

    def test_rejects_var_with_special_chars(self):
        with pytest.raises(HttpError) as exc_info:
            _resolve_env("VAR-WITH-DASHES")
        assert exc_info.value.status_code == 400
