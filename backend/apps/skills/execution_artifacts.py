import io
import json
import posixpath
import zipfile
from dataclasses import dataclass

from django.conf import settings
from ninja.errors import HttpError

from apps.skills.files import file_bytes, resolve_files
from apps.skills.models import SkillExecutionRun


@dataclass(frozen=True)
class ExecutionArtifacts:
    package_uri: str
    inputs_uri: str
    manifest_uri: str
    output_uri: str
    logs_uri: str


def normalize_gs_bucket(raw: str) -> str:
    bucket = (raw or "").strip()
    if bucket.startswith("gs://"):
        bucket = bucket[5:]
    return bucket.rstrip("/")


def gs_uri(bucket: str, blob_name: str) -> str:
    return f"gs://{bucket}/{blob_name}"


def split_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")
    bucket, _, blob = uri[5:].partition("/")
    if not bucket or not blob:
        raise ValueError("GCS URI must include bucket and object path")
    return bucket, blob


def _storage_client():
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise HttpError(500, "google-cloud-storage is not installed") from exc
    return storage.Client()


def _upload_bytes(uri: str, data: bytes, content_type: str):
    bucket_name, blob_name = split_gs_uri(uri)
    client = _storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)


def _safe_zip_path(path: str) -> str:
    normalized = posixpath.normpath(path)
    if (
        normalized in {"", "."}
        or normalized == ".."
        or normalized.startswith("../")
        or normalized.startswith("/")
        or "\\" in path
    ):
        raise HttpError(400, f"Invalid execution file path: {path}")
    return normalized


def build_execution_manifest(run: SkillExecutionRun) -> dict:
    spec = run.spec
    version = run.version
    if spec is None or version is None:
        raise HttpError(400, "Execution run is missing spec or version")
    return {
        "run_id": str(run.id),
        "skill_id": str(run.skill_id),
        "skill_slug": run.skill.slug,
        "version_number": version.version_number,
        "runtime": spec.runtime,
        "latency_class": spec.latency_class,
        "entrypoint_path": spec.entrypoint_path,
        "input_schema": spec.input_schema or {},
        "output_schema": spec.output_schema or {},
        "secret_refs": [
            {
                "name": ref.name,
                "scope": ref.scope,
                "required": bool(ref.required),
            }
            for ref in spec.secret_refs.all().order_by("name")
        ],
        "network": {
            "policy": spec.network_policy,
            "allowed": spec.allowed_egress or [],
        },
        "limits": {
            "timeout_seconds": spec.timeout_seconds,
            "memory_mb": spec.memory_mb,
            "max_output_bytes_inline": spec.max_output_bytes_inline,
        },
    }


def _build_skill_package(run: SkillExecutionRun) -> bytes:
    spec = run.spec
    version = run.version
    if spec is None or version is None:
        raise HttpError(400, "Execution run is missing spec or version")

    files = resolve_files(run.skill_id, version.version_number)
    entrypoint = files.get(spec.entrypoint_path)
    if entrypoint is None:
        raise HttpError(400, f"Execution entrypoint not found: {spec.entrypoint_path}")
    if entrypoint.file_type not in {"python", "text"}:
        raise HttpError(400, "Execution entrypoint must be a Python/text file")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, file in sorted(files.items()):
            zf.writestr(_safe_zip_path(path), file_bytes(file))
    return archive.getvalue()


def prepare_execution_artifacts(run: SkillExecutionRun) -> ExecutionArtifacts:
    bucket = normalize_gs_bucket(getattr(settings, "SKILL_EXECUTION_RUNS_BUCKET", ""))
    if not bucket:
        raise HttpError(500, "Skill execution runs bucket is not configured")

    prefix = f"runs/{run.id}"
    artifacts = ExecutionArtifacts(
        package_uri=gs_uri(bucket, f"{prefix}/skill.zip"),
        inputs_uri=gs_uri(bucket, f"{prefix}/inputs.json"),
        manifest_uri=gs_uri(bucket, f"{prefix}/manifest.json"),
        output_uri=gs_uri(bucket, f"{prefix}/output.json"),
        logs_uri=gs_uri(bucket, f"{prefix}/logs.txt"),
    )
    manifest = build_execution_manifest(run)

    _upload_bytes(artifacts.package_uri, _build_skill_package(run), "application/zip")
    _upload_bytes(
        artifacts.inputs_uri,
        json.dumps(run.inputs, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        "application/json",
    )
    _upload_bytes(
        artifacts.manifest_uri,
        json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        "application/json",
    )
    return artifacts
