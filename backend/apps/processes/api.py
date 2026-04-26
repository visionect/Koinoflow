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
from django.http import HttpResponse
from django.utils import timezone
from ninja import Field, File, Router, Schema, Status, UploadedFile
from ninja.errors import HttpError
from pgvector.django import CosineDistance

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import (
    apply_api_key_scope,
    apply_oauth_connection_scope,
    check_process_write,
    require_role,
)
from apps.common.throttles import (
    CreateAuthThrottle,
    ImportThrottle,
    MutationThrottle,
    ReadThrottle,
)
from apps.orgs.api import UserBriefOut, _user_brief
from apps.orgs.enums import EntityType, RoleChoices
from apps.orgs.models import Membership, get_effective_settings
from apps.processes.discovery import (
    VertexEmbeddingClient,
    get_embedding_config,
    queue_process_discovery_embedding,
)
from apps.processes.discovery import (
    normalize_metadata as normalize_discovery_metadata,
)
from apps.processes.enums import StatusChoices, VisibilityChoices
from apps.processes.files import (
    compute_file_delta,
    detect_file_type,
    file_bytes,
    is_text_file,
    resolve_file_list,
    resolve_files,
)
from apps.processes.models import Process, ProcessVersion, VersionFile

logger = logging.getLogger(__name__)

router = Router(tags=["processes"])

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


class ProcessVersionOut(Schema):
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


class ProcessVersionBriefOut(Schema):
    id: str
    version_number: int
    change_summary: str
    authored_by: UserBriefOut | None
    created_at: str
    reverted_from_version_number: int | None


class ProcessOut(Schema):
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
    discovery_embedding_status: DiscoveryEmbeddingStatus
    created_at: str
    updated_at: str


class ProcessDetailOut(Schema):
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
    owner: UserBriefOut | None
    current_version: ProcessVersionOut | None
    last_reviewed_at: str | None
    needs_audit: bool
    discovery_embedding_status: DiscoveryEmbeddingStatus
    created_at: str
    updated_at: str


class ProcessListOut(Schema):
    items: list[ProcessOut]
    count: int


class ProcessDiscoveryResultOut(Schema):
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


class ProcessDiscoveryOut(Schema):
    items: list[ProcessDiscoveryResultOut]
    count: int
    embedding_status: str


class VersionListOut(Schema):
    items: list[ProcessVersionBriefOut]
    count: int


class CreateProcessIn(Schema):
    department_id: str
    title: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", min_length=2, max_length=100)
    description: str = ""
    owner_id: str | None = None
    visibility: str = VisibilityChoices.DEPARTMENT
    shared_with_ids: list[str] = []


class UpdateProcessIn(Schema):
    title: str | None = None
    description: str | None = None
    owner_id: str | None = None
    visibility: str | None = None
    shared_with_ids: list[str] | None = None


class VersionDiffOut(Schema):
    old_version: ProcessVersionBriefOut
    new_version: ProcessVersionBriefOut
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
        "files": resolve_file_list(v.process_id, v.version_number),
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


def _compute_needs_audit(process, audit_settings_cache=None):
    """
    Return True if the process is published and overdue for review
    based on its effective process_audit setting.

    audit_settings_cache: optional dict keyed by (workspace_id, team_id, dept_id)
    mapping to the resolved ProcessAuditRule or None.
    """
    if process.status != StatusChoices.PUBLISHED:
        return False

    dept = process.department
    workspace_id = dept.team.workspace_id
    team_id = dept.team_id
    dept_id = dept.id
    cache_key = (workspace_id, team_id, dept_id)

    if audit_settings_cache is not None and cache_key in audit_settings_cache:
        rule = audit_settings_cache[cache_key]
    else:
        effective = get_effective_settings(workspace_id, team_id=team_id, department_id=dept_id)
        rule = effective.get("process_audit")
        if audit_settings_cache is not None:
            audit_settings_cache[cache_key] = rule

    if rule is None:
        return False

    if process.last_reviewed_at is None:
        return True

    cutoff = timezone.now() - timedelta(days=rule.period_days)
    return process.last_reviewed_at < cutoff


def _discovery_embedding_status(process) -> DiscoveryEmbeddingStatus:
    if (
        process.status != StatusChoices.PUBLISHED
        or not process.current_version_id
        or not process.current_version
    ):
        return "not_applicable"

    try:
        process.current_version.discovery_embedding
    except ObjectDoesNotExist:
        return "pending"
    return "ready"


