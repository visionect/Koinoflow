import base64
import binascii
import difflib
import hashlib
import io
import logging
import mimetypes
import posixpath
import re
import zipfile
from datetime import timedelta
from typing import Literal

import yaml
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from ninja import Field, File, Router, Schema, Status, UploadedFile
from ninja.errors import HttpError
from pgvector.django import CosineDistance

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import (
    apply_api_key_scope,
    apply_membership_scope,
    apply_oauth_connection_scope,
    check_skill_write,
    require_role,
)
from apps.common.throttles import (
    CreateAuthThrottle,
    ExecutionCallbackThrottle,
    ImportThrottle,
    MutationThrottle,
    ReadThrottle,
)
from apps.orgs.api import UserBriefOut, _user_brief
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.models import SYSTEM_KIND_AGENTS, Membership, get_effective_settings
from apps.skills.discovery import (
    VertexEmbeddingClient,
    get_embedding_config,
    queue_skill_discovery_embedding,
)
from apps.skills.discovery import (
    normalize_metadata as normalize_discovery_metadata,
)
from apps.skills.enums import StatusChoices, VisibilityChoices
from apps.skills.execution import (
    TERMINAL_STATUSES,
    apply_execution_callback,
    canonical_input_hash,
    dispatch_execution_run,
    enforce_skill_concurrency,
    enforce_skill_quota,
    fetch_run_secret_values,
    requires_execution_approval,
    run_expiry,
    validate_callback_token,
    validate_execution_inputs,
    validate_secret_fetch_token,
)
from apps.skills.files import (
    compute_file_delta,
    detect_file_type,
    file_bytes,
    is_text_file,
    resolve_file_list,
    resolve_files,
)
from apps.skills.models import (
    Skill,
    SkillExecutionRun,
    SkillExecutionSpec,
    SkillSecretDeclaration,
    SkillSecretValue,
    SkillVersion,
    VersionFile,
)
from apps.skills.sanitize import (
    sanitize_content_md,
    sanitize_frontmatter,
)
from apps.skills.secret_crypto import encrypt_secret_value
from apps.skills.secret_vault import parse_vault_ref

logger = logging.getLogger(__name__)

router = Router(tags=["skills"])

DiscoveryEmbeddingStatus = Literal["not_applicable", "pending", "ready"]

VERSION_FILE_TYPE_PATTERN = (
    r"^(python|markdown|html|yaml|json|javascript|typescript|shell|image|pdf|binary|text|other)$"
)
MAX_SKILL_IMPORT_BYTES = 2 * 1024 * 1024
MAX_SUPPORT_FILE_BYTES = 1 * 1024 * 1024
TEXT_FILE_TYPES = {
    "python",
    "markdown",
    "html",
    "yaml",
    "json",
    "javascript",
    "typescript",
    "shell",
    "text",
}


# ── Schemas ──────────────────────────────────────────────────────────────


class VersionFileOut(Schema):
    id: str
    path: str
    file_type: str
    mime_type: str
    encoding: str
    size_bytes: int


class VersionFileDetailOut(VersionFileOut):
    content: str | None = None
    content_base64: str | None = None


class VersionFileIn(Schema):
    path: str = Field(pattern=r"^[a-zA-Z0-9_\-./]+$", max_length=500)
    content: str | None = None
    content_base64: str | None = None
    file_type: str = Field(default="text", pattern=VERSION_FILE_TYPE_PATTERN)
    mime_type: str | None = Field(default=None, max_length=100)
    encoding: str | None = Field(default=None, max_length=20)


class DiffHunk(Schema):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]


class FileDiffEntry(Schema):
    path: str
    status: str  # "added" | "modified" | "deleted"
    old_size: int | None
    new_size: int | None
    hunks: list[DiffHunk] | None = None


class FileDiffOut(Schema):
    old_version_number: int
    new_version_number: int
    entries: list[FileDiffEntry]


RiskLevel = Literal["low", "medium", "high", "critical"]


class KoinoflowMetadata(Schema):
    """Koinoflow-native process metadata.

    Separate from frontmatter_yaml (which preserves Claude-compat fields silently).
    These fields are MCP-exposed to shape AI behavior but are never written to
    exported SKILL.md.
    """

    retrieval_keywords: list[str] = []
    risk_level: RiskLevel | None = None
    requires_human_approval: bool = False
    prerequisites: list[str] = []
    audience: list[str] = []


def _empty_metadata_dict() -> dict:
    return {
        "retrieval_keywords": [],
        "risk_level": None,
        "requires_human_approval": False,
        "prerequisites": [],
        "audience": [],
    }


def _normalize_metadata(raw) -> dict:
    """Coerce stored metadata to the canonical shape with sane defaults."""
    result = _empty_metadata_dict()
    if not isinstance(raw, dict):
        return result

    keywords = raw.get("retrieval_keywords")
    if isinstance(keywords, list):
        result["retrieval_keywords"] = [str(k) for k in keywords if isinstance(k, str) and k]

    risk = raw.get("risk_level")
    if risk in ("low", "medium", "high", "critical"):
        result["risk_level"] = risk

    approval = raw.get("requires_human_approval")
    if isinstance(approval, bool):
        result["requires_human_approval"] = approval

    prereqs = raw.get("prerequisites")
    if isinstance(prereqs, list):
        result["prerequisites"] = [str(p) for p in prereqs if isinstance(p, str) and p]

    audience = raw.get("audience")
    if isinstance(audience, list):
        result["audience"] = [str(a) for a in audience if isinstance(a, str) and a]

    return result


def _is_metadata_empty(md: dict) -> bool:
    return (
        not md.get("retrieval_keywords")
        and md.get("risk_level") is None
        and not md.get("requires_human_approval")
        and not md.get("prerequisites")
        and not md.get("audience")
    )


class SkillVersionOut(Schema):
    id: str
    version_number: int
    content_md: str
    frontmatter_yaml: str
    change_summary: str
    authored_by: UserBriefOut | None
    created_at: str
    files: list[VersionFileOut]
    koinoflow_metadata: KoinoflowMetadata
    reverted_from_version_number: int | None


class SkillVersionBriefOut(Schema):
    id: str
    version_number: int
    change_summary: str
    authored_by: UserBriefOut | None
    created_at: str
    reverted_from_version_number: int | None


class SkillOut(Schema):
    id: str
    title: str
    slug: str
    description: str
    status: str
    visibility: str
    shared_with_ids: list[str]
    department_slug: str
    department_name: str
    team_slug: str
    team_name: str
    owner: UserBriefOut | None
    current_version_number: int | None
    last_reviewed_at: str | None
    needs_audit: bool
    risk_level: RiskLevel | None
    retrieval_keywords: list[str]
    requires_human_approval: bool
    execution_enabled: bool
    discovery_embedding_status: DiscoveryEmbeddingStatus
    created_at: str
    updated_at: str


class SkillDetailOut(Schema):
    id: str
    title: str
    slug: str
    description: str
    status: str
    visibility: str
    shared_with_ids: list[str]
    is_shared_with_requester_team: bool
    department_slug: str
    department_name: str
    team_slug: str
    team_name: str
    system_kind: str
    owner: UserBriefOut | None
    current_version: SkillVersionOut | None
    last_reviewed_at: str | None
    needs_audit: bool
    execution_enabled: bool
    discovery_embedding_status: DiscoveryEmbeddingStatus
    created_at: str
    updated_at: str


class ExecutionLimitsOut(Schema):
    timeout_seconds: int
    memory_mb: int
    max_output_bytes_inline: int
    max_runs_per_day: int
    max_concurrent_runs: int


class ExecutionNetworkOut(Schema):
    policy: str
    allowed: list[str]


class SecretRefOut(Schema):
    name: str
    scope: str
    required: bool
    description: str = ""


class SecretRefIn(Schema):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$", max_length=64)
    scope: str = Field(default="workspace", pattern=r"^(workspace|user|platform)$")
    required: bool = True
    description: str = Field(default="", max_length=500)


class SkillExecutionSpecOut(Schema):
    enabled: bool
    version_number: int | None
    runtime: str
    latency_class: str
    entrypoint_path: str
    input_schema: dict
    output_schema: dict
    secrets_scope: str
    secret_refs: list[SecretRefOut]
    network: ExecutionNetworkOut
    limits: ExecutionLimitsOut
    updated_at: str | None


class ExecutionLimitsIn(Schema):
    timeout_seconds: int = Field(default=30, ge=1, le=900)
    memory_mb: int = Field(default=512, ge=128, le=4096)
    max_output_bytes_inline: int = Field(default=32768, ge=1024, le=262144)
    max_runs_per_day: int = Field(default=100, ge=1, le=10000)
    max_concurrent_runs: int = Field(default=1, ge=1, le=100)


class ExecutionNetworkIn(Schema):
    policy: str = Field(default="egress_allowlist", pattern=r"^(egress_allowlist|none)$")
    allowed: list[str] = []


class UpdateSkillExecutionSpecIn(Schema):
    enabled: bool
    runtime: str = Field(default="python", pattern=r"^python$")
    latency_class: str = Field(default="standard", pattern=r"^(interactive|standard|async)$")
    entrypoint_path: str = Field(default="run.py", pattern=r"^[a-zA-Z0-9_\-./]+$", max_length=500)
    input_schema: dict = {}
    output_schema: dict = {}
    secrets_scope: str = Field(default="workspace", pattern=r"^(workspace|user|platform)$")
    secret_refs: list[SecretRefIn] = []
    network: ExecutionNetworkIn = ExecutionNetworkIn()
    limits: ExecutionLimitsIn = ExecutionLimitsIn()


class SkillSecretStatusOut(Schema):
    name: str
    scope: str
    required: bool
    description: str
    is_set: bool
    kind: str | None = None
    vault_ref: str | None = None
    last_set_at: str | None
    last_set_by: UserBriefOut | None


class SkillSecretListOut(Schema):
    items: list[SkillSecretStatusOut]
    count: int


class UpsertSkillSecretValueIn(Schema):
    value: str | None = Field(default=None, max_length=10000)
    vault_ref: str | None = Field(default=None, max_length=512)


class ExecutionSecretsFetchOut(Schema):
    values: dict[str, str]


class ExecuteSkillIn(Schema):
    inputs: dict = {}
    approved: bool = False


class SkillExecutionRunOut(Schema):
    id: str
    skill_id: str
    skill_slug: str
    version_number: int | None
    status: str
    caller_type: str
    requires_approval: bool
    inputs: dict
    output: dict | None
    output_uri: str
    logs_uri: str
    error_message: str
    external_job_name: str
    resource_usage: dict
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    expires_at: str | None
    duration_ms: int | None
    caller_label: str
    cancellable: bool


class SkillExecutionRunListOut(Schema):
    items: list[SkillExecutionRunOut]
    count: int


class SkillExecutionRunLogsOut(Schema):
    run_id: str
    status: str
    logs: str
    truncated: bool
    available: bool
    source: str


class SkillFileAiEditIn(Schema):
    instruction: str = Field(..., min_length=1, max_length=4000)
    run_id: str | None = None
    model: str | None = None


class SandboxSkillSummaryOut(Schema):
    id: str
    slug: str
    title: str
    description: str
    status: str
    department_name: str
    team_name: str
    system_kind: str
    execution_enabled: bool
    latest_run: SkillExecutionRunOut | None
    last_run_at: str | None
    runs_24h: int
    failures_24h: int


class SandboxOverviewOut(Schema):
    skills: list[SandboxSkillSummaryOut]
    can_use_sandbox: bool
    workspace_min_role: str
    user_role: str | None


class SkillExecutionCallbackIn(Schema):
    status: str
    output: dict | None = None
    output_uri: str = ""
    logs_uri: str = ""
    error_message: str = ""
    resource_usage: dict = {}


