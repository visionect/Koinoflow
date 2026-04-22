import pytest

from apps.connectors.enums import CredentialStatus
from apps.connectors.models import decrypt_token, encrypt_token
from apps.connectors.tests.factories import ConnectorCredentialFactory


@pytest.mark.django_db
class TestEncryption:
    def test_roundtrip(self):
        plaintext = "secret-access-token-abc123"
        assert decrypt_token(encrypt_token(plaintext)) == plaintext

    def test_encrypted_differs_from_plaintext(self):
        plaintext = "my-token"
        assert encrypt_token(plaintext) != plaintext

    def test_get_access_token_decrypts(self):
        cred = ConnectorCredentialFactory()
        assert cred.get_access_token() == "test-access-token"

    def test_get_refresh_token_decrypts(self):
        cred = ConnectorCredentialFactory()
        assert cred.get_refresh_token() == "test-refresh-token"

    def test_set_access_token_encrypts(self):
        cred = ConnectorCredentialFactory()
        cred.set_access_token("new-token")
        assert cred.get_access_token() == "new-token"
        assert cred.access_token != "new-token"


@pytest.mark.django_db
class TestConnectorCredentialConstraints:
    def test_unique_per_workspace_provider(self):
        cred = ConnectorCredentialFactory()
        with pytest.raises(Exception):
            ConnectorCredentialFactory(
                workspace=cred.workspace,
                provider=cred.provider,
                status=CredentialStatus.ACTIVE,
            )

    def test_disconnected_allows_new_active(self):
        cred = ConnectorCredentialFactory(status=CredentialStatus.DISCONNECTED)
        # A new active credential for the same workspace+provider should be allowed
        new_cred = ConnectorCredentialFactory(
            workspace=cred.workspace,
            provider=cred.provider,
            status=CredentialStatus.ACTIVE,
        )
        assert new_cred.id != cred.id
