import pytest

from apps.skills.files import compute_file_delta, resolve_file_list, resolve_files
from apps.skills.models import VersionFile
from apps.skills.tests.factories import SkillFactory, SkillVersionFactory


def _make_file(version, path, content, is_deleted=False):
    return VersionFile.objects.create(
        version=version,
        path=path,
        content=content,
        file_type="text",
        size_bytes=len(content.encode()),
        is_deleted=is_deleted,
    )


@pytest.mark.django_db
class TestResolveFiles:
    def test_resolve_files_single_version(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "print('hello')")
        _make_file(v1, "references/schema.md", "# Schema")
        _make_file(v1, "assets/icon.svg", "<svg/>")

        result = resolve_files(skill.id, 1)
        assert set(result.keys()) == {"scripts/run.py", "references/schema.md", "assets/icon.svg"}

    def test_resolve_files_inherited(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "v1 content")
        _make_file(v1, "references/schema.md", "v1 schema")
        _make_file(v1, "assets/icon.svg", "v1 icon")
        SkillVersionFactory(skill=skill, version_number=2)

        result = resolve_files(skill.id, 2)
        assert set(result.keys()) == {"scripts/run.py", "references/schema.md", "assets/icon.svg"}
        assert result["scripts/run.py"].content == "v1 content"

    def test_resolve_files_modified(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "v1 content")
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        _make_file(v2, "scripts/run.py", "v2 content")

        result = resolve_files(skill.id, 2)
        assert result["scripts/run.py"].content == "v2 content"

    def test_resolve_files_added(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "run content")
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        _make_file(v2, "scripts/utils.py", "utils content")

        result = resolve_files(skill.id, 2)
        assert set(result.keys()) == {"scripts/run.py", "scripts/utils.py"}

    def test_resolve_files_deleted(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "run content")
        _make_file(v1, "scripts/utils.py", "utils content")
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        _make_file(v2, "scripts/utils.py", "", is_deleted=True)

        result = resolve_files(skill.id, 2)
        assert set(result.keys()) == {"scripts/run.py"}

    def test_resolve_files_delete_then_readd(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "v1 content")
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        _make_file(v2, "scripts/run.py", "", is_deleted=True)
        v3 = SkillVersionFactory(skill=skill, version_number=3)
        _make_file(v3, "scripts/run.py", "v3 content")

        result_v3 = resolve_files(skill.id, 3)
        assert "scripts/run.py" in result_v3
        assert result_v3["scripts/run.py"].content == "v3 content"

        result_v2 = resolve_files(skill.id, 2)
        assert "scripts/run.py" not in result_v2

    def test_resolve_files_at_middle_version(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "v1 run")
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        _make_file(v2, "scripts/utils.py", "v2 utils")
        v3 = SkillVersionFactory(skill=skill, version_number=3)
        _make_file(v3, "scripts/run.py", "v3 run")

        result = resolve_files(skill.id, 2)
        assert set(result.keys()) == {"scripts/run.py", "scripts/utils.py"}
        assert result["scripts/run.py"].content == "v1 run"

    def test_resolve_file_list_excludes_content(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "some content")

        result = resolve_file_list(skill.id, 1)
        assert len(result) == 1
        assert "content" not in result[0]
        assert result[0]["path"] == "scripts/run.py"
        assert "file_type" in result[0]
        assert "size_bytes" in result[0]


@pytest.mark.django_db
class TestComputeFileDelta:
    def test_compute_delta_detects_new_modified_deleted(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "original")
        _make_file(v1, "scripts/utils.py", "utils")

        submitted = [
            {"path": "scripts/run.py", "content": "modified", "file_type": "python"},
            {"path": "scripts/new.py", "content": "new file", "file_type": "python"},
        ]

        creates, tombstones = compute_file_delta(skill.id, 1, submitted)
        create_paths = {f["path"] for f in creates}
        tombstone_paths = {f["path"] for f in tombstones}

        assert "scripts/run.py" in create_paths
        assert "scripts/new.py" in create_paths
        assert "scripts/utils.py" in tombstone_paths

    def test_compute_delta_no_changes(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        _make_file(v1, "scripts/run.py", "same content")

        submitted = [
            {"path": "scripts/run.py", "content": "same content", "file_type": "python"},
        ]

        creates, tombstones = compute_file_delta(skill.id, 1, submitted)
        assert creates == []
        assert tombstones == []

    def test_compute_delta_no_previous_version(self):
        skill = SkillFactory()

        submitted = [
            {"path": "scripts/run.py", "content": "new", "file_type": "python"},
        ]

        creates, tombstones = compute_file_delta(skill.id, None, submitted)
        assert len(creates) == 1
        assert tombstones == []
