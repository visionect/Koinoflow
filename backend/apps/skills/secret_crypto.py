from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.fernet import Fernet
from django.conf import settings
from ninja.errors import HttpError


@dataclass(frozen=True)
class EncryptedSecret:
    wrapped_dek: bytes
    ciphertext: bytes
    kms_key_version: str


def _legacy_fernet() -> Fernet:
    key = getattr(settings, "CONNECTOR_ENCRYPTION_KEY", "")
    if not key:
        raise HttpError(500, "Connector encryption key is not configured")
    return Fernet(key.encode("utf-8"))


def _kms_client():
    try:
        from google.cloud import kms
    except ImportError as exc:
        raise HttpError(500, "google-cloud-kms is not installed") from exc
    return kms.KeyManagementServiceClient()


def _kms_encrypt(data_key: bytes) -> tuple[bytes, str]:
    key_name = getattr(settings, "SKILL_SECRET_KMS_KEY", "").strip()
    if not key_name:
        return b"", ""

    client = _kms_client()
    response = client.encrypt(request={"name": key_name, "plaintext": data_key})
    version = response.name or key_name
    return bytes(response.ciphertext), version


def _kms_decrypt(wrapped_dek: bytes) -> bytes:
    key_name = getattr(settings, "SKILL_SECRET_KMS_KEY", "").strip()
    if not key_name:
        raise HttpError(500, "Skill secret KMS key is not configured")
    client = _kms_client()
    response = client.decrypt(request={"name": key_name, "ciphertext": wrapped_dek})
    return bytes(response.plaintext)


def encrypt_secret_value(plaintext: str) -> EncryptedSecret:
    key_name = getattr(settings, "SKILL_SECRET_KMS_KEY", "").strip()
    if not key_name:
        token = _legacy_fernet().encrypt(plaintext.encode("utf-8"))
        return EncryptedSecret(wrapped_dek=b"", ciphertext=token, kms_key_version="")

    raw_dek = Fernet.generate_key()
    wrapped_dek, version = _kms_encrypt(raw_dek)
    ciphertext = Fernet(raw_dek).encrypt(plaintext.encode("utf-8"))
    return EncryptedSecret(
        wrapped_dek=wrapped_dek,
        ciphertext=ciphertext,
        kms_key_version=version,
    )


def decrypt_secret_value(*, wrapped_dek: bytes, ciphertext: bytes) -> str:
    if not ciphertext:
        return ""

    if wrapped_dek:
        raw_dek = _kms_decrypt(wrapped_dek)
        return Fernet(raw_dek).decrypt(ciphertext).decode("utf-8")

    return _legacy_fernet().decrypt(ciphertext).decode("utf-8")


def masked_secret_preview(value: str) -> str:
    data = value.encode("utf-8")
    if not data:
        return ""
    digest = base64.urlsafe_b64encode(data[:2] + data[-2:]).decode("ascii").rstrip("=")
    return f"***{digest}"
