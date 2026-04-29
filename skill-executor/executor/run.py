import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests
from google.cloud import storage
from jsonschema import validate

SECRET_RE = re.compile(r"(api[_-]?key|token|secret|password)", re.IGNORECASE)
TERMINAL_FAILURE_STATUS = "failed"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _split_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got {uri}")
    bucket, _, blob = uri[5:].partition("/")
    if not bucket or not blob:
        raise ValueError(f"Invalid GCS URI: {uri}")
    return bucket, blob


def _download_bytes(client: storage.Client, uri: str) -> bytes:
    bucket_name, blob_name = _split_gs_uri(uri)
    return client.bucket(bucket_name).blob(blob_name).download_as_bytes()


def _upload_text(client: storage.Client, uri: str, text: str, content_type: str):
    bucket_name, blob_name = _split_gs_uri(uri)
    client.bucket(bucket_name).blob(blob_name).upload_from_string(text, content_type=content_type)


def _safe_extract(zip_path: Path, destination: Path):
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            if not str(target).startswith(str(destination.resolve())):
                raise RuntimeError(f"Unsafe path in skill package: {member.filename}")
        zf.extractall(destination)


def _scrub_logs(logs: str) -> str:
    scrubbed_lines = []
    for line in logs.splitlines():
        if SECRET_RE.search(line):
            scrubbed_lines.append("[scrubbed potentially sensitive log line]")
        else:
            scrubbed_lines.append(line)
    return "\n".join(scrubbed_lines)


def _callback(callback_url: str, token: str, payload: dict[str, Any]):
    response = requests.post(
        callback_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def main() -> int:
    run_id = _required_env("KOINOFLOW_RUN_ID")
    package_uri = _required_env("KOINOFLOW_SKILL_PACKAGE_URI")
    inputs_uri = _required_env("KOINOFLOW_INPUTS_URI")
    manifest_uri = _required_env("KOINOFLOW_MANIFEST_URI")
    output_uri = _required_env("KOINOFLOW_OUTPUT_URI")
    logs_uri = _required_env("KOINOFLOW_LOGS_URI")
    callback_url = _required_env("KOINOFLOW_CALLBACK_URL")
    callback_token = _required_env("KOINOFLOW_CALLBACK_TOKEN")

    client = storage.Client()

    try:
        _callback(
            callback_url,
            callback_token,
            {"status": "running", "resource_usage": {"executor": "python"}},
        )
    except Exception:
        # The terminal callback below is the important one. Keep running if the
        # best-effort running update cannot be delivered.
        pass

    try:
        with tempfile.TemporaryDirectory(prefix=f"koinoflow-{run_id}-") as tmp:
            tmp_path = Path(tmp)
            package_path = tmp_path / "skill.zip"
            workdir = tmp_path / "skill"
            workdir.mkdir()

            package_path.write_bytes(_download_bytes(client, package_uri))
            inputs = json.loads(_download_bytes(client, inputs_uri).decode("utf-8"))
            manifest = json.loads(_download_bytes(client, manifest_uri).decode("utf-8"))
            validate(instance=inputs, schema=manifest.get("input_schema") or {})

            _safe_extract(package_path, workdir)
            entrypoint = (workdir / manifest["entrypoint_path"]).resolve()
            if not str(entrypoint).startswith(str(workdir.resolve())) or not entrypoint.is_file():
                raise RuntimeError("Execution entrypoint is missing or outside the skill package")

            timeout_seconds = int(manifest.get("limits", {}).get("timeout_seconds") or 30)
            process = subprocess.run(
                [sys.executable, str(entrypoint)],
                input=json.dumps(inputs),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                cwd=str(workdir),
                env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"},
                check=False,
            )

            logs = _scrub_logs(process.stderr)
            _upload_text(client, logs_uri, logs, "text/plain")

            if process.returncode != 0:
                _callback(
                    callback_url,
                    callback_token,
                    {
                        "status": TERMINAL_FAILURE_STATUS,
                        "logs_uri": logs_uri,
                        "error_message": f"Skill exited with code {process.returncode}",
                        "resource_usage": {"exit_code": process.returncode},
                    },
                )
                return process.returncode

            try:
                output = json.loads(process.stdout or "{}")
            except json.JSONDecodeError as exc:
                _callback(
                    callback_url,
                    callback_token,
                    {
                        "status": TERMINAL_FAILURE_STATUS,
                        "logs_uri": logs_uri,
                        "error_message": f"Skill stdout was not valid JSON: {exc}",
                        "resource_usage": {"exit_code": process.returncode},
                    },
                )
                return 1

            output_text = json.dumps(output, separators=(",", ":"), sort_keys=True)
            _upload_text(client, output_uri, output_text, "application/json")
            max_inline = int(manifest.get("limits", {}).get("max_output_bytes_inline") or 32768)
            inline_output = output if len(output_text.encode("utf-8")) <= max_inline else None
            _callback(
                callback_url,
                callback_token,
                {
                    "status": "succeeded",
                    "output": inline_output,
                    "output_uri": output_uri,
                    "logs_uri": logs_uri,
                    "resource_usage": {"exit_code": process.returncode},
                },
            )
            return 0
    except subprocess.TimeoutExpired:
        _callback(
            callback_url,
            callback_token,
            {
                "status": "timeout",
                "logs_uri": logs_uri,
                "error_message": "Skill execution timed out",
            },
        )
        return 124
    except Exception as exc:
        try:
            _callback(
                callback_url,
                callback_token,
                {
                    "status": TERMINAL_FAILURE_STATUS,
                    "logs_uri": logs_uri,
                    "error_message": str(exc),
                },
            )
        finally:
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
