import json
import zipfile
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.skills.enums import StatusChoices
from apps.skills.execution import issue_callback_token
from apps.skills.execution_artifacts import prepare_execution_artifacts
from apps.skills.models import SkillExecutionRun, SkillExecutionSpec, VersionFile
from apps.skills.tests.factories import (
    SkillFactory,
    SkillVersionFactory,
    VersionFileFactory,
)


@pytest.mark.django_db
class TestExecutionArtifacts:
    def test_prepare_execution_artifacts_packages_version_files(
        self,
        admin_membership,
        settings,
        monkeypatch,
    ):
        settings.SKILL_EXECUTION_RUNS_BUCKET = "gs://test-runs"
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace, status=StatusChoices.PUBLISHED
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.save()
        VersionFileFactory(
            version=version,
            path="run.py",
            content="import json, sys\nprint(json.dumps({'ok': True}))",
            file_type="python",
        )
        VersionFileFactory(
            version=version,
            path="lib/helper.py",
            content="VALUE = 1",
            file_type="python",
        )
        spec = SkillExecutionSpec.objects.create(
            skill=skill, version=version, entrypoint_path="run.py"
        )
        run = SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            inputs={"name": "Ada"},
            input_hash="a" * 64,
        )

        uploads = {}

        def fake_upload(uri, data, content_type):
            uploads[uri] = (data, content_type)

        monkeypatch.setattr("apps.skills.execution_artifacts._upload_bytes", fake_upload)
        artifacts = prepare_execution_artifacts(run)

        assert artifacts.package_uri == f"gs://test-runs/runs/{run.id}/skill.zip"
        package_data, package_type = uploads[artifacts.package_uri]
        assert package_type == "application/zip"
        with zipfile.ZipFile(BytesIO(package_data)) as zf:
            assert sorted(zf.namelist()) == ["lib/helper.py", "run.py"]
        inputs_data, inputs_type = uploads[artifacts.inputs_uri]
        assert inputs_type == "application/json"
        assert json.loads(inputs_data.decode()) == {"name": "Ada"}
        manifest_data, manifest_type = uploads[artifacts.manifest_uri]
        assert manifest_type == "application/json"
        manifest = json.loads(manifest_data.decode())
        assert manifest["entrypoint_path"] == "run.py"
        assert manifest["secret_refs"] == []

    def test_prepare_execution_artifacts_rejects_missing_entrypoint(
        self, admin_membership, settings
    ):
        settings.SKILL_EXECUTION_RUNS_BUCKET = "gs://test-runs"
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace, status=StatusChoices.PUBLISHED
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.save()
        spec = SkillExecutionSpec.objects.create(
            skill=skill, version=version, entrypoint_path="run.py"
        )
        run = SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            inputs={},
            input_hash="a" * 64,
        )

        with pytest.raises(Exception, match="Execution entrypoint not found"):
            prepare_execution_artifacts(run)


@pytest.mark.django_db
class TestExecutionCallback:
    def test_callback_accepts_valid_token_and_terminal_status(
        self,
        auth_client,
        admin_membership,
        settings,
    ):
        settings.SKILL_EXECUTION_CALLBACK_SECRET = "test-secret"
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace, status=StatusChoices.PUBLISHED
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.save()
        spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
        run = SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            inputs={},
            input_hash="a" * 64,
        )
        token = issue_callback_token(run)

        resp = auth_client.post(
            f"/api/v1/skill-executions/{run.id}/callback",
            data={
                "status": "succeeded",
                "output": {"ok": True},
                "output_uri": "gs://bucket/out.json",
                "logs_uri": "gs://bucket/logs.txt",
                "resource_usage": {"exit_code": 0},
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.status == SkillExecutionRun.StatusChoices.SUCCEEDED
        assert run.output == {"ok": True}
        assert run.finished_at is not None

        second = auth_client.post(
            f"/api/v1/skill-executions/{run.id}/callback",
            data={"status": "failed", "error_message": "late"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert second.status_code == 409

    def test_callback_rejects_invalid_token(self, auth_client, admin_membership):
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace, status=StatusChoices.PUBLISHED
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.save()
        spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
        run = SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            inputs={},
            input_hash="a" * 64,
        )

        resp = auth_client.post(
            f"/api/v1/skill-executions/{run.id}/callback",
            data={"status": "succeeded", "output": {"ok": True}},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer nope",
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestExecutionConcurrency:
    def test_execute_rejects_when_concurrency_cap_reached(self, auth_client, admin_membership):
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace, status=StatusChoices.PUBLISHED
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.execution_enabled = True
        skill.save()
        VersionFile.objects.create(
            version=version,
            path="run.py",
            content="import json\nprint(json.dumps({'ok': True}))",
            file_type="python",
        )
        spec = SkillExecutionSpec.objects.create(
            skill=skill,
            version=version,
            max_concurrent_runs=1,
        )
        SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            inputs={},
            input_hash="a" * 64,
        )

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/execute",
            data={"inputs": {}},
            content_type="application/json",
        )
        assert resp.status_code == 429


@pytest.mark.django_db
class TestCleanupStuckSkillRuns:
    def _make_run(self, admin_membership, *, status, age_minutes, started=False):
        skill = SkillFactory(
            department__team__workspace=admin_membership.workspace,
            status=StatusChoices.PUBLISHED,
        )
        version = SkillVersionFactory(skill=skill, version_number=1)
        skill.current_version = version
        skill.save()
        spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
        run = SkillExecutionRun.objects.create(
            workspace=admin_membership.workspace,
            skill=skill,
            version=version,
            spec=spec,
            department=skill.department,
            caller_type=SkillExecutionRun.CallerTypeChoices.USER,
            status=status,
            inputs={},
            input_hash="a" * 64,
        )
        old = timezone.now() - timedelta(minutes=age_minutes)
        SkillExecutionRun.objects.filter(pk=run.pk).update(
            created_at=old,
            started_at=old if started else None,
        )
        run.refresh_from_db()
        return run

    def test_marks_old_queued_runs_as_failed(self, admin_membership):
        old_queued = self._make_run(
            admin_membership,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            age_minutes=60,
        )
        recent_queued = self._make_run(
            admin_membership,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            age_minutes=2,
        )

        call_command("cleanup_stuck_skill_runs")

        old_queued.refresh_from_db()
        recent_queued.refresh_from_db()
        assert old_queued.status == SkillExecutionRun.StatusChoices.FAILED
        assert "stuck" in old_queued.error_message.lower()
        assert old_queued.finished_at is not None
        assert recent_queued.status == SkillExecutionRun.StatusChoices.QUEUED

    def test_dry_run_does_not_modify(self, admin_membership):
        run = self._make_run(
            admin_membership,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            age_minutes=60,
        )

        call_command("cleanup_stuck_skill_runs", "--dry-run")

        run.refresh_from_db()
        assert run.status == SkillExecutionRun.StatusChoices.QUEUED

    def test_filters_by_skill_slug(self, admin_membership):
        target = self._make_run(
            admin_membership,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            age_minutes=60,
        )
        other = self._make_run(
            admin_membership,
            status=SkillExecutionRun.StatusChoices.QUEUED,
            age_minutes=60,
        )

        call_command("cleanup_stuck_skill_runs", f"--skill-slug={target.skill.slug}")

        target.refresh_from_db()
        other.refresh_from_db()
        assert target.status == SkillExecutionRun.StatusChoices.FAILED
        assert other.status == SkillExecutionRun.StatusChoices.QUEUED
