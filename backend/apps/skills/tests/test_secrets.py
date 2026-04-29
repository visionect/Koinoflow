import pytest
from cryptography.fernet import Fernet
from django.test import Client

from apps.orgs.tests.factories import DepartmentFactory, TeamFactory
from apps.skills.execution import issue_secret_fetch_token
from apps.skills.models import SkillExecutionRun, SkillExecutionSpec
from apps.skills.tests.factories import (
    SkillFactory,
    SkillSecretDeclarationFactory,
    SkillSecretValueFactory,
    SkillVersionFactory,
)


@pytest.mark.django_db
def test_admin_can_manage_skill_secret_values(auth_client, admin_membership, settings):
    settings.CONNECTOR_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    team = TeamFactory(workspace=admin_membership.workspace)
    department = DepartmentFactory(team=team)
    skill = SkillFactory(department=department, status="published")
    version = SkillVersionFactory(skill=skill)
    skill.current_version = version
    skill.save()
    spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
    SkillSecretDeclarationFactory(
        spec=spec,
        name="OPENAI_API_KEY",
        scope="workspace",
        required=True,
    )

    before = auth_client.get(f"/api/v1/skills/{skill.slug}/secrets")
    assert before.status_code == 200
    assert before.json()["items"][0]["is_set"] is False

    upsert = auth_client.put(
        f"/api/v1/skills/{skill.slug}/secrets/OPENAI_API_KEY",
        data={"value": "sk-test-123"},
        content_type="application/json",
    )
    assert upsert.status_code == 200
    assert upsert.json()["is_set"] is True

    after = auth_client.get(f"/api/v1/skills/{skill.slug}/secrets")
    assert after.status_code == 200
    assert after.json()["items"][0]["is_set"] is True

    delete_resp = auth_client.delete(f"/api/v1/skills/{skill.slug}/secrets/OPENAI_API_KEY")
    assert delete_resp.status_code == 200

    final = auth_client.get(f"/api/v1/skills/{skill.slug}/secrets")
    assert final.status_code == 200
    assert final.json()["items"][0]["is_set"] is False


@pytest.mark.django_db
def test_non_admin_cannot_manage_skill_secrets(team_manager_membership, admin_membership):
    team = TeamFactory(workspace=admin_membership.workspace)
    department = DepartmentFactory(team=team)
    skill = SkillFactory(department=department, status="published")
    version = SkillVersionFactory(skill=skill)
    skill.current_version = version
    skill.save()
    spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
    SkillSecretDeclarationFactory(
        spec=spec,
        name="OPENAI_API_KEY",
        scope="workspace",
        required=True,
    )

    client = Client()
    client.force_login(team_manager_membership.user)
    response = client.get(f"/api/v1/skills/{skill.slug}/secrets")
    assert response.status_code == 403


@pytest.mark.django_db
def test_executor_fetches_declared_secrets_once(admin_membership, settings):
    settings.CONNECTOR_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    team = TeamFactory(workspace=admin_membership.workspace)
    department = DepartmentFactory(team=team)
    skill = SkillFactory(department=department, status="published")
    version = SkillVersionFactory(skill=skill)
    skill.current_version = version
    skill.save()
    spec = SkillExecutionSpec.objects.create(skill=skill, version=version)
    SkillSecretDeclarationFactory(
        spec=spec,
        name="OPENAI_API_KEY",
        scope="workspace",
        required=True,
    )
    SkillSecretValueFactory(
        skill=skill,
        workspace=admin_membership.workspace,
        name="OPENAI_API_KEY",
        scope="workspace",
    )

    run = SkillExecutionRun.objects.create(
        workspace=admin_membership.workspace,
        skill=skill,
        version=version,
        spec=spec,
        department=department,
        caller_type=SkillExecutionRun.CallerTypeChoices.USER,
        status=SkillExecutionRun.StatusChoices.QUEUED,
        inputs={},
        input_hash="a" * 64,
    )
    token = issue_secret_fetch_token(run, ["OPENAI_API_KEY"])

    client = Client()
    response = client.post(
        f"/api/v1/skill-executions/{run.id}/secrets",
        data={},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    assert response.json()["values"]["OPENAI_API_KEY"] == "test-secret-value"

    run.refresh_from_db()
    assert run.secrets_fetched_at is not None

    second = client.post(
        f"/api/v1/skill-executions/{run.id}/secrets",
        data={},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert second.status_code == 409
