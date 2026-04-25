import uuid

from apps.processes.models import VersionFile

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


def file_bytes(file: VersionFile) -> bytes:
    raw = getattr(file, "content_bytes", b"") or b""
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if raw:
        return bytes(raw)
    return (getattr(file, "content", "") or "").encode("utf-8")


def is_text_file(file: VersionFile) -> bool:
    return getattr(file, "encoding", "utf-8") == "utf-8" and file.file_type in TEXT_FILE_TYPES


def resolve_files(process_id: uuid.UUID, version_number: int) -> dict[str, VersionFile]:
    """Materialize the full file tree at a given version via DISTINCT ON."""
    rows = VersionFile.objects.raw(
        """
        SELECT DISTINCT ON (vf.path)
            vf.id, vf.path, vf.content, vf.content_bytes, vf.file_type,
            vf.mime_type, vf.encoding, vf.sha256,
            vf.size_bytes, vf.is_deleted, vf.version_id,
            vf.created_at, vf.updated_at
        FROM version_file vf
        JOIN process_version pv ON pv.id = vf.version_id
        WHERE pv.process_id = %s
          AND pv.version_number <= %s
        ORDER BY vf.path, pv.version_number DESC
        """,
        [str(process_id), version_number],
    )
    return {r.path: r for r in rows if not r.is_deleted}


def resolve_file_list(process_id: uuid.UUID, version_number: int) -> list[dict]:
    """Lightweight listing: returns path + file_type + size only (no content)."""
    files = resolve_files(process_id, version_number)
    return [
        {
            "id": str(f.id),
            "path": f.path,
            "file_type": f.file_type,
            "mime_type": f.mime_type,
            "encoding": f.encoding,
            "size_bytes": f.size_bytes,
        }
        for f in sorted(files.values(), key=lambda f: f.path)
    ]


def compute_file_delta(
    process_id: uuid.UUID,
    previous_version_number: int | None,
    submitted_files: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Compare submitted files against resolved state of previous version.

    Returns (files_to_create, tombstones_to_create).
    """
    old = resolve_files(process_id, previous_version_number) if previous_version_number else {}
    submitted_by_path = {f["path"]: f for f in submitted_files}

    creates = []
    for path, f in submitted_by_path.items():
        old_file = old.get(path)
        new_bytes = f.get("content_bytes")
        if new_bytes is None:
            new_bytes = (f.get("content") or "").encode("utf-8")
        if old_file is None or file_bytes(old_file) != new_bytes:
            creates.append(f)

    tombstones = []
    for path in old:
        if path not in submitted_by_path:
            tombstones.append({"path": path, "is_deleted": True})

    return creates, tombstones


def detect_file_type(filename: str) -> str:
    """Detect file_type from filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        "py": "python",
        "md": "markdown",
        "html": "html",
        "htm": "html",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "js": "javascript",
        "ts": "typescript",
        "sh": "shell",
        "png": "image",
        "jpg": "image",
        "jpeg": "image",
        "gif": "image",
        "webp": "image",
        "svg": "image",
        "pdf": "pdf",
    }
    return mapping.get(ext, "binary")
