import base64
import hashlib
import hmac
import json
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from ninja.errors import HttpError

from apps.skills.execution_artifacts import prepare_execution_artifacts
from apps.skills.models import (
    SkillExecutionQuotaCounter,
    SkillExecutionRun,
    SkillExecutionSpec,
)

RETENTION_DAYS = 30
HIGH_APPROVAL_RISKS = {"high", "critical"}
TERMINAL_STATUSES = {
    SkillExecutionRun.StatusChoices.SUCCEEDED,
    SkillExecutionRun.StatusChoices.FAILED,
    SkillExecutionRun.StatusChoices.TIMEOUT,
    SkillExecutionRun.StatusChoices.CANCELLED,
}


def canonical_input_hash(inputs: dict) -> str:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def requires_execution_approval(skill) -> bool:
    version = skill.current_version
    metadata = version.koinoflow_metadata if version else {}
    if not isinstance(metadata, dict):
        return False
    return (
        bool(metadata.get("requires_human_approval"))
        or metadata.get("risk_level") in HIGH_APPROVAL_RISKS
    )


def validate_execution_inputs(inputs: dict, spec: SkillExecutionSpec):
    schema = spec.input_schema or {}
    if not schema:
        return
    try:
        from jsonschema import ValidationError, validate

        validate(instance=inputs, schema=schema)
    except ImportError:
        pass
    except ValidationError as exc:
        raise HttpError(400, f"Invalid execution input: {exc.message}") from exc

    required = schema.get("required") or []
    if isinstance(required, list):
        missing = [field for field in required if field not in inputs]
        if missing:
            raise HttpError(400, f"Missing required execution input(s): {', '.join(missing)}")

    properties = schema.get("properties") or {}
    if isinstance(properties, dict):
        allowed = set(properties)
        extra = sorted(set(inputs) - allowed)
        if schema.get("additionalProperties") is False and extra:
            raise HttpError(400, f"Unexpected execution input(s): {', '.join(extra)}")


def enforce_skill_quota(spec: SkillExecutionSpec):
    today = timezone.localdate()
    with transaction.atomic():
        counter, _created = SkillExecutionQuotaCounter.objects.select_for_update().get_or_create(
            workspace=spec.skill.department.team.workspace,
            skill=spec.skill,
            day=today,
            defaults={"run_count": 0},
        )
        if counter.run_count >= spec.max_runs_per_day:
            raise HttpError(429, "Daily execution limit reached for this skill")
        counter.run_count = F("run_count") + 1
        counter.save(update_fields=["run_count", "updated_at"])


def enforce_skill_concurrency(spec: SkillExecutionSpec):
    active_count = SkillExecutionRun.objects.filter(
        skill=spec.skill,
        status__in=[
            SkillExecutionRun.StatusChoices.QUEUED,
            SkillExecutionRun.StatusChoices.RUNNING,
        ],
    ).count()
    if active_count >= spec.max_concurrent_runs:
        raise HttpError(429, "Concurrent execution limit reached for this skill")


def _callback_secret() -> str:
    secret = getattr(settings, "SKILL_EXECUTION_CALLBACK_SECRET", "") or settings.SECRET_KEY
    return str(secret)