def _get_slug(entity_type, entity_id):
    from apps.orgs.models import CoreSlug

    try:
        return CoreSlug.objects.get(entity_type=entity_type, entity_id=entity_id).slug
    except CoreSlug.DoesNotExist:
        return ""


def _process_out(p, audit_cache=None, shared_cache=None):
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
        "needs_audit": _compute_needs_audit(p, audit_cache),
        "risk_level": cv_metadata["risk_level"],
        "retrieval_keywords": cv_metadata["retrieval_keywords"],
        "requires_human_approval": cv_metadata["requires_human_approval"],
        "discovery_embedding_status": _discovery_embedding_status(p),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _process_detail_out(p, requester_team_id=None):
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
        "owner": _user_brief(p.owner),
        "current_version": cv,
        "last_reviewed_at": p.last_reviewed_at.isoformat() if p.last_reviewed_at else None,
        "needs_audit": _compute_needs_audit(p),
        "discovery_embedding_status": _discovery_embedding_status(p),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _set_shared_with(process, dept_ids, workspace):
    """Validate and set the shared_with M2M for a process."""
    from apps.orgs.models import Department

    if not dept_ids:
        process.shared_with.clear()
        return

    depts = Department.objects.filter(
        id__in=dept_ids,
        team__workspace=workspace,
    )
    if depts.count() != len(dept_ids):
        raise HttpError(400, "One or more shared department IDs are invalid")

    process.shared_with.set(depts)


def _get_process(request, slug: str, *, allow_draft=True):
    """Fetch a process scoped to the request's workspace."""
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")
    try:
        process = Process.objects.select_related(
            "department__team",
            "owner",
            "current_version__authored_by",
            "current_version__discovery_embedding",
            "current_version__reverted_from",
        ).get(slug=slug, department__team__workspace=workspace)
    except Process.DoesNotExist:
        raise HttpError(404, "Process not found")

    is_api_key = hasattr(request, "api_key")
    if is_api_key and not allow_draft and process.status != StatusChoices.PUBLISHED:
        raise HttpError(404, "Process not found")

    return process


def _base_process_queryset(request):
    workspace = request.workspace
    if not workspace:
        raise HttpError(403, "No workspace context")

    qs = (
        Process.objects.filter(department__team__workspace=workspace)
        .select_related("department__team", "owner", "current_version__discovery_embedding")
        .order_by("-updated_at")
    )

    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    if is_api_key:
        qs = qs.filter(status=StatusChoices.PUBLISHED)
        qs = apply_api_key_scope(request.api_key, qs)
    elif is_oauth:
        qs = qs.filter(status=StatusChoices.PUBLISHED)
        qs = apply_oauth_connection_scope(request, qs)
    return qs