class SkillListOut(Schema):
    items: list[SkillOut]
    count: int


class SkillDiscoveryResultOut(Schema):
    id: str
    title: str
    slug: str
    description: str
    department_slug: str
    department_name: str
    team_slug: str
    team_name: str
    current_version_number: int | None
    risk_level: RiskLevel | None
    retrieval_keywords: list[str]
    requires_human_approval: bool
    score: float
    vector_score: float | None
    lexical_score: float
    match_reasons: list[str]
    snippet: str
    indexed: bool


class SkillDiscoveryOut(Schema):
    items: list[SkillDiscoveryResultOut]
    count: int
    embedding_status: str


class VersionListOut(Schema):
    items: list[SkillVersionBriefOut]
    count: int


class CreateSkillIn(Schema):
    department_id: str
    title: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)
    description: str = ""
    owner_id: str | None = None
    visibility: str = VisibilityChoices.DEPARTMENT
    shared_with_ids: list[str] = []


class UpdateSkillIn(Schema):
    title: str | None = None
    description: str | None = None
    owner_id: str | None = None
    visibility: str | None = None
    shared_with_ids: list[str] | None = None


class VersionDiffOut(Schema):
    old_version: SkillVersionBriefOut
    new_version: SkillVersionBriefOut
    hunks: list[DiffHunk]
    stats: dict
    file_diff: list[FileDiffEntry]


class CreateVersionIn(Schema):
    content_md: str
    frontmatter_yaml: str = ""
    change_summary: str = ""
    files: list[VersionFileIn] | None = None
    koinoflow_metadata: KoinoflowMetadata | None = None


class RevertVersionIn(Schema):
    change_summary: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────


def _version_out(v):
    return {
        "id": str(v.id),
        "version_number": v.version_number,
        "content_md": v.content_md,
        "frontmatter_yaml": v.frontmatter_yaml,
        "change_summary": v.change_summary,
        "authored_by": _user_brief(v.authored_by),
        "created_at": v.created_at.isoformat(),
        "files": resolve_file_list(v.skill_id, v.version_number),
        "koinoflow_metadata": _normalize_metadata(v.koinoflow_metadata),
        "reverted_from_version_number": (
            v.reverted_from.version_number if v.reverted_from_id else None
        ),
    }


def _version_brief_out(v):
    return {
        "id": str(v.id),
        "version_number": v.version_number,
        "change_summary": v.change_summary,
        "authored_by": _user_brief(v.authored_by),
        "created_at": v.created_at.isoformat(),
        "reverted_from_version_number": (
            v.reverted_from.version_number if v.reverted_from_id else None
        ),
    }


def _compute_file_hunks(old_content: str, new_content: str) -> list[dict]:
    old_text = old_content.rstrip() + "\n" if old_content else ""
    new_text = new_content.rstrip() + "\n" if new_content else ""
    old_lines = old_text.splitlines(keepends=True) if old_text else []
    new_lines = new_text.splitlines(keepends=True) if new_text else []

    diff = difflib.unified_diff(old_lines, new_lines, n=3)
    hunks = []
    current_hunk = None

    for line in diff:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            parts = line.split("@@")
            range_info = parts[1].strip()
            old_range, new_range = range_info.split(" ")
            old_start, old_count = _parse_range(old_range[1:])
            new_start, new_count = _parse_range(new_range[1:])
            current_hunk = {
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": [],
            }
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif current_hunk is not None:
            current_hunk["lines"].append(line.rstrip("\n\r"))

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def _compute_file_diff_entries(old_files, new_files):
    entries = []
    all_paths = set(old_files) | set(new_files)
    for path in sorted(all_paths):
        in_old = path in old_files
        in_new = path in new_files
        if in_new and not in_old:
            f = new_files[path]
            hunks = None
            if is_text_file(f):
                hunks = _compute_file_hunks("", file_bytes(f).decode("utf-8"))
            entries.append(
                {
                    "path": path,
                    "status": "added",
                    "old_size": None,
                    "new_size": f.size_bytes,
                    "hunks": hunks,
                }
            )
        elif in_old and not in_new:
            f = old_files[path]
            hunks = None
            if is_text_file(f):
                hunks = _compute_file_hunks(file_bytes(f).decode("utf-8"), "")
            entries.append(
                {
                    "path": path,
                    "status": "deleted",
                    "old_size": f.size_bytes,
                    "new_size": None,
                    "hunks": hunks,
                }
            )
        elif file_bytes(old_files[path]) != file_bytes(new_files[path]):
            old_f = old_files[path]
            new_f = new_files[path]
            hunks = None
            if is_text_file(old_f) and is_text_file(new_f):
                hunks = _compute_file_hunks(
                    file_bytes(old_f).decode("utf-8"),
                    file_bytes(new_f).decode("utf-8"),
                )
            entries.append(
                {
                    "path": path,
                    "status": "modified",
                    "old_size": old_f.size_bytes,
                    "new_size": new_f.size_bytes,
                    "hunks": hunks,
                }
            )
    return entries


def _normalize_support_file_path(path: str) -> str:
    normalized = posixpath.normpath(path)
    if (
        normalized in {"", "."}
        or normalized == ".."
        or normalized.startswith("../")
        or normalized.startswith("/")
        or "\\" in path
    ):
        raise HttpError(400, "Archive contains an invalid support file path")
    return normalized


def _format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} bytes"


def _validate_support_file_size(path: str, size: int):
    if size > MAX_SUPPORT_FILE_BYTES:
        raise HttpError(
            413,
            (
                f"File {path} is {_format_bytes(size)}; "
                f"max per file is {_format_bytes(MAX_SUPPORT_FILE_BYTES)}"
            ),
        )


def _guess_mime_type(path: str, file_type: str) -> str:
    guessed, _encoding = mimetypes.guess_type(path)
    if guessed:
        return guessed
    defaults = {
        "python": "text/x-python",
        "markdown": "text/markdown",
        "html": "text/html",
        "yaml": "application/yaml",
        "json": "application/json",
        "javascript": "text/javascript",
        "typescript": "text/typescript",
        "shell": "text/x-shellscript",
        "text": "text/plain",
        "pdf": "application/pdf",
        "image": "application/octet-stream",
    }
    return defaults.get(file_type, "application/octet-stream")