def issue_callback_token(run: SkillExecutionRun) -> str:
    expires_at = int(
        (timezone.now() + timedelta(seconds=run.spec.timeout_seconds + 300)).timestamp()
    )
    payload = {
        "run_id": str(run.id),
        "exp": expires_at,
    }
    encoded = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    signature = hmac.new(
        _callback_secret().encode("utf-8"),
        encoded.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


def validate_callback_token(token: str, run_id: str) -> bool:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(
        _callback_secret().encode("utf-8"),
        encoded.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False

    try:
        padded = encoded + ("=" * (-len(encoded) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False

    return payload.get("run_id") == str(run_id) and int(payload.get("exp", 0)) >= int(
        timezone.now().timestamp()
    )


def apply_execution_callback(
    run: SkillExecutionRun,
    *,
    status: str,
    output: dict | None = None,
    output_uri: str = "",
    logs_uri: str = "",
    error_message: str = "",
    resource_usage: dict | None = None,
):
    if run.status in TERMINAL_STATUSES:
        raise HttpError(409, "Execution run is already terminal")
    if status not in SkillExecutionRun.StatusChoices.values:
        raise HttpError(400, "Invalid execution status")
    if status == SkillExecutionRun.StatusChoices.PENDING_APPROVAL:
        raise HttpError(400, "Callback cannot set pending approval")

    update_fields = ["status", "updated_at"]
    run.status = status
    now = timezone.now()
    if status == SkillExecutionRun.StatusChoices.RUNNING and run.started_at is None:
        run.started_at = now
        update_fields.append("started_at")
    if status in TERMINAL_STATUSES:
        if run.started_at is None:
            run.started_at = now
            update_fields.append("started_at")
        run.finished_at = now
        update_fields.append("finished_at")
    if output is not None:
        run.output = output
        update_fields.append("output")
    if output_uri:
        run.output_uri = output_uri
        update_fields.append("output_uri")
    if logs_uri:
        run.logs_uri = logs_uri
        update_fields.append("logs_uri")
    if error_message:
        run.error_message = error_message[:4000]
        update_fields.append("error_message")
    if resource_usage is not None:
        run.resource_usage = resource_usage
        update_fields.append("resource_usage")
    run.save(update_fields=update_fields)


def dispatch_execution_run(run: SkillExecutionRun):
    backend = getattr(settings, "SKILL_EXECUTION_BACKEND", "record_only")
    now = timezone.now()

    if backend == "inline_echo":
        run.status = SkillExecutionRun.StatusChoices.SUCCEEDED
        run.started_at = now
        run.finished_at = now
        run.output = {
            "message": "Inline execution backend completed the run.",
            "inputs": run.inputs,
        }
        run.resource_usage = {"backend": backend}
        run.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "output",
                "resource_usage",
                "updated_at",
            ]
        )
        return

    if backend == "cloud_run_jobs":
        _dispatch_cloud_run_job(run)
        return

    run.status = SkillExecutionRun.StatusChoices.QUEUED
    run.external_job_name = f"cloud-run/jobs/koinoflow-skill-executor/executions/skill-run-{run.id}"
    run.resource_usage = {"backend": backend}
    run.save(
        update_fields=[
            "status",
            "external_job_name",
            "resource_usage",
            "updated_at",
        ]
    )


def _dispatch_cloud_run_job(run: SkillExecutionRun):
    project = getattr(settings, "SKILL_EXECUTION_GCP_PROJECT", "")
    location = getattr(settings, "SKILL_EXECUTION_GCP_LOCATION", "europe-west1")
    job = getattr(settings, "SKILL_EXECUTION_CLOUD_RUN_JOB", "koinoflow-skill-executor")
    if not project or not location or not job:
        raise HttpError(500, "Cloud Run skill execution is not configured")

    try:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
    except Exception as exc:
        raise HttpError(500, f"Could not authorize Cloud Run skill execution: {exc}") from exc

    spec = run.spec
    version_number = run.version.version_number if run.version_id else ""
    artifacts = prepare_execution_artifacts(run)
    base_url = getattr(settings, "SKILL_EXECUTION_PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        raise HttpError(500, "Skill execution callback base URL is not configured")
    callback_url = f"{base_url}/api/v1/skill-executions/{run.id}/callback"
    callback_token = issue_callback_token(run)
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/jobs/{job}:run"
    payload = {
        "overrides": {
            "containerOverrides": [
                {
                    "env": [
                        {"name": "KOINOFLOW_RUN_ID", "value": str(run.id)},
                        {"name": "KOINOFLOW_SKILL_ID", "value": str(run.skill_id)},
                        {"name": "KOINOFLOW_VERSION_NUMBER", "value": str(version_number)},
                        {
                            "name": "KOINOFLOW_ENTRYPOINT_PATH",
                            "value": spec.entrypoint_path if spec else "",
                        },
                        {"name": "KOINOFLOW_SKILL_PACKAGE_URI", "value": artifacts.package_uri},
                        {"name": "KOINOFLOW_INPUTS_URI", "value": artifacts.inputs_uri},
                        {"name": "KOINOFLOW_MANIFEST_URI", "value": artifacts.manifest_uri},
                        {"name": "KOINOFLOW_OUTPUT_URI", "value": artifacts.output_uri},
                        {"name": "KOINOFLOW_LOGS_URI", "value": artifacts.logs_uri},
                        {"name": "KOINOFLOW_CALLBACK_URL", "value": callback_url},
                        {"name": "KOINOFLOW_CALLBACK_TOKEN", "value": callback_token},
                    ]
                }
            ],
            "taskCount": 1,
            "timeout": f"{spec.timeout_seconds if spec else 30}s",
        }
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    if response.status_code >= 400:
        run.status = SkillExecutionRun.StatusChoices.FAILED
        run.error_message = response.text[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        raise HttpError(502, "Cloud Run skill execution dispatch failed")

    body = response.json()
    run.status = SkillExecutionRun.StatusChoices.QUEUED
    run.external_job_name = body.get("name", "")
    run.output_uri = artifacts.output_uri
    run.logs_uri = artifacts.logs_uri
    run.resource_usage = {
        "backend": "cloud_run_jobs",
        "package_uri": artifacts.package_uri,
        "inputs_uri": artifacts.inputs_uri,
        "manifest_uri": artifacts.manifest_uri,
    }
    run.save(
        update_fields=[
            "status",
            "external_job_name",
            "output_uri",
            "logs_uri",
            "resource_usage",
            "updated_at",
        ]
    )


def run_expiry():
    return timezone.now() + timedelta(days=RETENTION_DAYS)
