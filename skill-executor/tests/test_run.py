import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.run import _safe_extract, _scrub_logs


def test_scrub_logs_redacts_secret_lines():
    logs = "hello\nAPI_KEY=secret\nall good"
    assert _scrub_logs(logs) == "hello\n[scrubbed potentially sensitive log line]\nall good"


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../bad.py", "print('bad')")

    with pytest.raises(RuntimeError, match="Unsafe path"):
        _safe_extract(archive, tmp_path / "out")