def _is_text_payload(file_type: str, mime_type: str, data: bytes) -> bool:
    if file_type in TEXT_FILE_TYPES or mime_type.startswith("text/"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def _file_entry(
    *,
    path: str,
    data: bytes,
    file_type: str | None = None,
    mime_type: str | None = None,
    encoding: str | None = None,
) -> dict:
    normalized_path = _normalize_support_file_path(path)
    _validate_support_file_size(normalized_path, len(data))
    resolved_file_type = file_type or detect_file_type(normalized_path)
    resolved_mime = mime_type or _guess_mime_type(normalized_path, resolved_file_type)
    text_payload = _is_text_payload(resolved_file_type, resolved_mime, data)
    resolved_encoding = encoding or ("utf-8" if text_payload else "base64")
    content = data.decode("utf-8") if text_payload else ""
    return {
        "path": normalized_path,
        "content": content,
        "content_bytes": data,
        "file_type": resolved_file_type,
        "mime_type": resolved_mime,
        "encoding": resolved_encoding,
        "sha256": hashlib.sha256(data).hexdigest() if data else "",
        "size_bytes": len(data),
    }


def _file_entry_from_payload(payload: dict) -> dict:
    path = payload["path"]
    if payload.get("content_base64") is not None:
        try:
            data = base64.b64decode(payload["content_base64"], validate=True)
        except (binascii.Error, ValueError):
            raise HttpError(400, f"File {path} has invalid base64 content")
    elif payload.get("content") is not None:
        data = payload.get("content", "").encode("utf-8")
    else:
        raise HttpError(400, f"File {path} must include content or content_base64")
    return _file_entry(
        path=path,
        data=data,
        file_type=payload.get("file_type"),
        mime_type=payload.get("mime_type"),
        encoding=payload.get("encoding"),
    )


def _version_file_from_entry(version, entry: dict, *, is_deleted=False) -> VersionFile:
    data = b"" if is_deleted else entry.get("content_bytes", b"")
    return VersionFile(
        version=version,
        path=entry["path"],
        content="" if is_deleted else entry.get("content", ""),
        content_bytes=data,
        file_type=entry.get("file_type", "text"),
        mime_type=entry.get("mime_type", "text/plain"),
        encoding=entry.get("encoding", "utf-8"),
        sha256=entry.get("sha256", ""),
        size_bytes=0 if is_deleted else entry.get("size_bytes", len(data)),
        is_deleted=is_deleted,
    )


def _file_detail(f: VersionFile) -> dict:
    data = file_bytes(f)
    content = None
    if is_text_file(f):
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = None
    return {
        "id": str(f.id),
        "path": f.path,
        "file_type": f.file_type,
        "mime_type": f.mime_type,
        "encoding": f.encoding,
        "size_bytes": f.size_bytes,
        "content": content,
        "content_base64": base64.b64encode(data).decode("ascii") if content is None else None,
    }


def _compute_skill_needs_audit(skill, audit_settings_cache=None):
    """
    Return True if the skill is published and overdue for review
    based on its effective skill_audit setting.

    audit_settings_cache: optional dict keyed by (workspace_id, team_id, dept_id)
    mapping to the resolved ProcessAuditRule or None.
    """
    if skill.status != StatusChoices.PUBLISHED:
        return False

    dept = skill.department
    workspace_id = dept.team.workspace_id
    team_id = dept.team_id
    dept_id = dept.id
    cache_key = (workspace_id, team_id, dept_id)

    if audit_settings_cache is not None and cache_key in audit_settings_cache:
        rule = audit_settings_cache[cache_key]
    else:
        effective = get_effective_settings(workspace_id, team_id=team_id, department_id=dept_id)
        rule = effective.get("skill_audit")
        if audit_settings_cache is not None:
            audit_settings_cache[cache_key] = rule

    if rule is None:
        return False

    if skill.last_reviewed_at is None:
        return True

    cutoff = timezone.now() - timedelta(days=rule.period_days)
    return skill.last_reviewed_at < cutoff


def _skill_discovery_embedding_status(skill) -> DiscoveryEmbeddingStatus:
    if (
        skill.status != StatusChoices.PUBLISHED
        or not skill.current_version_id
        or not skill.current_version
    ):
        return "not_applicable"

    try:
        skill.current_version.discovery_embedding
    except ObjectDoesNotExist:
        return "pending"
    return "ready"


def _get_slug(entity_type, entity_id):
    from apps.orgs.models import CoreSlug

    try:
        return CoreSlug.objects.get(entity_type=entity_type, entity_id=entity_id).slug
    except CoreSlug.DoesNotExist:
        return ""


def _skill_out(p, audit_cache=None, shared_cache=None):
    cv_number = None
    cv_metadata = _empty_metadata_dict()
    if p.current_version_id:
        cv = p.current_version
        if cv:
            cv_number = cv.version_number
            cv_metadata = _normalize_metadata(cv.koinoflow_metadata)

    if shared_cache is not None and p.id in shared_cache:
        sw_ids = shared_cache[p.id]
    else:
        sw_ids = [str(pk) for pk in p.shared_with.values_list("id", flat=True)]
        if shared_cache is not None:
            shared_cache[p.id] = sw_ids

    return {
        "id": str(p.id),
        "title": p.title,
        "slug": p.slug,
        "description": p.description,
        "status": p.status,
        "visibility": p.visibility,
        "shared_with_ids": sw_ids,
        "department_slug": _get_slug(EntityType.DEPARTMENT, p.department_id),
        "department_name": p.department.name,
        "team_slug": _get_slug(EntityType.TEAM, p.department.team_id),
        "team_name": p.department.team.name,
        "owner": _user_brief(p.owner),
        "current_version_number": cv_number,
        "last_reviewed_at": p.last_reviewed_at.isoformat() if p.last_reviewed_at else None,
        "needs_audit": _compute_skill_needs_audit(p, audit_cache),
        "risk_level": cv_metadata["risk_level"],
        "retrieval_keywords": cv_metadata["retrieval_keywords"],
        "requires_human_approval": cv_metadata["requires_human_approval"],
        "execution_enabled": p.execution_enabled,
        "discovery_embedding_status": _skill_discovery_embedding_status(p),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _skill_detail_out(p, requester_team_id=None):
    from apps.orgs.models import Department

    cv = None
    if p.current_version:
        cv = _version_out(p.current_version)
    shared_with_ids = [str(pk) for pk in p.shared_with.values_list("id", flat=True)]
    is_shared_with_requester_team = False
    if requester_team_id and shared_with_ids:
        team_dept_ids = {
            str(pk)
            for pk in Department.objects.filter(team_id=requester_team_id).values_list(
                "id", flat=True
            )
        }
        is_shared_with_requester_team = bool(team_dept_ids & set(shared_with_ids))
    return {
        "id": str(p.id),
        "title": p.title,
        "slug": p.slug,
        "description": p.description,
        "status": p.status,
        "visibility": p.visibility,
        "shared_with_ids": shared_with_ids,
        "is_shared_with_requester_team": is_shared_with_requester_team,
        "department_slug": _get_slug(EntityType.DEPARTMENT, p.department_id),
        "department_name": p.department.name,
        "team_slug": _get_slug(EntityType.TEAM, p.department.team_id),
        "team_name": p.department.team.name,
        "system_kind": p.department.system_kind or "",
        "owner": _user_brief(p.owner),
        "current_version": cv,
        "last_reviewed_at": p.last_reviewed_at.isoformat() if p.last_reviewed_at else None,
        "needs_audit": _compute_skill_needs_audit(p),
        "execution_enabled": p.execution_enabled,
        "discovery_embedding_status": _skill_discovery_embedding_status(p),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _execution_spec_out(skill: Skill) -> dict:
    try:
        spec = skill.execution_spec
    except SkillExecutionSpec.DoesNotExist:
        return {
            "enabled": skill.execution_enabled,
            "version_number": None,
            "runtime": "python",
            "latency_class": "standard",
            "entrypoint_path": "run.py",
            "input_schema": {},
            "output_schema": {},
            "secrets_scope": "workspace",
            "secret_refs": [],
            "network": {"policy": "egress_allowlist", "allowed": []},
            "limits": {
                "timeout_seconds": 30,
                "memory_mb": 512,
                "max_output_bytes_inline": 32768,
                "max_runs_per_day": 100,
                "max_concurrent_runs": 1,
            },
            "updated_at": None,
        }

    return {
        "enabled": skill.execution_enabled,
        "version_number": spec.version.version_number if spec.version_id else None,
        "runtime": spec.runtime,
        "latency_class": spec.latency_class,
        "entrypoint_path": spec.entrypoint_path,
        "input_schema": spec.input_schema,
        "output_schema": spec.output_schema,
        "secrets_scope": spec.secrets_scope,
        "secret_refs": [
            {
                "name": ref.name,
                "scope": ref.scope,
                "required": bool(ref.required),
                "description": ref.description or "",
            }
            for ref in spec.secret_refs.all().order_by("name")
        ],
        "network": {
            "policy": spec.network_policy,
            "allowed": spec.allowed_egress,
        },
        "limits": {
            "timeout_seconds": spec.timeout_seconds,
            "memory_mb": spec.memory_mb,
            "max_output_bytes_inline": spec.max_output_bytes_inline,
            "max_runs_per_day": spec.max_runs_per_day,
            "max_concurrent_runs": spec.max_concurrent_runs,
        },
        "updated_at": spec.updated_at.isoformat(),
    }


EXECUTION_CANCELLABLE_STATUSES = {
    SkillExecutionRun.StatusChoices.PENDING_APPROVAL,
    SkillExecutionRun.StatusChoices.QUEUED,
    SkillExecutionRun.StatusChoices.RUNNING,
}


def _execution_run_caller_label(run: SkillExecutionRun) -> str:
    if run.agent_id and getattr(run, "agent", None):
        agent_name = getattr(run.agent, "name", "") or "Agent"
        return f"Agent · {agent_name}"
    if run.user_id and getattr(run, "user", None):
        user = run.user
        full_name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        label = full_name or getattr(user, "email", "") or "User"
        return f"User · {label}"
    if run.caller_type == SkillExecutionRun.CallerTypeChoices.API_KEY:
        return "API key"
    if run.caller_type == SkillExecutionRun.CallerTypeChoices.OAUTH:
        return "OAuth"
    return run.caller_type or "Unknown"


def _execution_run_duration_ms(run: SkillExecutionRun) -> int | None:
    if run.started_at and run.finished_at:
        delta = run.finished_at - run.started_at
        return max(0, int(delta.total_seconds() * 1000))
    if run.started_at and run.status == SkillExecutionRun.StatusChoices.RUNNING:
        delta = timezone.now() - run.started_at
        return max(0, int(delta.total_seconds() * 1000))
    return None


def _execution_run_out(run: SkillExecutionRun) -> dict:
    return {
        "id": str(run.id),
        "skill_id": str(run.skill_id),
        "skill_slug": run.skill.slug,
        "version_number": run.version.version_number if run.version_id else None,
        "status": run.status,
        "caller_type": run.caller_type,
        "requires_approval": run.status == SkillExecutionRun.StatusChoices.PENDING_APPROVAL,
        "inputs": run.inputs or {},
        "output": run.output,
        "output_uri": run.output_uri,
        "logs_uri": run.logs_uri,
        "error_message": run.error_message,
        "external_job_name": run.external_job_name,
        "resource_usage": run.resource_usage or {},
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "expires_at": run.expires_at.isoformat() if run.expires_at else None,
        "duration_ms": _execution_run_duration_ms(run),
        "caller_label": _execution_run_caller_label(run),
        "cancellable": run.status in EXECUTION_CANCELLABLE_STATUSES,
    }


def _sync_secret_refs(spec: SkillExecutionSpec, refs: list[SecretRefIn]):
    desired: dict[str, SecretRefIn] = {}
    for ref in refs:
        desired[ref.name] = ref

    existing = {row.name: row for row in spec.secret_refs.all()}
    for name, row in existing.items():
        incoming = desired.get(name)
        if incoming is None:
            row.delete()
            continue
        changed = (
            row.scope != incoming.scope
            or row.required != incoming.required
            or row.description != incoming.description
        )
        if changed:
            row.scope = incoming.scope
            row.required = incoming.required
            row.description = incoming.description
            row.save(update_fields=["scope", "required", "description", "updated_at"])

    for name, incoming in desired.items():
        if name in existing:
            continue
        SkillSecretDeclaration.objects.create(
            spec=spec,
            name=incoming.name,
            scope=incoming.scope,
            required=incoming.required,
            description=incoming.description,
        )


def _skill_secret_status_items(skill: Skill) -> list[dict]:
    try:
        spec = skill.execution_spec
    except SkillExecutionSpec.DoesNotExist:
        return []

    workspace = skill.department.team.workspace
    values = {
        (row.name, row.scope): row
        for row in SkillSecretValue.objects.select_related("last_set_by")
        .filter(skill=skill, workspace=workspace)
        .order_by("name")
    }
    items = []
    for ref in spec.secret_refs.all().order_by("name"):
        row = values.get((ref.name, ref.scope))
        items.append(
            {
                "name": ref.name,
                "scope": ref.scope,
                "required": bool(ref.required),
                "description": ref.description or "",
                "is_set": row is not None,
                "kind": _secret_row_kind(row),
                "vault_ref": (row.vault_ref or None) if row else None,
                "last_set_at": row.updated_at.isoformat() if row else None,
                "last_set_by": _user_brief(row.last_set_by) if row else None,
            }
        )
    return items


def _secret_row_kind(row) -> str | None:
    if row is None:
        return None
    return "vault_ref" if row.vault_ref else "encrypted"


def _set_skill_shared_with(skill, dept_ids, workspace):
    """Validate and set the shared_with M2M for a skill."""
    from apps.orgs.models import Department

    if not dept_ids:
        skill.shared_with.clear()
        return

    depts = Department.objects.filter(
        id__in=dept_ids,
        team__workspace=workspace,
    )
    if depts.count() != len(dept_ids):
        raise HttpError(400, "One or more shared department IDs are invalid")

    skill.shared_with.set(depts)


def _normalize_skill_system_kind(system_kind: str | None) -> str:
    if system_kind in (None, ""):
        return ""
    if system_kind == SYSTEM_KIND_AGENTS:
        return SYSTEM_KIND_AGENTS
    raise HttpError(400, "Invalid skill system kind")


def _get_skill(request, slug: str, *, allow_draft=True, system_kind: str | None = ""):
    """Fetch a skill scoped to the request's workspace."""
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    requested_system_kind = _normalize_skill_system_kind(system_kind)
    agent = getattr(request, "agent", None)
    qs = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__discovery_embedding",
        "current_version__reverted_from",
    ).filter(slug=slug, department__team__workspace=workspace)
    if agent is not None:
        from apps.agents.selectors import skills_for_agent

        qs = (
            skills_for_agent(agent)
            .select_related(
                "department__team",
                "owner",
                "current_version__authored_by",
                "current_version__discovery_embedding",
                "current_version__reverted_from",
            )
            .filter(slug=slug)
        )
    elif requested_system_kind == SYSTEM_KIND_AGENTS:
        qs = qs.filter(department__system_kind=SYSTEM_KIND_AGENTS)
    else:
        qs = qs.exclude(department__system_kind=SYSTEM_KIND_AGENTS)
    try:
        skill = qs.get()
    except Skill.DoesNotExist:
        raise HttpError(404, "Skill not found")
    except Skill.MultipleObjectsReturned:
        raise HttpError(409, "Skill slug is ambiguous")

    if agent is None and skill.department.system_kind == SYSTEM_KIND_AGENTS:
        is_api_key = hasattr(request, "api_key")
        is_oauth = hasattr(request, "oauth_token")
        membership = getattr(request, "membership", None)
        if is_api_key or is_oauth or membership is None or membership.role != RoleChoices.ADMIN:
            raise HttpError(404, "Skill not found")

    is_api_key = hasattr(request, "api_key")
    if is_api_key and not allow_draft and skill.status != StatusChoices.PUBLISHED:
        raise HttpError(404, "Skill not found")

    return skill


def _base_skill_queryset(request):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")

    qs = (
        Skill.objects.filter(department__team__workspace=workspace)
        .select_related("department__team", "owner", "current_version__discovery_embedding")
        .order_by("-updated_at")
    )

    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    agent = getattr(request, "agent", None)
    if agent is not None:
        from apps.agents.selectors import skills_for_agent

        qs = skills_for_agent(agent).select_related(
            "department__team", "owner", "current_version__discovery_embedding"
        )
    elif is_api_key:
        qs = qs.filter(status=StatusChoices.PUBLISHED)
        qs = apply_api_key_scope(request.api_key, qs)
        qs = qs.exclude(department__system_kind=SYSTEM_KIND_AGENTS)
    elif is_oauth:
        qs = qs.filter(status=StatusChoices.PUBLISHED)
        qs = apply_oauth_connection_scope(request, qs)
        qs = qs.exclude(department__system_kind=SYSTEM_KIND_AGENTS)
    else:
        qs = qs.exclude(department__system_kind=SYSTEM_KIND_AGENTS)
    return qs


def _apply_skill_filters(
    qs,
    *,
    department: str | None = None,
    team: str | None = None,
    status: str | None = None,
):
    if department:
        from apps.orgs.models import CoreSlug
        from apps.orgs.models import Department as Dept

        dept_ids = list(
            CoreSlug.objects.filter(entity_type=EntityType.DEPARTMENT, slug=department).values_list(
                "entity_id", flat=True
            )
        )
        dept_team_ids = list(Dept.objects.filter(id__in=dept_ids).values_list("team_id", flat=True))
        qs = qs.filter(
            Q(department_id__in=dept_ids)
            | Q(shared_with__id__in=dept_ids)
            | Q(visibility=VisibilityChoices.TEAM, department__team_id__in=dept_team_ids)
            | Q(visibility=VisibilityChoices.WORKSPACE)
        ).distinct()
    if team:
        from apps.orgs.models import CoreSlug

        team_ids = CoreSlug.objects.filter(entity_type=EntityType.TEAM, slug=team).values_list(
            "entity_id", flat=True
        )
        qs = qs.filter(
            Q(department__team_id__in=team_ids) | Q(visibility=VisibilityChoices.WORKSPACE)
        )
    if status:
        qs = qs.filter(status=status)
    return qs


def _query_tokens(query: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", query.lower()) if len(token) > 1}


def _token_hit_ratio(tokens: set[str], text: str) -> float:
    if not tokens or not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for token in tokens if token in lowered)
    return hits / len(tokens)


def _skill_snippet(skill: Skill, tokens: set[str]) -> str:
    if skill.description:
        ratio = _token_hit_ratio(tokens, skill.description)
        if ratio:
            return skill.description[:280]
    content = skill.current_version.content_md if skill.current_version else ""
    for line in content.splitlines():
        cleaned = line.strip()
        if cleaned and _token_hit_ratio(tokens, cleaned):
            return cleaned[:280]
    return (skill.description or content.strip())[:280]


def _lexical_skill_discovery_score(skill: Skill, query: str) -> tuple[float, list[str], str]:
    tokens = _query_tokens(query)
    version = skill.current_version
    metadata = normalize_discovery_metadata(version.koinoflow_metadata if version else {})

    title_score = _token_hit_ratio(tokens, skill.title)
    slug_score = _token_hit_ratio(tokens, skill.slug)
    description_score = _token_hit_ratio(tokens, skill.description)
    keyword_score = _token_hit_ratio(tokens, " ".join(metadata["retrieval_keywords"]))
    audience_score = _token_hit_ratio(tokens, " ".join(metadata["audience"]))
    prerequisite_score = _token_hit_ratio(tokens, " ".join(metadata["prerequisites"]))
    content_score = _token_hit_ratio(tokens, version.content_md if version else "")

    score = (
        0.25 * title_score
        + 0.15 * slug_score
        + 0.15 * description_score
        + 0.25 * keyword_score
        + 0.05 * audience_score
        + 0.05 * prerequisite_score
        + 0.10 * content_score
    )
    reasons = []
    if title_score:
        reasons.append("title matched query terms")
    if slug_score:
        reasons.append("slug matched query terms")
    if description_score:
        reasons.append("description matched query terms")
    if keyword_score:
        reasons.append("retrieval keywords matched query terms")
    if audience_score:
        reasons.append("audience matched query terms")
    if prerequisite_score:
        reasons.append("prerequisites matched query terms")
    if content_score:
        reasons.append("skill body matched query terms")

    return min(score, 1.0), reasons, _skill_snippet(skill, tokens)


# ── Skill Endpoints ──────────────────────────────────────────────────────


@router.get("/skills", response=SkillListOut, auth=api_or_session, throttle=[ReadThrottle()])
def list_skills(
    request,
    department: str | None = None,
    team: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    qs = _apply_skill_filters(
        _base_skill_queryset(request),
        department=department,
        team=team,
        status=status,
    )
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    count = qs.count()
    page = qs[offset : offset + limit]
    page = page.prefetch_related("shared_with")
    audit_cache = {}
    shared_cache = {}
    items = [_skill_out(p, audit_cache, shared_cache) for p in page]
    return {"items": items, "count": count}


@router.get(
    "/skills/discover",
    response=SkillDiscoveryOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def discover_skills(
    request,
    query: str,
    department: str | None = None,
    team: str | None = None,
    limit: int = 10,
):
    query = query.strip()
    if not query:
        raise HttpError(400, "Query is required")

    limit = min(max(limit, 1), 25)
    qs = _apply_skill_filters(
        _base_skill_queryset(request),
        department=department,
        team=team,
    ).filter(current_version__isnull=False)
    qs = qs.select_related(
        "department__team",
        "current_version__discovery_embedding",
    )

    config = None
    query_vector = None
    embedding_status = "unavailable"
    try:
        config = get_embedding_config()
        query_vector = VertexEmbeddingClient(config).embed_query(query)
        embedding_status = "ready"
    except Exception as exc:
        logger.warning("Skill discovery embedding unavailable: %s", exc)

    vector_scores = {}
    candidates = {}
    if query_vector is not None and config is not None:
        vector_rows = (
            qs.filter(
                current_version__discovery_embedding__embedding_model=config.model,
                current_version__discovery_embedding__embedding_dimensions=config.dimensions,
            )
            .annotate(
                vector_distance=CosineDistance(
                    "current_version__discovery_embedding__embedding",
                    query_vector,
                )
            )
            .order_by("vector_distance")[: max(limit * 5, 50)]
        )
        for skill in vector_rows:
            distance = float(skill.vector_distance)
            score = max(0.0, min(1.0, 1.0 - distance))
            vector_scores[skill.id] = score
            candidates[skill.id] = skill

    lexical_pool = qs[:500]
    for skill in lexical_pool:
        candidates[skill.id] = skill

    results = []
    for skill in candidates.values():
        lexical_score, reasons, snippet = _lexical_skill_discovery_score(skill, query)
        vector_score = vector_scores.get(skill.id)
        if vector_score is not None:
            combined_score = (0.70 * vector_score) + (0.30 * lexical_score)
            reasons = [f"semantic similarity {vector_score:.2f}", *reasons]
        else:
            combined_score = lexical_score

        if combined_score <= 0:
            continue

        version = skill.current_version
        metadata = normalize_discovery_metadata(version.koinoflow_metadata if version else {})
        indexed = False
        if version is not None:
            try:
                indexed = bool(version.discovery_embedding)
            except SkillVersion.discovery_embedding.RelatedObjectDoesNotExist:
                indexed = False
        results.append(
            {
                "id": str(skill.id),
                "title": skill.title,
                "slug": skill.slug,
                "description": skill.description,
                "department_slug": _get_slug(EntityType.DEPARTMENT, skill.department_id),
                "department_name": skill.department.name,
                "team_slug": _get_slug(EntityType.TEAM, skill.department.team_id),
                "team_name": skill.department.team.name,
                "current_version_number": version.version_number if version else None,
                "risk_level": metadata["risk_level"],
                "retrieval_keywords": metadata["retrieval_keywords"],
                "requires_human_approval": metadata["requires_human_approval"],
                "score": round(combined_score, 4),
                "vector_score": round(vector_score, 4) if vector_score is not None else None,
                "lexical_score": round(lexical_score, 4),
                "match_reasons": reasons[:5],
                "snippet": snippet,
                "indexed": indexed,
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    page = results[:limit]
    return {
        "items": page,
        "count": len(results),
        "embedding_status": embedding_status,
    }


@router.post(
    "/skills",
    response={201: SkillDetailOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def create_skill(request, payload: CreateSkillIn):
    workspace = request.workspace
    from apps.orgs.models import Department

    try:
        dept = Department.objects.select_related("team").get(
            id=payload.department_id, team__workspace=workspace, system_kind=""
        )
    except Department.DoesNotExist:
        raise HttpError(404, "Department not found")

    from apps.accounts.permissions import get_writable_dept_ids

    writable = get_writable_dept_ids(request)
    if writable is not None and str(dept.id) not in writable:
        raise HttpError(403, "Insufficient permissions for this department")

    if payload.visibility not in VisibilityChoices.values:
        raise HttpError(400, f"Invalid visibility: {payload.visibility}")

    owner = None
    if payload.owner_id:
        if not Membership.objects.filter(workspace=workspace, user_id=payload.owner_id).exists():
            raise HttpError(400, "Owner is not a workspace member")
        from apps.accounts.models import User

        owner = User.objects.get(id=payload.owner_id)

    from django.db import IntegrityError, transaction

    with transaction.atomic():
        slug_taken = Skill.objects.filter(
            department__team__workspace=workspace, slug=payload.slug
        ).exists()
        if slug_taken:
            raise HttpError(409, "Skill slug already taken in this workspace")

        try:
            skill = Skill.objects.create(
                department=dept,
                title=payload.title,
                slug=payload.slug,
                description=payload.description,
                owner=owner,
                status=StatusChoices.DRAFT,
                visibility=payload.visibility,
            )
        except IntegrityError:
            raise HttpError(409, "Skill slug already taken in this workspace")

    if payload.shared_with_ids:
        _set_skill_shared_with(skill, payload.shared_with_ids, workspace)

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)
    return Status(201, _skill_detail_out(skill))


@router.get(
    "/skills/{slug}",
    response=SkillDetailOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_skill(request, slug: str, system_kind: str | None = ""):
    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    skill = _get_skill(
        request,
        slug,
        allow_draft=not (is_api_key or is_oauth),
        system_kind=system_kind,
    )
    if is_api_key:
        allowed = apply_api_key_scope(request.api_key, Skill.objects.filter(pk=skill.pk))
        if not allowed.exists():
            raise HttpError(404, "Skill not found")
    elif is_oauth:
        allowed = apply_oauth_connection_scope(request, Skill.objects.filter(pk=skill.pk))
        if not allowed.exists():
            raise HttpError(404, "Skill not found")
    membership = getattr(request, "membership", None)
    team_id = membership.team_id if membership and membership.team_id else None
    return _skill_detail_out(skill, requester_team_id=team_id)


@router.patch(
    "/skills/{slug}",
    response=SkillDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def update_skill(request, slug: str, payload: UpdateSkillIn, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    workspace = request.workspace
    update_fields = ["updated_at"]

    if payload.title is not None:
        skill.title = payload.title
        update_fields.append("title")
    if payload.description is not None:
        skill.description = payload.description
        update_fields.append("description")
    if payload.owner_id is not None:
        if not Membership.objects.filter(workspace=workspace, user_id=payload.owner_id).exists():
            raise HttpError(400, "Owner is not a workspace member")
        from apps.accounts.models import User

        skill.owner = User.objects.get(id=payload.owner_id)
        update_fields.append("owner")

    if payload.visibility is not None:
        if payload.visibility not in VisibilityChoices.values:
            raise HttpError(400, f"Invalid visibility: {payload.visibility}")
        if (
            payload.visibility == VisibilityChoices.WORKSPACE
            and skill.visibility != VisibilityChoices.WORKSPACE
        ):
            membership = getattr(request, "membership", None)
            if membership is None or membership.role != RoleChoices.ADMIN:
                raise HttpError(403, "Only admins can set workspace-wide visibility")
        skill.visibility = payload.visibility
        update_fields.append("visibility")

    skill.save(update_fields=update_fields)

    if payload.shared_with_ids is not None:
        _set_skill_shared_with(skill, payload.shared_with_ids, workspace)

    if skill.status == StatusChoices.PUBLISHED and skill.current_version_id:
        queue_skill_discovery_embedding(str(skill.current_version_id))

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)
    membership = getattr(request, "membership", None)
    team_id = membership.team_id if membership and membership.team_id else None
    return _skill_detail_out(skill, requester_team_id=team_id)


SANDBOX_ROLE_ORDER = {
    RoleChoices.MEMBER: 0,
    RoleChoices.TEAM_MANAGER: 1,
    RoleChoices.ADMIN: 2,
}


def _resolve_sandbox_min_role(workspace_id) -> str:
    """
    Sandbox access is a workspace-level capability, not a per-skill permission.
    Per-skill ACLs (visibility, shared_with, system_kind) already do per-skill
    filtering; this gate only decides who is allowed to use the sandbox tool
    at all in this workspace.
    """
    effective = get_effective_settings(workspace_id)
    raw = effective.get("sandbox_min_role")
    if isinstance(raw, str) and raw in SANDBOX_ROLE_ORDER:
        return raw
    return RoleChoices.MEMBER


def _check_sandbox_access(request, skill: Skill):
    """Raise 403 if the caller's workspace role is below the sandbox threshold."""
    if getattr(request, "agent", None) is not None:
        return
    if hasattr(request, "api_key") or hasattr(request, "oauth_token"):
        return  # API/OAuth callers are already scoped via API key permissions
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(403, "Sandbox access requires authentication")

    membership = (
        Membership.objects.filter(workspace=skill.department.team.workspace, user=user)
        .order_by("-role")
        .first()
    )
    if membership is None:
        raise HttpError(403, "You do not have sandbox access in this workspace")
    user_rank = SANDBOX_ROLE_ORDER.get(membership.role, -1)
    required_rank = SANDBOX_ROLE_ORDER.get(
        _resolve_sandbox_min_role(skill.department.team.workspace_id), 0
    )
    if user_rank < required_rank:
        raise HttpError(
            403,
            "Your workspace role does not include sandbox access. Ask an admin to lower the "
            "sandbox minimum role.",
        )


def _check_skill_execute_access(request, skill: Skill):
    if skill.status != StatusChoices.PUBLISHED:
        raise HttpError(404, "Skill not found")

    agent = getattr(request, "agent", None)
    if agent is not None:
        return

    qs = Skill.objects.filter(pk=skill.pk)
    if hasattr(request, "api_key"):
        allowed = apply_api_key_scope(request.api_key, qs)
    elif hasattr(request, "oauth_token"):
        allowed = apply_oauth_connection_scope(request, qs)
    else:
        allowed = apply_membership_scope(request, qs)

    if not allowed.exists():
        raise HttpError(404, "Skill not found")

    _check_sandbox_access(request, skill)


def _caller_type(request) -> str:
    if getattr(request, "agent", None) is not None:
        return SkillExecutionRun.CallerTypeChoices.AGENT
    if getattr(request, "api_key", None) is not None:
        return SkillExecutionRun.CallerTypeChoices.API_KEY
    if getattr(request, "oauth_token", None) is not None:
        return SkillExecutionRun.CallerTypeChoices.OAUTH
    return SkillExecutionRun.CallerTypeChoices.USER


def _mark_run_failed_after_dispatch_error(run: SkillExecutionRun, exc: BaseException) -> None:
    """Flip the run to FAILED so it stops blocking concurrency / quota.

    `dispatch_execution_run` may raise after the run row has been created
    (e.g. missing entrypoint, GCS upload error, Cloud Run API error). Without
    this safety net the run sits in QUEUED forever and prevents new runs
    from being accepted.
    """
    run.refresh_from_db()
    if run.status in TERMINAL_STATUSES:
        return

    message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
    now = timezone.now()
    run.status = SkillExecutionRun.StatusChoices.FAILED
    run.error_message = (message or "Dispatch failed")[:4000]
    if run.started_at is None:
        run.started_at = now
    run.finished_at = now
    run.save(
        update_fields=[
            "status",
            "error_message",
            "started_at",
            "finished_at",
            "updated_at",
        ]
    )


@router.get(
    "/skills/{slug}/execution",
    response=SkillExecutionSpecOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_skill_execution_spec(request, slug: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    _check_skill_execute_access(request, skill) if skill.execution_enabled else None
    return _execution_spec_out(skill)


@router.patch(
    "/skills/{slug}/execution",
    response=SkillExecutionSpecOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def update_skill_execution_spec(
    request,
    slug: str,
    payload: UpdateSkillExecutionSpecIn,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    if payload.enabled and not skill.current_version_id:
        raise HttpError(400, "Publish or create a skill version before enabling execution")
    if payload.network.policy == "egress_allowlist" and not isinstance(
        payload.network.allowed, list
    ):
        raise HttpError(400, "Network allowlist must be a list")
    secret_ref_names = [ref.name for ref in payload.secret_refs]
    if len(secret_ref_names) != len(set(secret_ref_names)):
        raise HttpError(400, "Secret names must be unique per skill")

    spec, _created = SkillExecutionSpec.objects.get_or_create(skill=skill)
    spec.version = skill.current_version
    spec.runtime = payload.runtime
    spec.latency_class = payload.latency_class
    spec.entrypoint_path = payload.entrypoint_path
    spec.input_schema = payload.input_schema
    spec.output_schema = payload.output_schema
    spec.secrets_scope = payload.secrets_scope
    spec.network_policy = payload.network.policy
    spec.allowed_egress = [str(host) for host in payload.network.allowed if str(host).strip()]
    spec.timeout_seconds = payload.limits.timeout_seconds
    spec.memory_mb = payload.limits.memory_mb
    spec.max_output_bytes_inline = payload.limits.max_output_bytes_inline
    spec.max_runs_per_day = payload.limits.max_runs_per_day
    spec.max_concurrent_runs = payload.limits.max_concurrent_runs
    spec.save()
    _sync_secret_refs(spec, payload.secret_refs)

    skill.execution_enabled = payload.enabled
    skill.save(update_fields=["execution_enabled", "updated_at"])
    return _execution_spec_out(skill)


@router.post(
    "/skills/{slug}/execute",
    response={201: SkillExecutionRunOut},
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
def execute_skill(
    request,
    slug: str,
    payload: ExecuteSkillIn,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, allow_draft=False, system_kind=system_kind)
    _check_skill_execute_access(request, skill)
    if not skill.execution_enabled:
        raise HttpError(400, "Skill execution is not enabled")
    if not skill.current_version_id:
        raise HttpError(400, "Skill has no published version to execute")
    try:
        spec = skill.execution_spec
    except SkillExecutionSpec.DoesNotExist:
        raise HttpError(400, "Skill has no execution specification")

    validate_execution_inputs(payload.inputs, spec)
    approval_required = requires_execution_approval(skill)
    status = (
        SkillExecutionRun.StatusChoices.PENDING_APPROVAL
        if approval_required and not payload.approved
        else SkillExecutionRun.StatusChoices.QUEUED
    )
    if status != SkillExecutionRun.StatusChoices.PENDING_APPROVAL:
        enforce_skill_concurrency(spec)
        enforce_skill_quota(spec)

    run = SkillExecutionRun.objects.create(
        workspace=skill.department.team.workspace,
        skill=skill,
        version=skill.current_version,
        spec=spec,
        department=skill.department,
        user=request.user
        if getattr(request, "user", None) and request.user.is_authenticated
        else None,
        agent=getattr(request, "agent", None),
        caller_type=_caller_type(request),
        status=status,
        inputs=payload.inputs,
        input_hash=canonical_input_hash(payload.inputs),
        approved_by=(
            request.user
            if payload.approved and getattr(request, "user", None) and request.user.is_authenticated
            else None
        ),
        approved_at=timezone.now() if payload.approved else None,
        expires_at=run_expiry(),
    )

    if status != SkillExecutionRun.StatusChoices.PENDING_APPROVAL:
        try:
            dispatch_execution_run(run)
        except Exception as exc:
            _mark_run_failed_after_dispatch_error(run, exc)
            raise

    run = SkillExecutionRun.objects.select_related("skill", "version", "agent", "user").get(
        pk=run.pk
    )
    return Status(201, _execution_run_out(run))


@router.get(
    "/skills/{slug}/secrets",
    response=SkillSecretListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def list_skill_secrets(request, slug: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    items = _skill_secret_status_items(skill)
    return {"items": items, "count": len(items)}


@router.put(
    "/skills/{slug}/secrets/{name}",
    response=SkillSecretStatusOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def upsert_skill_secret(
    request,
    slug: str,
    name: str,
    payload: UpsertSkillSecretValueIn,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    try:
        spec = skill.execution_spec
    except SkillExecutionSpec.DoesNotExist:
        raise HttpError(400, "Skill has no execution specification")

    try:
        ref = spec.secret_refs.get(name=name)
    except SkillSecretDeclaration.DoesNotExist:
        raise HttpError(404, "Secret declaration not found on this skill")

    has_value = payload.value is not None and payload.value != ""
    has_ref = payload.vault_ref is not None and payload.vault_ref.strip() != ""
    if has_value and has_ref:
        raise HttpError(400, "Provide either 'value' or 'vault_ref', not both.")
    if not has_value and not has_ref:
        raise HttpError(
            400,
            "Provide one of 'value' (stored encrypted) or 'vault_ref' (external vault reference).",
        )

    setter = request.user if request.user.is_authenticated else None
    if has_ref:
        parsed = parse_vault_ref(payload.vault_ref)
        defaults = {
            "wrapped_dek": b"",
            "ciphertext": b"",
            "kms_key_version": "",
            "vault_ref": str(parsed),
            "last_set_by": setter,
        }
    else:
        encrypted = encrypt_secret_value(payload.value)
        defaults = {
            "wrapped_dek": encrypted.wrapped_dek,
            "ciphertext": encrypted.ciphertext,
            "kms_key_version": encrypted.kms_key_version,
            "vault_ref": "",
            "last_set_by": setter,
        }
    row, _created = SkillSecretValue.objects.update_or_create(
        skill=skill,
        workspace=skill.department.team.workspace,
        name=ref.name,
        scope=ref.scope,
        defaults=defaults,
    )
    return {
        "name": ref.name,
        "scope": ref.scope,
        "required": bool(ref.required),
        "description": ref.description or "",
        "is_set": True,
        "kind": "vault_ref" if has_ref else "encrypted",
        "vault_ref": row.vault_ref or None,
        "last_set_at": row.updated_at.isoformat(),
        "last_set_by": _user_brief(row.last_set_by),
    }


@router.delete(
    "/skills/{slug}/secrets/{name}",
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def delete_skill_secret(request, slug: str, name: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    try:
        spec = skill.execution_spec
    except SkillExecutionSpec.DoesNotExist:
        raise HttpError(400, "Skill has no execution specification")
    try:
        ref = spec.secret_refs.get(name=name)
    except SkillSecretDeclaration.DoesNotExist:
        raise HttpError(404, "Secret declaration not found on this skill")
    workspace = skill.department.team.workspace
    SkillSecretValue.objects.filter(
        skill=skill,
        workspace=workspace,
        name=ref.name,
        scope=ref.scope,
    ).delete()
    return {"ok": True}


@router.post(
    "/skill-executions/{run_id}/callback",
    response=SkillExecutionRunOut,
    auth=None,
    throttle=[ExecutionCallbackThrottle()],
    include_in_schema=False,
)
def callback_skill_execution_run(request, run_id: str, payload: SkillExecutionCallbackIn):
    auth_header = request.headers.get("authorization", "")
    token = (
        auth_header[len("Bearer ") :].strip() if auth_header.lower().startswith("bearer ") else ""
    )
    if not validate_callback_token(token, run_id):
        raise HttpError(401, "Invalid execution callback token")

    try:
        run = SkillExecutionRun.objects.select_related("skill", "version", "spec").get(id=run_id)
    except SkillExecutionRun.DoesNotExist:
        raise HttpError(404, "Execution run not found")

    apply_execution_callback(
        run,
        status=payload.status,
        output=payload.output,
        output_uri=payload.output_uri,
        logs_uri=payload.logs_uri,
        error_message=payload.error_message,
        resource_usage=payload.resource_usage,
    )
    run = SkillExecutionRun.objects.select_related("skill", "version", "agent", "user").get(
        pk=run.pk
    )
    return _execution_run_out(run)


@router.post(
    "/skill-executions/{run_id}/secrets",
    response=ExecutionSecretsFetchOut,
    auth=None,
    throttle=[ExecutionCallbackThrottle()],
    include_in_schema=False,
)
def fetch_skill_execution_secrets(request, run_id: str):
    from django.db import transaction

    auth_header = request.headers.get("authorization", "")
    token = (
        auth_header[len("Bearer ") :].strip() if auth_header.lower().startswith("bearer ") else ""
    )
    allowed_names = validate_secret_fetch_token(token, run_id)
    if allowed_names is None:
        raise HttpError(401, "Invalid execution secret token")

    with transaction.atomic():
        try:
            run = (
                SkillExecutionRun.objects.select_for_update()
                .select_related("skill", "workspace")
                .get(id=run_id)
            )
        except SkillExecutionRun.DoesNotExist:
            raise HttpError(404, "Execution run not found")

        if run.secrets_fetched_at is not None:
            raise HttpError(409, "Execution secrets were already fetched")
        if run.status in {
            SkillExecutionRun.StatusChoices.SUCCEEDED,
            SkillExecutionRun.StatusChoices.FAILED,
            SkillExecutionRun.StatusChoices.TIMEOUT,
            SkillExecutionRun.StatusChoices.CANCELLED,
        }:
            raise HttpError(409, "Execution run is already terminal")

        values = fetch_run_secret_values(run, allowed_names=allowed_names)
        run.secrets_fetched_at = timezone.now()
        run.save(update_fields=["secrets_fetched_at", "updated_at"])
    return {"values": values}


@router.get(
    "/skills/{slug}/executions",
    response=SkillExecutionRunListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_skill_execution_runs(
    request,
    slug: str,
    limit: int = 20,
    offset: int = 0,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, allow_draft=False, system_kind=system_kind)
    _check_skill_execute_access(request, skill)
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    qs = SkillExecutionRun.objects.select_related("skill", "version", "agent", "user").filter(
        skill=skill
    )
    agent = getattr(request, "agent", None)
    if agent is not None:
        qs = qs.filter(agent=agent)
    elif getattr(request, "user", None) and request.user.is_authenticated:
        qs = qs.filter(user=request.user)
    count = qs.count()
    return {
        "items": [_execution_run_out(run) for run in qs[offset : offset + limit]],
        "count": count,
    }


@router.get(
    "/skill-executions/{run_id}",
    response=SkillExecutionRunOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_skill_execution_run(request, run_id: str):
    try:
        run = SkillExecutionRun.objects.select_related(
            "skill__department__team",
            "version",
            "agent",
            "user",
        ).get(id=run_id, workspace=request.workspace)
    except SkillExecutionRun.DoesNotExist:
        raise HttpError(404, "Execution run not found")

    _check_skill_execute_access(request, run.skill)
    agent = getattr(request, "agent", None)
    if agent is not None and run.agent_id != agent.id:
        raise HttpError(404, "Execution run not found")
    if (
        agent is None
        and getattr(request, "user", None)
        and request.user.is_authenticated
        and run.user_id
        and run.user_id != request.user.id
    ):
        raise HttpError(404, "Execution run not found")
    return _execution_run_out(run)


def _load_run_for_caller(request, run_id: str) -> SkillExecutionRun:
    try:
        run = SkillExecutionRun.objects.select_related(
            "skill__department__team",
            "version",
            "agent",
            "user",
            "spec",
        ).get(id=run_id, workspace=request.workspace)
    except SkillExecutionRun.DoesNotExist:
        raise HttpError(404, "Execution run not found")

    _check_skill_execute_access(request, run.skill)
    agent = getattr(request, "agent", None)
    if agent is not None and run.agent_id != agent.id:
        raise HttpError(404, "Execution run not found")
    if (
        agent is None
        and getattr(request, "user", None)
        and request.user.is_authenticated
        and run.user_id
        and run.user_id != request.user.id
    ):
        raise HttpError(404, "Execution run not found")
    return run


MAX_INLINE_LOGS_BYTES = 256 * 1024


def _fetch_run_logs(run: SkillExecutionRun) -> tuple[str, bool, str]:
    """Return (logs_text, truncated, source). Best-effort, never raises."""
    if not run.logs_uri:
        return "", False, "none"
    if not run.logs_uri.startswith("gs://"):
        return "", False, "unsupported"
    try:
        from google.cloud import storage  # type: ignore[import-not-found]

        from apps.skills.execution_artifacts import split_gs_uri
    except ImportError:
        return "", False, "unavailable"
    try:
        bucket_name, blob_name = split_gs_uri(run.logs_uri)
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(blob_name)
        if not blob.exists(client):
            return "", False, "missing"
        size = blob.size or 0
        if size > MAX_INLINE_LOGS_BYTES:
            data = blob.download_as_bytes(start=size - MAX_INLINE_LOGS_BYTES, end=size - 1)
            text = data.decode("utf-8", errors="replace")
            return text, True, "gcs"
        text = blob.download_as_text()
        return text, False, "gcs"
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Could not fetch execution logs for run %s: %s", run.id, exc)
        return "", False, "error"


@router.get(
    "/skill-executions/{run_id}/logs",
    response=SkillExecutionRunLogsOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_skill_execution_run_logs(request, run_id: str):
    run = _load_run_for_caller(request, run_id)
    logs, truncated, source = _fetch_run_logs(run)
    available = source == "gcs"
    return {
        "run_id": str(run.id),
        "status": run.status,
        "logs": logs,
        "truncated": truncated,
        "available": available,
        "source": source,
    }


@router.post(
    "/skill-executions/{run_id}/cancel",
    response=SkillExecutionRunOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
def cancel_skill_execution_run(request, run_id: str):
    run = _load_run_for_caller(request, run_id)
    if run.status not in EXECUTION_CANCELLABLE_STATUSES:
        raise HttpError(409, "Execution run is already terminal")

    now = timezone.now()
    run.status = SkillExecutionRun.StatusChoices.CANCELLED
    update_fields = ["status", "updated_at"]
    if run.started_at is None:
        run.started_at = now
        update_fields.append("started_at")
    run.finished_at = now
    update_fields.append("finished_at")
    if not run.error_message:
        run.error_message = "Execution cancelled by user"
        update_fields.append("error_message")
    run.save(update_fields=update_fields)

    run = SkillExecutionRun.objects.select_related("skill", "version", "agent", "user").get(
        pk=run.pk
    )
    return _execution_run_out(run)


@router.get(
    "/sandbox/overview",
    response=SandboxOverviewOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
    include_in_schema=False,
)
def sandbox_overview(request):
    workspace = request.workspace
    user = getattr(request, "user", None)

    membership = None
    if user is not None and user.is_authenticated:
        membership = (
            Membership.objects.filter(workspace=workspace, user=user).order_by("-role").first()
        )
    user_role = membership.role if membership else None

    effective = get_effective_settings(workspace.id)
    raw_min_role = effective.get("sandbox_min_role")
    workspace_min_role = (
        raw_min_role
        if isinstance(raw_min_role, str) and raw_min_role in SANDBOX_ROLE_ORDER
        else RoleChoices.MEMBER
    )

    if user_role is None:
        can_use = False
    else:
        can_use = SANDBOX_ROLE_ORDER.get(user_role, -1) >= SANDBOX_ROLE_ORDER.get(
            workspace_min_role, 0
        )

    base_qs = Skill.objects.filter(
        execution_enabled=True,
        status=StatusChoices.PUBLISHED,
        department__team__workspace=workspace,
    )
    if hasattr(request, "api_key"):
        base_qs = apply_api_key_scope(request.api_key, base_qs)
    elif hasattr(request, "oauth_token"):
        base_qs = apply_oauth_connection_scope(request, base_qs)
    else:
        base_qs = apply_membership_scope(request, base_qs)

    base_qs = base_qs.select_related("department__team")
    skills_list = list(base_qs[:200])

    twenty_four_h_ago = timezone.now() - timedelta(hours=24)
    skill_ids = [s.id for s in skills_list]
    runs_24h_map: dict[str, int] = {}
    failures_24h_map: dict[str, int] = {}
    last_run_map: dict[str, SkillExecutionRun] = {}
    if skill_ids:
        recent_runs_qs = (
            SkillExecutionRun.objects.filter(
                skill_id__in=skill_ids,
                workspace=workspace,
            )
            .select_related("skill", "version", "agent", "user")
            .order_by("skill_id", "-created_at")
        )
        for run in recent_runs_qs:
            sid = str(run.skill_id)
            if sid not in last_run_map:
                last_run_map[sid] = run
            if run.created_at >= twenty_four_h_ago:
                runs_24h_map[sid] = runs_24h_map.get(sid, 0) + 1
                if run.status in {
                    SkillExecutionRun.StatusChoices.FAILED,
                    SkillExecutionRun.StatusChoices.TIMEOUT,
                }:
                    failures_24h_map[sid] = failures_24h_map.get(sid, 0) + 1

    items = []
    for skill in skills_list:
        sid = str(skill.id)
        latest = last_run_map.get(sid)
        items.append(
            {
                "id": sid,
                "slug": skill.slug,
                "title": skill.title,
                "description": skill.description or "",
                "status": skill.status,
                "department_name": skill.department.name,
                "team_name": skill.department.team.name,
                "system_kind": skill.department.team.system_kind or "",
                "execution_enabled": skill.execution_enabled,
                "latest_run": _execution_run_out(latest) if latest else None,
                "last_run_at": latest.created_at.isoformat() if latest else None,
                "runs_24h": runs_24h_map.get(sid, 0),
                "failures_24h": failures_24h_map.get(sid, 0),
            }
        )

    return {
        "skills": items,
        "can_use_sandbox": can_use,
        "workspace_min_role": workspace_min_role,
        "user_role": user_role,
    }


@router.post(
    "/skills/{slug}/versions/{version_number}/files/{path}/ai-edit",
    auth=api_or_session,
    throttle=[MutationThrottle()],
    include_in_schema=False,
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def stream_skill_file_ai_edit(
    request,
    slug: str,
    version_number: int,
    path: str,
    payload: SkillFileAiEditIn,
    system_kind: str | None = "",
):
    from apps.skills.ai_edit import stream_ai_edit

    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)

    try:
        version = SkillVersion.objects.get(skill=skill, version_number=version_number)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    files = resolve_files(skill.id, version.version_number)
    file = files.get(path)
    if file is None:
        raise HttpError(404, "File not found in this version")
    if not is_text_file(file):
        raise HttpError(400, "AI edit only supports text files")

    file_content = file_bytes(file).decode("utf-8", errors="replace")

    recent_error: str | None = None
    recent_logs: str | None = None
    if payload.run_id:
        try:
            run = SkillExecutionRun.objects.select_related("skill").get(
                id=payload.run_id, workspace=request.workspace, skill=skill
            )
        except SkillExecutionRun.DoesNotExist:
            run = None
        if run is not None:
            recent_error = run.error_message or None
            try:
                logs_text, _truncated, source = _fetch_run_logs(run)
                if source == "gcs":
                    recent_logs = logs_text or None
            except Exception:
                recent_logs = None

    input_schema: dict | None = None
    entrypoint_path: str | None = None
    spec = getattr(skill, "execution_spec", None)
    if spec is not None:
        if isinstance(spec.input_schema, dict) and spec.input_schema:
            input_schema = spec.input_schema
        if spec.entrypoint_path:
            entrypoint_path = spec.entrypoint_path

    skill_description = (skill.description or skill.title or "").strip() or None

    def stream_iter():
        yield from stream_ai_edit(
            file_path=file.path,
            file_type=file.file_type,
            file_content=file_content,
            instruction=payload.instruction,
            skill_description=skill_description,
            input_schema=input_schema,
            recent_error=recent_error,
            recent_logs=recent_logs,
            entrypoint_path=entrypoint_path,
            model=payload.model,
        )

    response = StreamingHttpResponse(
        streaming_content=stream_iter(),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response


@router.delete("/skills/{slug}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def delete_skill(request, slug: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    skill.delete()
    return {"ok": True}


@router.delete(
    "/skills/{slug}/shared-with/my-team",
    response=SkillDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.TEAM_MANAGER)
def unshare_from_my_team(request, slug: str, system_kind: str | None = ""):
    """Remove the requester's team from a skill's shared_with list."""
    from apps.orgs.models import Department

    skill = _get_skill(request, slug, system_kind=system_kind)
    membership = getattr(request, "membership", None)
    if not membership or not membership.team_id:
        raise HttpError(400, "No team context")

    team_dept_ids = set(
        Department.objects.filter(team_id=membership.team_id).values_list("id", flat=True)
    )
    current_shared = set(skill.shared_with.values_list("id", flat=True))
    overlap = team_dept_ids & current_shared
    if not overlap:
        raise HttpError(400, "Process is not shared with your team")

    new_shared = current_shared - overlap
    if new_shared:
        skill.shared_with.set(Department.objects.filter(id__in=new_shared))
    else:
        skill.shared_with.clear()

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)
    return _skill_detail_out(skill, requester_team_id=membership.team_id)


# ── Version Endpoints ────────────────────────────────────────────────────


@router.post(
    "/skills/{slug}/versions",
    response={201: SkillVersionOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def create_version(request, slug: str, payload: CreateVersionIn, system_kind: str | None = ""):
    oauth_token = getattr(request, "oauth_token", None)
    if oauth_token is not None and "skills:write" not in oauth_token.scope.split():
        raise HttpError(403, "OAuth token missing required scope: skills:write")

    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)

    if oauth_token is not None:
        dept = skill.department
        effective = get_effective_settings(
            dept.team.workspace_id,
            team_id=dept.team_id,
            department_id=dept.id,
        )
        if effective.get("allow_agent_skill_updates") is not True:
            raise HttpError(403, "Agent skill updates are not enabled for this workspace.")

    metadata_dict = _empty_metadata_dict()
    if payload.koinoflow_metadata is not None:
        metadata_dict = _normalize_metadata(payload.koinoflow_metadata.model_dump())

    from django.db import transaction

    with transaction.atomic():
        latest = (
            SkillVersion.objects.select_for_update()
            .filter(skill=skill)
            .order_by("-version_number")
            .first()
        )
        latest_metadata = (
            _normalize_metadata(latest.koinoflow_metadata) if latest else _empty_metadata_dict()
        )
        metadata_unchanged = metadata_dict == latest_metadata
        if latest and (
            latest.content_md == payload.content_md
            and latest.frontmatter_yaml == (payload.frontmatter_yaml or "")
            and not payload.files
            and metadata_unchanged
        ):
            raise HttpError(409, "No changes detected since the last version")

        max_num = latest.version_number if latest else 0
        version = SkillVersion.objects.create(
            skill=skill,
            version_number=max_num + 1,
            content_md=sanitize_content_md(payload.content_md),
            frontmatter_yaml=sanitize_frontmatter(payload.frontmatter_yaml or ""),
            change_summary=payload.change_summary,
            authored_by=request.user if request.user.is_authenticated else None,
            koinoflow_metadata=metadata_dict,
        )

        if payload.files is not None:
            submitted = [_file_entry_from_payload(f.model_dump()) for f in payload.files]
            creates, tombstones = compute_file_delta(
                skill.id,
                latest.version_number if latest else None,
                submitted,
            )
            file_rows = []
            for f in creates:
                file_rows.append(_version_file_from_entry(version, f))
            for t in tombstones:
                file_rows.append(
                    _version_file_from_entry(version, {"path": t["path"]}, is_deleted=True)
                )
            if file_rows:
                VersionFile.objects.bulk_create(file_rows)

    return Status(201, _version_out(version))


@router.get(
    "/skills/{slug}/versions",
    response=VersionListOut,
    auth=api_or_session,
)
def list_versions(
    request,
    slug: str,
    limit: int = 50,
    offset: int = 0,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, system_kind=system_kind)
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        SkillVersion.objects.filter(skill=skill)
        .select_related("authored_by", "reverted_from")
        .order_by("-version_number")
    )
    count = qs.count()
    items = [_version_brief_out(v) for v in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.get(
    "/skills/{slug}/versions/{version_number}",
    response=SkillVersionOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version(request, slug: str, version_number: int, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    try:
        version = SkillVersion.objects.select_related("authored_by", "reverted_from").get(
            skill=skill, version_number=version_number
        )
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    return _version_out(version)


class UpdateVersionIn(Schema):
    change_summary: str


@router.patch(
    "/skills/{slug}/versions/{version_number}",
    response=SkillVersionBriefOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def update_version(
    request,
    slug: str,
    version_number: int,
    payload: UpdateVersionIn,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    try:
        version = SkillVersion.objects.select_related("authored_by").get(
            skill=skill, version_number=version_number
        )
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    version.change_summary = payload.change_summary
    version.save(update_fields=["change_summary", "updated_at"])
    return _version_brief_out(version)


@router.post(
    "/skills/{slug}/versions/{target_version_number}/revert",
    response={201: SkillVersionOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def revert_version(
    request,
    slug: str,
    target_version_number: int,
    payload: RevertVersionIn,
    system_kind: str | None = "",
):
    from django.db import transaction

    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)

    try:
        target = SkillVersion.objects.get(skill=skill, version_number=target_version_number)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Target version not found")

    with transaction.atomic():
        latest = (
            SkillVersion.objects.select_for_update()
            .filter(skill=skill)
            .order_by("-version_number")
            .first()
        )

        if target_version_number == latest.version_number:
            raise HttpError(409, "Target version is already the latest version")

        target_files = resolve_files(skill.id, target_version_number)
        submitted_files = [
            {
                "path": f.path,
                "content": f.content,
                "content_bytes": file_bytes(f),
                "file_type": f.file_type,
                "mime_type": f.mime_type,
                "encoding": f.encoding,
                "sha256": f.sha256,
                "size_bytes": f.size_bytes,
            }
            for f in target_files.values()
        ]

        # Identity check: reject if target content + files identical to latest
        content_same = (
            target.content_md == latest.content_md
            and target.frontmatter_yaml == latest.frontmatter_yaml
            and _normalize_metadata(target.koinoflow_metadata)
            == _normalize_metadata(latest.koinoflow_metadata)
        )
        if content_same:
            latest_files = resolve_files(skill.id, latest.version_number)
            if set(target_files.keys()) == set(latest_files.keys()) and all(
                file_bytes(target_files[p]) == file_bytes(latest_files[p]) for p in target_files
            ):
                raise HttpError(409, "No changes detected since the last version")

        creates, tombstones = compute_file_delta(skill.id, latest.version_number, submitted_files)

        summary = payload.change_summary.strip() or f"Reverted to version {target_version_number}"

        new_version = SkillVersion.objects.create(
            skill=skill,
            version_number=latest.version_number + 1,
            content_md=target.content_md,
            frontmatter_yaml=target.frontmatter_yaml,
            koinoflow_metadata=_normalize_metadata(target.koinoflow_metadata),
            change_summary=summary,
            authored_by=request.user if request.user.is_authenticated else None,
            reverted_from=target,
        )

        file_rows = []
        for f in creates:
            file_rows.append(_version_file_from_entry(new_version, f))
        for t in tombstones:
            file_rows.append(
                _version_file_from_entry(new_version, {"path": t["path"]}, is_deleted=True)
            )
        if file_rows:
            VersionFile.objects.bulk_create(file_rows)

    return Status(201, _version_out(new_version))


@router.get(
    "/skills/{slug}/versions/{version_number}/files",
    response=list[VersionFileOut],
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_version_files(request, slug: str, version_number: int, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    try:
        SkillVersion.objects.get(skill=skill, version_number=version_number)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    return resolve_file_list(skill.id, version_number)


@router.get(
    "/skills/{slug}/versions/{version_number}/files/{path:path}",
    response=VersionFileDetailOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_file(
    request,
    slug: str,
    version_number: int,
    path: str,
    system_kind: str | None = "",
):
    skill = _get_skill(request, slug, system_kind=system_kind)
    try:
        SkillVersion.objects.get(skill=skill, version_number=version_number)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    files = resolve_files(skill.id, version_number)
    if path not in files:
        raise HttpError(404, "File not found")
    f = files[path]
    return _file_detail(f)


@router.get(
    "/skills/{slug}/versions/{version_number}/file-diff",
    response=FileDiffOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_file_diff(request, slug: str, version_number: int, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    try:
        SkillVersion.objects.get(skill=skill, version_number=version_number)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    if version_number <= 1:
        raise HttpError(400, "No previous version to diff against")

    try:
        SkillVersion.objects.get(skill=skill, version_number=version_number - 1)
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Previous version not found")

    old_files = resolve_files(skill.id, version_number - 1)
    new_files = resolve_files(skill.id, version_number)

    return {
        "old_version_number": version_number - 1,
        "new_version_number": version_number,
        "entries": _compute_file_diff_entries(old_files, new_files),
    }


@router.get(
    "/skills/{slug}/versions/{version_number}/diff",
    response=VersionDiffOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_diff(request, slug: str, version_number: int, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    try:
        new_version = SkillVersion.objects.select_related("authored_by").get(
            skill=skill, version_number=version_number
        )
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    if version_number <= 1:
        raise HttpError(400, "No previous version to diff against")

    try:
        old_version = SkillVersion.objects.select_related("authored_by").get(
            skill=skill, version_number=version_number - 1
        )
    except SkillVersion.DoesNotExist:
        raise HttpError(404, "Previous version not found")

    old_text = old_version.content_md.rstrip() + "\n"
    new_text = new_version.content_md.rstrip() + "\n"
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, n=3)

    hunks = []
    current_hunk = None
    additions = 0
    deletions = 0

    for line in diff:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            parts = line.split("@@")
            range_info = parts[1].strip()
            old_range, new_range = range_info.split(" ")
            old_start, old_count = _parse_range(old_range[1:])
            new_start, new_count = _parse_range(new_range[1:])
            current_hunk = {
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": [],
            }
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif current_hunk is not None:
            stripped = line.rstrip("\n\r")
            current_hunk["lines"].append(stripped)
            if line.startswith("+"):
                additions += 1
            elif line.startswith("-"):
                deletions += 1

    if current_hunk:
        hunks.append(current_hunk)

    old_file_set = resolve_files(skill.id, version_number - 1)
    new_file_set = resolve_files(skill.id, version_number)

    return {
        "old_version": _version_brief_out(old_version),
        "new_version": _version_brief_out(new_version),
        "hunks": hunks,
        "stats": {
            "additions": additions,
            "deletions": deletions,
            "total_hunks": len(hunks),
        },
        "file_diff": _compute_file_diff_entries(old_file_set, new_file_set),
    }


def _parse_range(range_str: str):
    if "," in range_str:
        start, count = range_str.split(",")
        return int(start), int(count)
    return int(range_str), 1


# ── Publish ──────────────────────────────────────────────────────────────


@router.post(
    "/skills/{slug}/publish",
    response=SkillDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def publish_skill(request, slug: str, system_kind: str | None = ""):
    from django.db import transaction

    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    latest = SkillVersion.objects.filter(skill=skill).order_by("-version_number").first()
    if not latest:
        raise HttpError(400, "No versions to publish")

    dept = skill.department
    effective = get_effective_settings(
        dept.team.workspace_id, team_id=dept.team_id, department_id=dept.id
    )
    if (
        effective.get("require_change_summary")
        and latest.version_number > 1
        and not latest.change_summary.strip()
    ):
        raise HttpError(400, "A change summary is required before publishing")

    skill.current_version = latest
    skill.status = StatusChoices.PUBLISHED
    skill.last_reviewed_at = timezone.now()
    skill.save(update_fields=["current_version", "status", "last_reviewed_at", "updated_at"])
    transaction.on_commit(lambda: queue_skill_discovery_embedding(str(latest.id), force=True))

    try:
        spec = skill.execution_spec
        if spec.version_id != latest.id:
            spec.version = latest
            spec.save(update_fields=["version"])
    except SkillExecutionSpec.DoesNotExist:
        pass

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)
    from apps.orgs.onboarding import sync_onboarding_state

    sync_onboarding_state(dept.team.workspace)
    return _skill_detail_out(skill)


# ── Review ────────────────────────────────────────────────────────────────


@router.post(
    "/skills/{slug}/review",
    response=SkillDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def review_skill(request, slug: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)
    skill.last_reviewed_at = timezone.now()
    skill.save(update_fields=["last_reviewed_at", "updated_at"])

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)
    return _skill_detail_out(skill)


# ── Export / Import ─────────────────────────────────────────────────────


_KOINOFLOW_METADATA_SIDECAR = "koinoflow-metadata.json"


def _build_skill_md(skill, version):
    """Build a SKILL.md string from a skill version's frontmatter + content.

    koinoflow_metadata is NEVER written into the SKILL.md frontmatter — it is
    Koinoflow-native metadata and does not belong in a Claude-format export.
    Only fields already present in frontmatter_yaml (Claude-compat) are emitted.
    """
    fm_dict = {}
    if version.frontmatter_yaml:
        try:
            fm_dict = yaml.safe_load(version.frontmatter_yaml) or {}
        except yaml.YAMLError:
            pass

    if not fm_dict.get("name"):
        fm_dict["name"] = skill.slug
    if not fm_dict.get("description"):
        fm_dict["description"] = skill.description

    fm_yaml = yaml.dump(fm_dict, default_flow_style=False, allow_unicode=True).strip()
    return f"---\n{fm_yaml}\n---\n\n{version.content_md}\n"


def _parse_skill_md(text):
    """Parse a SKILL.md file into (frontmatter_dict, content_md)."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.DOTALL)
    if match:
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        return fm, match.group(2).strip()
    return {}, text.strip()


@router.get("/skills/{slug}/export", auth=api_or_session, throttle=[ReadThrottle()])
def export_skill(request, slug: str, system_kind: str | None = ""):
    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    skill = _get_skill(
        request,
        slug,
        allow_draft=not (is_api_key or is_oauth),
        system_kind=system_kind,
    )
    if is_api_key:
        allowed = apply_api_key_scope(request.api_key, Skill.objects.filter(pk=skill.pk))
        if not allowed.exists():
            raise HttpError(404, "Skill not found")
    elif is_oauth:
        allowed = apply_oauth_connection_scope(request, Skill.objects.filter(pk=skill.pk))
        if not allowed.exists():
            raise HttpError(404, "Skill not found")

    version = skill.current_version
    if not version:
        latest = SkillVersion.objects.filter(skill=skill).order_by("-version_number").first()
        if not latest:
            raise HttpError(400, "No versions to export")
        version = latest

    skill_md = _build_skill_md(skill, version)
    skill_name = skill.slug
    support_files = resolve_files(skill.id, version.version_number)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{skill_name}/SKILL.md", skill_md)
        for path, f in support_files.items():
            zf.writestr(f"{skill_name}/{path}", file_bytes(f))

        metadata = _normalize_metadata(version.koinoflow_metadata)
        if not _is_metadata_empty(metadata):
            import json as _json

            zf.writestr(
                f"{skill_name}/{_KOINOFLOW_METADATA_SIDECAR}",
                _json.dumps(metadata, indent=2),
            )
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{skill_name}.skill"'
    return response


class GenerateSkillIn(Schema):
    source_text: str = Field(min_length=10, max_length=50_000)


class GenerateSkillOut(Schema):
    frontmatter_yaml: str
    content_md: str


@router.post(
    "/skills/generate",
    response={200: GenerateSkillOut},
    auth=api_or_session,
    throttle=[ImportThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def generate_skill(request, payload: GenerateSkillIn):
    """
    Transform unstructured documentation or informal workflow text into a
    structured skill (frontmatter_yaml + content_md) ready to save as a version.
    """
    from apps.skills.generate import generate_skill_from_text

    try:
        frontmatter_yaml, content_md = generate_skill_from_text(payload.source_text)
    except ValueError as exc:
        raise HttpError(422, str(exc))
    except Exception as exc:
        logger.error("Process generation failed: %s", exc)
        raise HttpError(503, "Process generation temporarily unavailable")

    return {"frontmatter_yaml": frontmatter_yaml, "content_md": content_md}


class ImportSkillOut(Schema):
    skill: SkillDetailOut
    version_number: int


@router.post(
    "/skills/{slug}/import",
    response={201: ImportSkillOut},
    auth=api_or_session,
    throttle=[ImportThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def import_skill(request, slug: str, file: UploadedFile = File(...), system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    check_skill_write(request, skill)

    if file.size and file.size > MAX_SKILL_IMPORT_BYTES:
        raise HttpError(413, f"Archive is too large (max {_format_bytes(MAX_SKILL_IMPORT_BYTES)})")

    raw = file.read()
    if len(raw) > MAX_SKILL_IMPORT_BYTES:
        raise HttpError(413, f"Archive is too large (max {_format_bytes(MAX_SKILL_IMPORT_BYTES)})")

    skill_text = None
    support_file_entries: list[dict] = []
    imported_metadata: dict | None = None

    if file.name and (file.name.endswith(".skill") or file.name.endswith(".zip")):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    if name.endswith("SKILL.md"):
                        try:
                            skill_text = zf.read(name).decode("utf-8")
                        except UnicodeDecodeError:
                            raise HttpError(400, "SKILL.md is not valid UTF-8")
                    elif name.endswith(_KOINOFLOW_METADATA_SIDECAR):
                        try:
                            import json as _json

                            sidecar_text = zf.read(name).decode("utf-8")
                            sidecar_data = _json.loads(sidecar_text)
                            imported_metadata = _normalize_metadata(sidecar_data)
                        except (UnicodeDecodeError, ValueError):
                            imported_metadata = None
                    elif not name.endswith("/"):
                        # Extract support files: strip the leading skill-name prefix
                        parts = name.split("/", 1)
                        rel_path = parts[1] if len(parts) == 2 else name
                        if rel_path:
                            rel_path = _normalize_support_file_path(rel_path)
                            data = zf.read(name)
                            support_file_entries.append(_file_entry(path=rel_path, data=data))
        except zipfile.BadZipFile:
            raise HttpError(400, "Invalid zip archive")

        if not skill_text:
            raise HttpError(400, "No SKILL.md found in the archive")
    else:
        try:
            skill_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HttpError(400, "File is not valid UTF-8")

    fm_dict, content_md = _parse_skill_md(skill_text)

    fm_yaml = yaml.dump(fm_dict, default_flow_style=False, allow_unicode=True).strip()

    from django.db import transaction

    with transaction.atomic():
        latest = (
            SkillVersion.objects.select_for_update()
            .filter(skill=skill)
            .order_by("-version_number")
            .first()
        )
        max_num = latest.version_number if latest else 0
        version = SkillVersion.objects.create(
            skill=skill,
            version_number=max_num + 1,
            content_md=sanitize_content_md(content_md),
            frontmatter_yaml=sanitize_frontmatter(fm_yaml),
            change_summary="Imported from skill file",
            authored_by=request.user if request.user.is_authenticated else None,
            koinoflow_metadata=imported_metadata or _empty_metadata_dict(),
        )
        if support_file_entries:
            prev_num = max_num if max_num > 0 else None
            creates, tombstones = compute_file_delta(skill.id, prev_num, support_file_entries)
            file_rows = []
            for f in creates:
                file_rows.append(_version_file_from_entry(version, f))
            for t in tombstones:
                file_rows.append(
                    _version_file_from_entry(version, {"path": t["path"]}, is_deleted=True)
                )
            if file_rows:
                VersionFile.objects.bulk_create(file_rows)

    if fm_dict.get("name") and fm_dict["name"] != skill.title:
        skill.title = fm_dict["name"]
    if fm_dict.get("description"):
        skill.description = fm_dict["description"]
    skill.save(update_fields=["title", "description", "updated_at"])

    skill = Skill.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=skill.id)

    return Status(
        201,
        {
            "skill": _skill_detail_out(skill),
            "version_number": version.version_number,
        },
    )


# ── Skill-scoped agent deployment (works for any skill, not just agent-dept) ──


class SkillAgentDeploymentOut(Schema):
    skill_id: str
    deploy_to_all: bool
    agent_ids: list[str]


class UpdateSkillAgentDeploymentIn(Schema):
    deploy_to_all: bool = False
    agent_ids: list[str] = []


def _skill_agent_deployment_out(skill) -> dict:
    from apps.agents.models import AgentSkillDeployment

    deployments = list(AgentSkillDeployment.objects.filter(skill=skill).select_related("agent"))
    deploy_to_all = any(d.deploy_to_all for d in deployments)
    return {
        "skill_id": str(skill.id),
        "deploy_to_all": deploy_to_all,
        "agent_ids": [str(d.agent_id) for d in deployments if d.agent_id],
    }


@router.get(
    "/skills/{slug}/agent-deployment",
    response=SkillAgentDeploymentOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN)
def get_skill_agent_deployment(request, slug: str, system_kind: str | None = ""):
    skill = _get_skill(request, slug, system_kind=system_kind)
    return _skill_agent_deployment_out(skill)


@router.put(
    "/skills/{slug}/agent-deployment",
    response=SkillAgentDeploymentOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def update_skill_agent_deployment(
    request, slug: str, payload: UpdateSkillAgentDeploymentIn, system_kind: str | None = ""
):
    from django.db import transaction

    from apps.agents.models import Agent, AgentSkillDeployment

    skill = _get_skill(request, slug, system_kind=system_kind)

    if not payload.deploy_to_all and not payload.agent_ids:
        with transaction.atomic():
            skill.agent_deployments.all().delete()
        return _skill_agent_deployment_out(skill)

    agents = []
    if payload.agent_ids:
        agents = list(
            Agent.objects.filter(
                id__in=payload.agent_ids,
                workspace=request.workspace,
                is_active=True,
            )
        )
        if len(agents) != len(set(payload.agent_ids)):
            raise HttpError(400, "One or more agent IDs are invalid")

    with transaction.atomic():
        skill.agent_deployments.all().delete()
        if payload.deploy_to_all:
            AgentSkillDeployment.objects.create(skill=skill, deploy_to_all=True)
        elif agents:
            AgentSkillDeployment.objects.bulk_create(
                [AgentSkillDeployment(skill=skill, agent=agent) for agent in agents]
            )

    return _skill_agent_deployment_out(skill)