def _apply_process_filters(
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


def _process_snippet(process: Process, tokens: set[str]) -> str:
    if process.description:
        ratio = _token_hit_ratio(tokens, process.description)
        if ratio:
            return process.description[:280]
    content = process.current_version.content_md if process.current_version else ""
    for line in content.splitlines():
        cleaned = line.strip()
        if cleaned and _token_hit_ratio(tokens, cleaned):
            return cleaned[:280]
    return (process.description or content.strip())[:280]


def _lexical_discovery_score(process: Process, query: str) -> tuple[float, list[str], str]:
    tokens = _query_tokens(query)
    version = process.current_version
    metadata = normalize_discovery_metadata(version.koinoflow_metadata if version else {})

    title_score = _token_hit_ratio(tokens, process.title)
    slug_score = _token_hit_ratio(tokens, process.slug)
    description_score = _token_hit_ratio(tokens, process.description)
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
        reasons.append("process body matched query terms")

    return min(score, 1.0), reasons, _process_snippet(process, tokens)


# ── Process Endpoints ────────────────────────────────────────────────────


@router.get("/processes", response=ProcessListOut, auth=api_or_session, throttle=[ReadThrottle()])
def list_processes(
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
    qs = _apply_process_filters(
        _base_process_queryset(request),
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
    items = [_process_out(p, audit_cache, shared_cache) for p in page]
    return {"items": items, "count": count}


@router.get(
    "/processes/discover",
    response=ProcessDiscoveryOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def discover_processes(
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
    qs = _apply_process_filters(
        _base_process_queryset(request),
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
        logger.warning("Process discovery embedding unavailable: %s", exc)

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
        for process in vector_rows:
            distance = float(process.vector_distance)
            score = max(0.0, min(1.0, 1.0 - distance))
            vector_scores[process.id] = score
            candidates[process.id] = process

    lexical_pool = qs[:500]
    for process in lexical_pool:
        candidates[process.id] = process

    results = []
    for process in candidates.values():
        lexical_score, reasons, snippet = _lexical_discovery_score(process, query)
        vector_score = vector_scores.get(process.id)
        if vector_score is not None:
            combined_score = (0.70 * vector_score) + (0.30 * lexical_score)
            reasons = [f"semantic similarity {vector_score:.2f}", *reasons]
        else:
            combined_score = lexical_score

        if combined_score <= 0:
            continue

        version = process.current_version
        metadata = normalize_discovery_metadata(version.koinoflow_metadata if version else {})
        indexed = False
        if version is not None:
            try:
                indexed = bool(version.discovery_embedding)
            except ProcessVersion.discovery_embedding.RelatedObjectDoesNotExist:
                indexed = False
        results.append(
            {
                "id": str(process.id),
                "title": process.title,
                "slug": process.slug,
                "description": process.description,
                "department_slug": _get_slug(EntityType.DEPARTMENT, process.department_id),
                "department_name": process.department.name,
                "team_slug": _get_slug(EntityType.TEAM, process.department.team_id),
                "team_name": process.department.team.name,
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
    "/processes",
    response={201: ProcessDetailOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def create_process(request, payload: CreateProcessIn):
    workspace = request.workspace
    from apps.orgs.models import Department

    try:
        dept = Department.objects.select_related("team").get(
            id=payload.department_id, team__workspace=workspace
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
        slug_taken = Process.objects.filter(
            department__team__workspace=workspace, slug=payload.slug
        ).exists()
        if slug_taken:
            raise HttpError(409, "Process slug already taken in this workspace")

        try:
            process = Process.objects.create(
                department=dept,
                title=payload.title,
                slug=payload.slug,
                description=payload.description,
                owner=owner,
                status=StatusChoices.DRAFT,
                visibility=payload.visibility,
            )
        except IntegrityError:
            raise HttpError(409, "Process slug already taken in this workspace")

    if payload.shared_with_ids:
        _set_shared_with(process, payload.shared_with_ids, workspace)

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)
    return Status(201, _process_detail_out(process))


@router.get(
    "/processes/{slug}",
    response=ProcessDetailOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_process(request, slug: str):
    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    process = _get_process(request, slug, allow_draft=not (is_api_key or is_oauth))
    if is_api_key:
        allowed = apply_api_key_scope(request.api_key, Process.objects.filter(pk=process.pk))
        if not allowed.exists():
            raise HttpError(404, "Process not found")
    elif is_oauth:
        allowed = apply_oauth_connection_scope(request, Process.objects.filter(pk=process.pk))
        if not allowed.exists():
            raise HttpError(404, "Process not found")
    membership = getattr(request, "membership", None)
    team_id = membership.team_id if membership and membership.team_id else None
    return _process_detail_out(process, requester_team_id=team_id)


@router.patch(
    "/processes/{slug}",
    response=ProcessDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def update_process(request, slug: str, payload: UpdateProcessIn):
    process = _get_process(request, slug)
    check_process_write(request, process)
    workspace = request.workspace
    update_fields = ["updated_at"]

    if payload.title is not None:
        process.title = payload.title
        update_fields.append("title")
    if payload.description is not None:
        process.description = payload.description
        update_fields.append("description")
    if payload.owner_id is not None:
        if not Membership.objects.filter(workspace=workspace, user_id=payload.owner_id).exists():
            raise HttpError(400, "Owner is not a workspace member")
        from apps.accounts.models import User

        process.owner = User.objects.get(id=payload.owner_id)
        update_fields.append("owner")

    if payload.visibility is not None:
        if payload.visibility not in VisibilityChoices.values:
            raise HttpError(400, f"Invalid visibility: {payload.visibility}")
        if (
            payload.visibility == VisibilityChoices.WORKSPACE
            and process.visibility != VisibilityChoices.WORKSPACE
        ):
            membership = getattr(request, "membership", None)
            if membership is None or membership.role != RoleChoices.ADMIN:
                raise HttpError(403, "Only admins can set workspace-wide visibility")
        process.visibility = payload.visibility
        update_fields.append("visibility")

    process.save(update_fields=update_fields)

    if payload.shared_with_ids is not None:
        _set_shared_with(process, payload.shared_with_ids, workspace)

    if process.status == StatusChoices.PUBLISHED and process.current_version_id:
        queue_process_discovery_embedding(str(process.current_version_id))

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)
    membership = getattr(request, "membership", None)
    team_id = membership.team_id if membership and membership.team_id else None
    return _process_detail_out(process, requester_team_id=team_id)


@router.delete("/processes/{slug}", auth=api_or_session, throttle=[MutationThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def delete_process(request, slug: str):
    process = _get_process(request, slug)
    check_process_write(request, process)
    process.delete()
    return {"ok": True}


@router.delete(
    "/processes/{slug}/shared-with/my-team",
    response=ProcessDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.TEAM_MANAGER)
def unshare_from_my_team(request, slug: str):
    """Remove the requester's team from a process's shared_with list."""
    from apps.orgs.models import Department

    process = _get_process(request, slug)
    membership = getattr(request, "membership", None)
    if not membership or not membership.team_id:
        raise HttpError(400, "No team context")

    team_dept_ids = set(
        Department.objects.filter(team_id=membership.team_id).values_list("id", flat=True)
    )
    current_shared = set(process.shared_with.values_list("id", flat=True))
    overlap = team_dept_ids & current_shared
    if not overlap:
        raise HttpError(400, "Process is not shared with your team")

    new_shared = current_shared - overlap
    if new_shared:
        process.shared_with.set(Department.objects.filter(id__in=new_shared))
    else:
        process.shared_with.clear()

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)
    return _process_detail_out(process, requester_team_id=membership.team_id)


# ── Version Endpoints ────────────────────────────────────────────────────


@router.post(
    "/processes/{slug}/versions",
    response={201: ProcessVersionOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def create_version(request, slug: str, payload: CreateVersionIn):
    oauth_token = getattr(request, "oauth_token", None)
    if oauth_token is not None and "processes:write" not in oauth_token.scope.split():
        raise HttpError(403, "OAuth token missing required scope: processes:write")

    process = _get_process(request, slug)
    check_process_write(request, process)

    if oauth_token is not None:
        dept = process.department
        effective = get_effective_settings(
            dept.team.workspace_id,
            team_id=dept.team_id,
            department_id=dept.id,
        )
        if effective.get("allow_agent_process_updates") is not True:
            raise HttpError(403, "Agent process updates are not enabled for this workspace.")

    metadata_dict = _empty_metadata_dict()
    if payload.koinoflow_metadata is not None:
        metadata_dict = _normalize_metadata(payload.koinoflow_metadata.model_dump())

    from django.db import transaction

    with transaction.atomic():
        latest = (
            ProcessVersion.objects.select_for_update()
            .filter(process=process)
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
        version = ProcessVersion.objects.create(
            process=process,
            version_number=max_num + 1,
            content_md=payload.content_md,
            frontmatter_yaml=payload.frontmatter_yaml,
            change_summary=payload.change_summary,
            authored_by=request.user if request.user.is_authenticated else None,
            koinoflow_metadata=metadata_dict,
        )

        if payload.files is not None:
            submitted = [_file_entry_from_payload(f.model_dump()) for f in payload.files]
            creates, tombstones = compute_file_delta(
                process.id,
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
    "/processes/{slug}/versions",
    response=VersionListOut,
    auth=api_or_session,
)
def list_versions(request, slug: str, limit: int = 50, offset: int = 0):
    process = _get_process(request, slug)
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    qs = (
        ProcessVersion.objects.filter(process=process)
        .select_related("authored_by", "reverted_from")
        .order_by("-version_number")
    )
    count = qs.count()
    items = [_version_brief_out(v) for v in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.get(
    "/processes/{slug}/versions/{version_number}",
    response=ProcessVersionOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version(request, slug: str, version_number: int):
    process = _get_process(request, slug)
    try:
        version = ProcessVersion.objects.select_related("authored_by", "reverted_from").get(
            process=process, version_number=version_number
        )
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    return _version_out(version)


class UpdateVersionIn(Schema):
    change_summary: str


@router.patch(
    "/processes/{slug}/versions/{version_number}",
    response=ProcessVersionBriefOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def update_version(request, slug: str, version_number: int, payload: UpdateVersionIn):
    process = _get_process(request, slug)
    check_process_write(request, process)
    try:
        version = ProcessVersion.objects.select_related("authored_by").get(
            process=process, version_number=version_number
        )
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    version.change_summary = payload.change_summary
    version.save(update_fields=["change_summary", "updated_at"])
    return _version_brief_out(version)


@router.post(
    "/processes/{slug}/versions/{target_version_number}/revert",
    response={201: ProcessVersionOut},
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def revert_version(request, slug: str, target_version_number: int, payload: RevertVersionIn):
    from django.db import transaction

    process = _get_process(request, slug)
    check_process_write(request, process)

    try:
        target = ProcessVersion.objects.get(process=process, version_number=target_version_number)
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Target version not found")

    with transaction.atomic():
        latest = (
            ProcessVersion.objects.select_for_update()
            .filter(process=process)
            .order_by("-version_number")
            .first()
        )

        if target_version_number == latest.version_number:
            raise HttpError(409, "Target version is already the latest version")

        target_files = resolve_files(process.id, target_version_number)
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
            latest_files = resolve_files(process.id, latest.version_number)
            if set(target_files.keys()) == set(latest_files.keys()) and all(
                file_bytes(target_files[p]) == file_bytes(latest_files[p]) for p in target_files
            ):
                raise HttpError(409, "No changes detected since the last version")

        creates, tombstones = compute_file_delta(process.id, latest.version_number, submitted_files)

        summary = payload.change_summary.strip() or f"Reverted to version {target_version_number}"

        new_version = ProcessVersion.objects.create(
            process=process,
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
    "/processes/{slug}/versions/{version_number}/files",
    response=list[VersionFileOut],
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_version_files(request, slug: str, version_number: int):
    process = _get_process(request, slug)
    try:
        ProcessVersion.objects.get(process=process, version_number=version_number)
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    return resolve_file_list(process.id, version_number)


@router.get(
    "/processes/{slug}/versions/{version_number}/files/{path:path}",
    response=VersionFileDetailOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_file(request, slug: str, version_number: int, path: str):
    process = _get_process(request, slug)
    try:
        ProcessVersion.objects.get(process=process, version_number=version_number)
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")
    files = resolve_files(process.id, version_number)
    if path not in files:
        raise HttpError(404, "File not found")
    f = files[path]
    return _file_detail(f)


@router.get(
    "/processes/{slug}/versions/{version_number}/file-diff",
    response=FileDiffOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_file_diff(request, slug: str, version_number: int):
    process = _get_process(request, slug)
    try:
        ProcessVersion.objects.get(process=process, version_number=version_number)
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    if version_number <= 1:
        raise HttpError(400, "No previous version to diff against")

    try:
        ProcessVersion.objects.get(process=process, version_number=version_number - 1)
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Previous version not found")

    old_files = resolve_files(process.id, version_number - 1)
    new_files = resolve_files(process.id, version_number)

    return {
        "old_version_number": version_number - 1,
        "new_version_number": version_number,
        "entries": _compute_file_diff_entries(old_files, new_files),
    }


@router.get(
    "/processes/{slug}/versions/{version_number}/diff",
    response=VersionDiffOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_version_diff(request, slug: str, version_number: int):
    process = _get_process(request, slug)
    try:
        new_version = ProcessVersion.objects.select_related("authored_by").get(
            process=process, version_number=version_number
        )
    except ProcessVersion.DoesNotExist:
        raise HttpError(404, "Version not found")

    if version_number <= 1:
        raise HttpError(400, "No previous version to diff against")

    try:
        old_version = ProcessVersion.objects.select_related("authored_by").get(
            process=process, version_number=version_number - 1
        )
    except ProcessVersion.DoesNotExist:
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

    old_file_set = resolve_files(process.id, version_number - 1)
    new_file_set = resolve_files(process.id, version_number)

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
    "/processes/{slug}/publish",
    response=ProcessDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def publish_process(request, slug: str):
    process = _get_process(request, slug)
    check_process_write(request, process)
    latest = ProcessVersion.objects.filter(process=process).order_by("-version_number").first()
    if not latest:
        raise HttpError(400, "No versions to publish")

    dept = process.department
    effective = get_effective_settings(
        dept.team.workspace_id, team_id=dept.team_id, department_id=dept.id
    )
    if (
        effective.get("require_change_summary")
        and latest.version_number > 1
        and not latest.change_summary.strip()
    ):
        raise HttpError(400, "A change summary is required before publishing")

    process.current_version = latest
    process.status = StatusChoices.PUBLISHED
    process.last_reviewed_at = timezone.now()
    process.save(update_fields=["current_version", "status", "last_reviewed_at", "updated_at"])
    queue_process_discovery_embedding(str(latest.id), force=True)

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)
    return _process_detail_out(process)


# ── Review ────────────────────────────────────────────────────────────────


@router.post(
    "/processes/{slug}/review",
    response=ProcessDetailOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def review_process(request, slug: str):
    process = _get_process(request, slug)
    check_process_write(request, process)
    process.last_reviewed_at = timezone.now()
    process.save(update_fields=["last_reviewed_at", "updated_at"])

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)
    return _process_detail_out(process)


# ── Export / Import ─────────────────────────────────────────────────────


_KOINOFLOW_METADATA_SIDECAR = "koinoflow-metadata.json"


def _build_skill_md(process, version):
    """Build a SKILL.md string from a process version's frontmatter + content.

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
        fm_dict["name"] = process.slug
    if not fm_dict.get("description"):
        fm_dict["description"] = process.description

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


@router.get("/processes/{slug}/export", auth=api_or_session, throttle=[ReadThrottle()])
def export_process(request, slug: str):
    is_api_key = hasattr(request, "api_key")
    is_oauth = hasattr(request, "oauth_token")
    process = _get_process(request, slug, allow_draft=not (is_api_key or is_oauth))
    if is_api_key:
        allowed = apply_api_key_scope(request.api_key, Process.objects.filter(pk=process.pk))
        if not allowed.exists():
            raise HttpError(404, "Process not found")
    elif is_oauth:
        allowed = apply_oauth_connection_scope(request, Process.objects.filter(pk=process.pk))
        if not allowed.exists():
            raise HttpError(404, "Process not found")

    version = process.current_version
    if not version:
        latest = ProcessVersion.objects.filter(process=process).order_by("-version_number").first()
        if not latest:
            raise HttpError(400, "No versions to export")
        version = latest

    skill_md = _build_skill_md(process, version)
    skill_name = process.slug
    support_files = resolve_files(process.id, version.version_number)

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


class GenerateProcessIn(Schema):
    source_text: str = Field(min_length=10, max_length=50_000)


class GenerateProcessOut(Schema):
    frontmatter_yaml: str
    content_md: str


@router.post(
    "/processes/generate",
    response={200: GenerateProcessOut},
    auth=api_or_session,
    throttle=[ImportThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def generate_process(request, payload: GenerateProcessIn):
    """
    Transform unstructured documentation or informal workflow text into a
    structured process (frontmatter_yaml + content_md) ready to save as a version.
    """
    from apps.processes.generate import generate_process_from_text

    try:
        frontmatter_yaml, content_md = generate_process_from_text(payload.source_text)
    except ValueError as exc:
        raise HttpError(422, str(exc))
    except Exception as exc:
        logger.error("Process generation failed: %s", exc)
        raise HttpError(503, "Process generation temporarily unavailable")

    return {"frontmatter_yaml": frontmatter_yaml, "content_md": content_md}


class ImportSkillOut(Schema):
    process: ProcessDetailOut
    version_number: int


@router.post(
    "/processes/{slug}/import",
    response={201: ImportSkillOut},
    auth=api_or_session,
    throttle=[ImportThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def import_skill(request, slug: str, file: UploadedFile = File(...)):
    process = _get_process(request, slug)
    check_process_write(request, process)

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
            ProcessVersion.objects.select_for_update()
            .filter(process=process)
            .order_by("-version_number")
            .first()
        )
        max_num = latest.version_number if latest else 0
        version = ProcessVersion.objects.create(
            process=process,
            version_number=max_num + 1,
            content_md=content_md,
            frontmatter_yaml=fm_yaml,
            change_summary="Imported from skill file",
            authored_by=request.user if request.user.is_authenticated else None,
            koinoflow_metadata=imported_metadata or _empty_metadata_dict(),
        )
        if support_file_entries:
            prev_num = max_num if max_num > 0 else None
            creates, tombstones = compute_file_delta(process.id, prev_num, support_file_entries)
            file_rows = []
            for f in creates:
                file_rows.append(_version_file_from_entry(version, f))
            for t in tombstones:
                file_rows.append(
                    _version_file_from_entry(version, {"path": t["path"]}, is_deleted=True)
                )
            if file_rows:
                VersionFile.objects.bulk_create(file_rows)

    if fm_dict.get("name") and fm_dict["name"] != process.title:
        process.title = fm_dict["name"]
    if fm_dict.get("description"):
        process.description = fm_dict["description"]
    process.save(update_fields=["title", "description", "updated_at"])

    process = Process.objects.select_related(
        "department__team",
        "owner",
        "current_version__authored_by",
        "current_version__reverted_from",
    ).get(id=process.id)

    return Status(
        201,
        {
            "process": _process_detail_out(process),
            "version_number": version.version_number,
        },
    )
