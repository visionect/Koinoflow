"""Resolve external vault references at execution time.

A skill secret can be stored in two ways:

1. As an encrypted value in our database (envelope-encrypted via KMS or
   Fernet — see ``secret_crypto``).
2. As a *vault reference* — a non-sensitive pointer to a secret in an
   external vault that the workspace already operates. The actual secret
   value is fetched at run time from inside the executor and never
   persisted by Koinoflow.

For vault references, the only thing stored in our database — and the
only thing visible to a database attacker or to a Koinoflow operator —
is the reference string itself (e.g. ``gcp-sm://my-project/my-secret``).
The plaintext is read directly from the user's vault by the executor.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ninja.errors import HttpError

_VAULT_REF_RE = re.compile(r"^(?P<scheme>[a-z][a-z0-9-]*)://(?P<path>\S+)$")
_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

KNOWN_SCHEMES = ("env", "gcp-sm")


@dataclass(frozen=True)
class VaultRef:
    scheme: str
    path: str

    def __str__(self) -> str:
        return f"{self.scheme}://{self.path}"


def parse_vault_ref(ref: str) -> VaultRef:
    """Validate ``ref`` and return its parsed scheme + path.

    Raises ``HttpError(400)`` for any malformed or unsupported reference.
    """
    if not isinstance(ref, str) or not ref.strip():
        raise HttpError(400, "Vault reference must be a non-empty string.")
    match = _VAULT_REF_RE.match(ref.strip())
    if not match:
        raise HttpError(
            400,
            "Vault reference must look like 'scheme://path' "
            "(e.g. 'gcp-sm://my-project/my-secret').",
        )
    scheme = match.group("scheme")
    if scheme not in KNOWN_SCHEMES:
        raise HttpError(
            400,
            f"Unsupported vault scheme '{scheme}'. Supported schemes: {', '.join(KNOWN_SCHEMES)}.",
        )
    return VaultRef(scheme=scheme, path=match.group("path"))


def resolve_vault_ref(ref: str) -> str:
    """Fetch the plaintext secret behind ``ref`` from its external vault.

    The returned string is intended to be injected straight into the
    executor's environment for the duration of one run; callers must
    never persist it.
    """
    parsed = parse_vault_ref(ref)
    if parsed.scheme == "env":
        return _resolve_env(parsed.path)
    if parsed.scheme == "gcp-sm":
        return _resolve_gcp_sm(parsed.path)
    raise HttpError(500, f"No resolver registered for scheme '{parsed.scheme}'.")


def _resolve_env(name: str) -> str:
    if not _ENV_VAR_RE.match(name):
        raise HttpError(400, f"Invalid env-var name in vault reference: '{name}'.")
    value = os.environ.get(name)
    if value is None:
        raise HttpError(
            502,
            f"Vault reference 'env://{name}' could not be resolved: "
            "env var not set on the executor.",
        )
    return value


def _resolve_gcp_sm(path: str) -> str:
    project, secret_id, version = _parse_gcp_sm_path(path)
    try:
        from google.cloud import secretmanager
    except ImportError as exc:  # pragma: no cover - surfaced to operator
        raise HttpError(
            500,
            "google-cloud-secret-manager is not installed on the executor; "
            "cannot resolve gcp-sm:// references.",
        ) from exc

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{secret_id}/versions/{version}"
    try:
        response = client.access_secret_version(request={"name": name})
    except Exception as exc:  # pragma: no cover - depends on GCP
        import logging

        logging.getLogger(__name__).exception(
            "Failed to fetch gcp-sm secret '%s' from project '%s'", secret_id, project
        )
        raise HttpError(
            502,
            "Failed to fetch secret from Google Cloud Secret Manager.",
        ) from exc
    return response.payload.data.decode("utf-8")


def _parse_gcp_sm_path(path: str) -> tuple[str, str, str]:
    parts = path.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HttpError(
            400,
            "gcp-sm reference must be 'project/secret' or 'project/secret@version'.",
        )
    project, rest = parts
    if "@" in rest:
        secret_id, version = rest.rsplit("@", 1)
    else:
        secret_id, version = rest, "latest"
    if not secret_id or not version:
        raise HttpError(400, "gcp-sm reference is missing secret name or version.")
    return project, secret_id, version
