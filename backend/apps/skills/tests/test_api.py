import base64
import io
import zipfile
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application

from apps.orgs.models import ApiKey, CoreSettings
from apps.orgs.tests.factories import DepartmentFactory, TeamFactory
from apps.skills.discovery import build_skill_indexed_text
from apps.skills.enums import StatusChoices, VisibilityChoices
from apps.skills.files import resolve_files
from apps.skills.models import Skill, SkillDiscoveryEmbedding, SkillVersion, VersionFile
from apps.skills.tests.factories import SkillFactory, SkillVersionFactory, VersionFileFactory


@pytest.mark.django_db
class TestCreateSkill:
    def test_create_skill_without_version(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy Process",
                "slug": "deploy-process",
                "description": "How to deploy",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Deploy Process"
        assert data["status"] == StatusChoices.DRAFT
        assert data["current_version"] is None

        skill = Skill.objects.get(slug="deploy-process")
        assert skill.versions.count() == 0

    def test_create_skill_duplicate_slug(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="existing")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Dupe",
                "slug": "existing",
            },
            content_type="application/json",
        )
        assert resp.status_code == 409


@pytest.mark.django_db
class TestGetProcess:
    def test_get_skill_published(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)
        version = SkillVersionFactory(skill=skill, version_number=1, content_md="# Deploy")
        skill.current_version = version
        skill.save()

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_version"]["content_md"] == "# Deploy"
        assert data["discovery_embedding_status"] == "pending"

        SkillDiscoveryEmbedding.objects.create(
            version=version,
            embedding=[0.0] * 768,
            embedding_model="gemini-embedding-2",
            embedding_dimensions=768,
            content_hash="a" * 64,
            indexed_text="# Deploy",
            indexed_at=timezone.now(),
        )

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.status_code == 200
        assert resp.json()["discovery_embedding_status"] == "ready"

    def test_get_skill_draft_via_session(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="draft-proc", status=StatusChoices.DRAFT)

        resp = auth_client.get("/api/v1/skills/draft-proc")
        assert resp.status_code == 200

    def test_get_skill_draft_via_api_key(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="draft-proc", status=StatusChoices.DRAFT)

        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
        )
        client = Client()
        resp = client.get(
            "/api/v1/skills/draft-proc",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestUpdateProcess:
    def test_update_process_title(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", title="Old Title")

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"title": "New Title"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"


@pytest.mark.django_db
class TestUpdateProcessScope:
    def test_admin_can_change_visibility_to_workspace(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", visibility=VisibilityChoices.DEPARTMENT)

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"visibility": "workspace"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "workspace"

    def test_team_manager_cannot_set_workspace_visibility(
        self, admin_membership, team_manager_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", visibility=VisibilityChoices.TEAM)

        client = Client()
        client.force_login(team_manager_membership.user)
        resp = client.patch(
            "/api/v1/skills/deploy",
            data={"visibility": "workspace"},
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_admin_can_change_workspace_to_team(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", visibility=VisibilityChoices.WORKSPACE)

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"visibility": "team"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "team"

    def test_update_shared_with_ids(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept1 = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        SkillFactory(department=dept1, slug="deploy", visibility=VisibilityChoices.DEPARTMENT)

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"shared_with_ids": [str(dept2.id)]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert str(dept2.id) in resp.json()["shared_with_ids"]

    def test_shared_with_invalid_dept_returns_400(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy")

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"shared_with_ids": ["00000000-0000-0000-0000-000000000000"]},
            content_type="application/json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestUnshareFromMyTeam:
    def test_team_manager_can_unshare_from_own_team(
        self, admin_membership, team_manager_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        owner_dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=owner_dept, slug="shared-proc")

        mgr_team = team_manager_membership.team
        mgr_dept = DepartmentFactory(team=mgr_team)
        skill.shared_with.add(mgr_dept)

        client = Client()
        client.force_login(team_manager_membership.user)
        resp = client.delete("/api/v1/skills/shared-proc/shared-with/my-team")

        assert resp.status_code == 200
        assert str(mgr_dept.id) not in resp.json()["shared_with_ids"]
        assert resp.json()["is_shared_with_requester_team"] is False

    def test_unshare_does_not_affect_other_teams(self, admin_membership, team_manager_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        owner_dept = DepartmentFactory(team=team)
        other_team = TeamFactory(workspace=ws)
        other_dept = DepartmentFactory(team=other_team)
        skill = SkillFactory(department=owner_dept, slug="shared-proc")

        mgr_dept = DepartmentFactory(team=team_manager_membership.team)
        skill.shared_with.add(mgr_dept, other_dept)

        client = Client()
        client.force_login(team_manager_membership.user)
        resp = client.delete("/api/v1/skills/shared-proc/shared-with/my-team")

        assert resp.status_code == 200
        data = resp.json()
        assert str(mgr_dept.id) not in data["shared_with_ids"]
        assert str(other_dept.id) in data["shared_with_ids"]

    def test_returns_400_when_not_shared(self, admin_membership, team_manager_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        SkillFactory(department=dept, slug="not-shared")

        client = Client()
        client.force_login(team_manager_membership.user)
        resp = client.delete("/api/v1/skills/not-shared/shared-with/my-team")

        assert resp.status_code == 400

    def test_admin_cannot_use_endpoint(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, slug="proc")
        other_dept = DepartmentFactory(team=TeamFactory(workspace=ws))
        skill.shared_with.add(other_dept)

        resp = auth_client.delete("/api/v1/skills/proc/shared-with/my-team")
        assert resp.status_code == 403

    def test_get_skill_reflects_is_shared_with_requester_team(
        self, admin_membership, team_manager_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, slug="shared-proc")

        mgr_dept = DepartmentFactory(team=team_manager_membership.team)
        skill.shared_with.add(mgr_dept)

        client = Client()
        client.force_login(team_manager_membership.user)
        resp = client.get("/api/v1/skills/shared-proc")

        assert resp.status_code == 200
        assert resp.json()["is_shared_with_requester_team"] is True


@pytest.mark.django_db
class TestDeleteSkill:
    def test_delete_skill(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy")

        resp = auth_client.delete("/api/v1/skills/deploy")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert not Skill.objects.filter(slug="deploy").exists()


@pytest.mark.django_db
class TestCreateVersion:
    def test_create_version_increments_number(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1)

        resp = auth_client.post(
            "/api/v1/skills/deploy/versions",
            data={
                "content_md": "# Deploy v2",
                "change_summary": "Updated steps",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version_number"] == 2

    def test_create_version_rejects_identical_content(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(
            skill=skill,
            version_number=1,
            content_md="# Deploy",
            frontmatter_yaml="name: deploy",
        )

        resp = auth_client.post(
            "/api/v1/skills/deploy/versions",
            data={
                "content_md": "# Deploy",
                "frontmatter_yaml": "name: deploy",
                "change_summary": "No real changes",
            },
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert "No changes detected" in resp.json()["detail"]


@pytest.mark.django_db
class TestListVersions:
    def test_list_versions(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1)
        SkillVersionFactory(skill=skill, version_number=2)

        resp = auth_client.get("/api/v1/skills/deploy/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["version_number"] == 2


@pytest.mark.django_db
class TestGetVersion:
    def test_get_specific_version(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V2")

        resp = auth_client.get("/api/v1/skills/deploy/versions/1")
        assert resp.status_code == 200
        assert resp.json()["content_md"] == "# V1"


@pytest.mark.django_db
class TestVersionDiff:
    def test_diff_returns_hunks(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Deploy\n\nStep 1: Build")
        SkillVersionFactory(
            skill=skill, version_number=2, content_md="# Deploy\n\nStep 1: Build\nStep 2: Ship"
        )

        resp = auth_client.get("/api/v1/skills/deploy/versions/2/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_version"]["version_number"] == 1
        assert data["new_version"]["version_number"] == 2
        assert data["stats"]["additions"] >= 1
        assert len(data["hunks"]) >= 1

    def test_diff_v1_returns_400(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Deploy")

        resp = auth_client.get("/api/v1/skills/deploy/versions/1/diff")
        assert resp.status_code == 400

    def test_diff_nonexistent_version_returns_404(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy")

        resp = auth_client.get("/api/v1/skills/deploy/versions/99/diff")
        assert resp.status_code == 404

    def test_diff_no_changes_returns_empty_hunks(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Deploy\n\nSame content")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# Deploy\n\nSame content")

        resp = auth_client.get("/api/v1/skills/deploy/versions/2/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hunks"] == []
        assert data["stats"]["additions"] == 0
        assert data["stats"]["deletions"] == 0


@pytest.mark.django_db
class TestPublishProcess:
    def test_publish_updates_current_version(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1)
        v2 = SkillVersionFactory(skill=skill, version_number=2)

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == StatusChoices.PUBLISHED
        assert data["current_version"]["version_number"] == 2
        assert data["last_reviewed_at"] is not None

        skill.refresh_from_db()
        assert skill.current_version_id == v2.id


@pytest.mark.django_db
class TestListSkills:
    def test_list_skills_basic(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="p1", title="First")
        SkillFactory(department=dept, slug="p2", title="Second")

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    def test_list_skills_search(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", title="Deploy Process")
        SkillFactory(department=dept, slug="onboard", title="Onboarding Guide")

        resp = auth_client.get("/api/v1/skills?search=deploy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "Deploy Process"

    def test_list_processes_api_key_hides_drafts(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="draft", status=StatusChoices.DRAFT)
        SkillFactory(department=dept, slug="published", status=StatusChoices.PUBLISHED)

        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
        )
        client = Client()
        resp = client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["items"][0]["slug"] == "published"

    def test_list_processes_embedding_statuses(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        draft = SkillFactory(department=dept, slug="draft", status=StatusChoices.DRAFT)
        published = SkillFactory(
            department=dept,
            slug="published",
            status=StatusChoices.PUBLISHED,
        )
        ready = SkillFactory(department=dept, slug="ready", status=StatusChoices.PUBLISHED)
        published_version = SkillVersionFactory(skill=published, version_number=1)
        ready_version = SkillVersionFactory(skill=ready, version_number=1)
        published.current_version = published_version
        published.save(update_fields=["current_version"])
        ready.current_version = ready_version
        ready.save(update_fields=["current_version"])
        SkillDiscoveryEmbedding.objects.create(
            version=ready_version,
            embedding=[0.0] * 768,
            embedding_model="gemini-embedding-2",
            embedding_dimensions=768,
            content_hash="a" * 64,
            indexed_text="Ready",
            indexed_at=timezone.now(),
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        statuses = {
            item["slug"]: item["discovery_embedding_status"] for item in resp.json()["items"]
        }
        assert statuses[draft.slug] == "not_applicable"
        assert statuses[published.slug] == "pending"
        assert statuses[ready.slug] == "ready"


@pytest.mark.django_db
class TestDiscoverProcesses:
    def _published_skill(self, dept, *, slug, title, content, metadata=None):
        skill = SkillFactory(
            department=dept,
            slug=slug,
            title=title,
            status=StatusChoices.PUBLISHED,
        )
        version = SkillVersionFactory(
            skill=skill,
            version_number=1,
            content_md=content,
            koinoflow_metadata=metadata or {},
        )
        skill.current_version = version
        skill.save(update_fields=["current_version"])
        return skill, version

    def test_indexed_text_uses_core_slugs(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="platform")
        dept = DepartmentFactory(team=team, slug="sre")
        _, version = self._published_skill(
            dept,
            slug="incident-response",
            title="Incident Response",
            content="# Incident\n\nTriage the outage.",
        )

        indexed_text = build_skill_indexed_text(version)

        assert "Team: " in indexed_text
        assert "(platform)" in indexed_text
        assert "Department: " in indexed_text
        assert "(sre)" in indexed_text

    def test_discover_processes_uses_metadata_when_embeddings_unavailable(
        self, auth_client, admin_membership, monkeypatch
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="platform")
        self._published_skill(
            dept,
            slug="deploy-prod",
            title="Deploy Production",
            content="# Deploy\n\nShip services safely.",
            metadata={"retrieval_keywords": ["ship", "release", "production"]},
        )
        self._published_skill(
            dept,
            slug="onboard",
            title="Onboard Employee",
            content="# Onboard\n\nCreate accounts.",
            metadata={"retrieval_keywords": ["hire", "account"]},
        )

        class FailingEmbeddingClient:
            def __init__(self, *args, **kwargs):
                pass

            def embed_query(self, query):
                raise RuntimeError("vertex unavailable")

        monkeypatch.setattr("apps.skills.api.VertexEmbeddingClient", FailingEmbeddingClient)

        resp = auth_client.get("/api/v1/skills/discover?query=ship%20production")
        assert resp.status_code == 200
        data = resp.json()
        assert data["embedding_status"] == "unavailable"
        assert data["items"][0]["slug"] == "deploy-prod"
        assert "retrieval keywords matched query terms" in data["items"][0]["match_reasons"]

    def test_discover_processes_ranks_semantic_matches(
        self, auth_client, admin_membership, monkeypatch
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="platform")
        deploy, deploy_version = self._published_skill(
            dept,
            slug="deploy-prod",
            title="Deploy Production",
            content="# Deploy\n\nRelease services.",
        )
        _, onboard_version = self._published_skill(
            dept,
            slug="onboard",
            title="Onboard Employee",
            content="# Onboard\n\nCreate accounts.",
        )
        vector_a = [1.0] + [0.0] * 767
        vector_b = [0.8, 0.6] + [0.0] * 766
        SkillDiscoveryEmbedding.objects.create(
            version=deploy_version,
            embedding=vector_a,
            embedding_model="gemini-embedding-2",
            embedding_dimensions=768,
            content_hash="a" * 64,
            indexed_text="deploy production",
            indexed_at=timezone.now(),
        )
        SkillDiscoveryEmbedding.objects.create(
            version=onboard_version,
            embedding=vector_b,
            embedding_model="gemini-embedding-2",
            embedding_dimensions=768,
            content_hash="b" * 64,
            indexed_text="onboarding",
            indexed_at=timezone.now(),
        )

        class StaticEmbeddingClient:
            def __init__(self, *args, **kwargs):
                pass

            def embed_query(self, query):
                return vector_a

        monkeypatch.setattr("apps.skills.api.VertexEmbeddingClient", StaticEmbeddingClient)

        resp = auth_client.get("/api/v1/skills/discover?query=release")
        assert resp.status_code == 200
        data = resp.json()
        assert data["embedding_status"] == "ready"
        assert data["items"][0]["slug"] == deploy.slug
        assert data["items"][0]["indexed"] is True
        assert data["items"][0]["vector_score"] > data["items"][1]["vector_score"]

    def test_discover_processes_api_key_hides_drafts(self, admin_membership, monkeypatch):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="platform")
        draft = SkillFactory(department=dept, slug="draft", status=StatusChoices.DRAFT)
        draft_version = SkillVersionFactory(
            skill=draft,
            version_number=1,
            content_md="# Draft secret deploy process",
        )
        draft.current_version = draft_version
        draft.save(update_fields=["current_version"])
        self._published_skill(
            dept,
            slug="published",
            title="Published Deploy",
            content="# Published deploy process",
        )

        class FailingEmbeddingClient:
            def __init__(self, *args, **kwargs):
                pass

            def embed_query(self, query):
                raise RuntimeError("vertex unavailable")

        monkeypatch.setattr("apps.skills.api.VertexEmbeddingClient", FailingEmbeddingClient)
        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
        )
        client = Client()
        resp = client.get(
            "/api/v1/skills/discover?query=deploy",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        slugs = [item["slug"] for item in resp.json()["items"]]
        assert slugs == ["published"]


@pytest.mark.django_db
class TestCreateProcessSlugUniqueness:
    def test_workspace_wide_slug_uniqueness(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept1 = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        SkillFactory(department=dept1, slug="deploy")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept2.id),
                "title": "Deploy Again",
                "slug": "deploy",
            },
            content_type="application/json",
        )
        assert resp.status_code == 409


@pytest.mark.django_db
class TestProcessVisibility:
    def test_create_skill_with_default_visibility(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["visibility"] == VisibilityChoices.DEPARTMENT

    def test_create_skill_with_team_visibility(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
                "visibility": "team",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["visibility"] == VisibilityChoices.TEAM

    def test_create_skill_with_workspace_visibility(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
                "visibility": "workspace",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["visibility"] == VisibilityChoices.WORKSPACE

    def test_create_skill_with_invalid_visibility(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
                "visibility": "invalid",
            },
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_visibility_in_list_response(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="p1", visibility=VisibilityChoices.TEAM)

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["visibility"] == "team"

    def test_visibility_in_detail_response(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", visibility=VisibilityChoices.WORKSPACE)

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "workspace"

    def test_update_visibility(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", visibility=VisibilityChoices.DEPARTMENT)

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"visibility": "workspace"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "workspace"

    def test_workspace_wide_survives_team_filter(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team_a = TeamFactory(workspace=ws, slug="eng")
        team_b = TeamFactory(workspace=ws, slug="ops")
        dept_a = DepartmentFactory(team=team_a, slug="backend")
        dept_b = DepartmentFactory(team=team_b, slug="finance")

        SkillFactory(department=dept_a, slug="ws-skill", visibility=VisibilityChoices.WORKSPACE)
        SkillFactory(department=dept_b, slug="local-skill", visibility=VisibilityChoices.DEPARTMENT)

        resp = auth_client.get("/api/v1/skills?department=finance&team=ops")
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "ws-skill" in slugs
        assert "local-skill" in slugs

    def test_api_key_member_sees_workspace_visible_processes(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept1 = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")

        SkillFactory(
            department=dept2,
            slug="ws-visible",
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.WORKSPACE,
        )
        SkillFactory(
            department=dept2,
            slug="dept-only",
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.DEPARTMENT,
        )

        raw_key, key_hash, key_prefix = ApiKey.generate()
        key = ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
            role="member",
            team=team,
        )
        key.departments.add(dept1)

        client = Client()
        resp = client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "ws-visible" in slugs
        assert "dept-only" not in slugs

    def test_api_key_member_sees_team_visible_processes(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept1 = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")

        SkillFactory(
            department=dept2,
            slug="team-visible",
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.TEAM,
        )

        raw_key, key_hash, key_prefix = ApiKey.generate()
        key = ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
            role="member",
            team=team,
        )
        key.departments.add(dept1)

        client = Client()
        resp = client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "team-visible" in slugs


@pytest.mark.django_db
class TestSharedWith:
    def test_create_skill_with_shared_with(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
                "shared_with_ids": [str(dept2.id)],
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert str(dept2.id) in data["shared_with_ids"]

    def test_shared_with_ids_in_list_response(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        skill = SkillFactory(department=dept, slug="deploy")
        skill.shared_with.add(dept2)

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert str(dept2.id) in item["shared_with_ids"]

    def test_shared_with_ids_in_detail_response(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        skill = SkillFactory(department=dept, slug="deploy")
        skill.shared_with.add(dept2)

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.status_code == 200
        assert str(dept2.id) in resp.json()["shared_with_ids"]

    def test_update_shared_with(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        SkillFactory(department=dept, slug="deploy")

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"shared_with_ids": [str(dept2.id)]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert str(dept2.id) in resp.json()["shared_with_ids"]

    def test_update_shared_with_clear(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        dept2 = DepartmentFactory(team=team, slug="backend")
        skill = SkillFactory(department=dept, slug="deploy")
        skill.shared_with.add(dept2)

        resp = auth_client.patch(
            "/api/v1/skills/deploy",
            data={"shared_with_ids": []},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["shared_with_ids"] == []

    def test_shared_with_invalid_dept_id(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/skills",
            data={
                "department_id": str(dept.id),
                "title": "Deploy",
                "slug": "deploy",
                "shared_with_ids": ["00000000-0000-0000-0000-000000000000"],
            },
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_api_key_member_sees_shared_process(self, admin_membership):
        ws = admin_membership.workspace
        team1 = TeamFactory(workspace=ws, slug="eng")
        team2 = TeamFactory(workspace=ws, slug="ops")
        dept1 = DepartmentFactory(team=team1, slug="frontend")
        dept2 = DepartmentFactory(team=team2, slug="devops")

        skill = SkillFactory(
            department=dept1,
            slug="shared-proc",
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.DEPARTMENT,
        )
        skill.shared_with.add(dept2)

        raw_key, key_hash, key_prefix = ApiKey.generate()
        key = ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
            role="member",
            team=team2,
        )
        key.departments.add(dept2)

        client = Client()
        resp = client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "shared-proc" in slugs

    def test_api_key_member_cannot_see_unshared_process(self, admin_membership):
        ws = admin_membership.workspace
        team1 = TeamFactory(workspace=ws, slug="eng")
        team2 = TeamFactory(workspace=ws, slug="ops")
        dept1 = DepartmentFactory(team=team1, slug="frontend")
        dept2 = DepartmentFactory(team=team2, slug="devops")

        SkillFactory(
            department=dept1,
            slug="private-proc",
            status=StatusChoices.PUBLISHED,
            visibility=VisibilityChoices.DEPARTMENT,
        )

        raw_key, key_hash, key_prefix = ApiKey.generate()
        key = ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="test",
            role="member",
            team=team2,
        )
        key.departments.add(dept2)

        client = Client()
        resp = client.get(
            "/api/v1/skills",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "private-proc" not in slugs


@pytest.mark.django_db
class TestReviewProcess:
    def test_mark_as_reviewed(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        resp = auth_client.post("/api/v1/skills/deploy/review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_reviewed_at"] is not None

        skill.refresh_from_db()
        assert skill.last_reviewed_at is not None

    def test_review_resets_needs_audit(self, auth_client, admin_membership):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now() - timedelta(days=60),
        )

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.json()["needs_audit"] is True

        auth_client.post("/api/v1/skills/deploy/review")

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.json()["needs_audit"] is False

    def test_mark_as_reviewed_unassigned_member_forbidden(self, member_membership):
        ws = member_membership.workspace
        # Create a department the member is NOT assigned to
        from apps.orgs.tests.factories import DepartmentFactory, TeamFactory

        team = TeamFactory(workspace=ws, slug="other-team")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        client = Client()
        client.force_login(member_membership.user)
        resp = client.post("/api/v1/skills/deploy/review")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestNeedsAudit:
    def test_needs_audit_false_when_no_audit_rule(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is False

    def test_needs_audit_true_when_overdue(self, auth_client, admin_membership):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now() - timedelta(days=60),
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is True

    def test_needs_audit_false_when_recently_reviewed(
        self,
        auth_client,
        admin_membership,
    ):
        from django.utils import timezone

        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now(),
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is False

    def test_needs_audit_true_when_never_reviewed(
        self,
        auth_client,
        admin_membership,
    ):
        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=None,
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is True

    def test_needs_audit_false_for_draft_process(
        self,
        auth_client,
        admin_membership,
    ):
        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.DRAFT,
            last_reviewed_at=None,
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is False

    def test_needs_audit_on_detail_endpoint(self, auth_client, admin_membership):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now() - timedelta(days=60),
        )

        resp = auth_client.get("/api/v1/skills/deploy")
        assert resp.status_code == 200
        assert resp.json()["needs_audit"] is True

    def test_needs_audit_inherits_from_team(self, auth_client, admin_membership):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orgs.models import CoreSettings
        from apps.orgs.tests.factories import SkillAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        rule = SkillAuditRuleFactory(workspace=ws, period_days=30)
        CoreSettings.objects.create(
            workspace=ws,
            team=team,
            skill_audit=rule,
        )

        SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now() - timedelta(days=60),
        )

        resp = auth_client.get("/api/v1/skills")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["needs_audit"] is True


@pytest.mark.django_db
class TestUpdateVersionSummary:
    def test_update_change_summary(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, change_summary="Old summary")

        resp = auth_client.patch(
            "/api/v1/skills/deploy/versions/1",
            data={"change_summary": "New summary"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["change_summary"] == "New summary"
        assert data["version_number"] == 1

    def test_update_nonexistent_version_returns_404(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        SkillFactory(department=dept, slug="deploy")

        resp = auth_client.patch(
            "/api/v1/skills/deploy/versions/99",
            data={"change_summary": "Updated"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_update_summary_persists(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        SkillVersionFactory(skill=skill, version_number=1, change_summary="Before")

        auth_client.patch(
            "/api/v1/skills/deploy/versions/1",
            data={"change_summary": "After"},
            content_type="application/json",
        )

        resp = auth_client.get("/api/v1/skills/deploy/versions")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["change_summary"] == "After"


@pytest.mark.django_db
class TestPublishRequireChangeSummary:
    def test_publish_v1_allowed_even_when_summary_required(self, auth_client, admin_membership):
        from apps.orgs.models import CoreSettings

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        CoreSettings.objects.create(
            workspace=ws,
            require_change_summary=True,
        )

        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1, change_summary="")

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == StatusChoices.PUBLISHED

    def test_publish_blocked_when_summary_required_and_empty(self, auth_client, admin_membership):
        from apps.orgs.models import CoreSettings

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        CoreSettings.objects.create(
            workspace=ws,
            require_change_summary=True,
        )

        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1)
        SkillVersionFactory(skill=skill, version_number=2, change_summary="")

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 400
        assert "change summary" in resp.json()["detail"].lower()

    def test_publish_allowed_when_summary_required_and_present(
        self,
        auth_client,
        admin_membership,
    ):
        from apps.orgs.models import CoreSettings

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        CoreSettings.objects.create(
            workspace=ws,
            require_change_summary=True,
        )

        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1)
        SkillVersionFactory(
            skill=skill,
            version_number=2,
            change_summary="Added deployment steps",
        )

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == StatusChoices.PUBLISHED

    def test_publish_allowed_when_summary_not_required(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1, change_summary="")

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == StatusChoices.PUBLISHED

    def test_publish_blocked_with_whitespace_only_summary(self, auth_client, admin_membership):
        from apps.orgs.models import CoreSettings

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        CoreSettings.objects.create(
            workspace=ws,
            require_change_summary=True,
        )

        skill = SkillFactory(department=dept, slug="deploy", status=StatusChoices.DRAFT)
        SkillVersionFactory(skill=skill, version_number=1)
        SkillVersionFactory(skill=skill, version_number=2, change_summary="   ")

        resp = auth_client.post("/api/v1/skills/deploy/publish")
        assert resp.status_code == 400


# ── File endpoint tests ─────────────────────────────────────────────────


def _make_dept_for_files(ws):
    team = TeamFactory(workspace=ws)
    return DepartmentFactory(team=team)


@pytest.mark.django_db
class TestCreateVersionWithFiles:
    def test_create_version_with_files(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-files")

        resp = auth_client.post(
            "/api/v1/skills/proc-files/versions",
            data={
                "content_md": "# Hello",
                "files": [
                    {"path": "scripts/run.py", "content": "print('hi')", "file_type": "python"},
                    {
                        "path": "references/schema.md",
                        "content": "# Schema",
                        "file_type": "markdown",
                    },
                ],
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["files"]) == 2
        paths = {f["path"] for f in data["files"]}
        assert paths == {"scripts/run.py", "references/schema.md"}
        assert VersionFile.objects.filter(version__skill__slug="proc-files").count() == 2

    def test_create_version_rejects_invalid_file_type(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-files-invalid-type")

        resp = auth_client.post(
            "/api/v1/skills/proc-files-invalid-type/versions",
            data={
                "content_md": "# Hello",
                "files": [
                    {"path": "scripts/run.py", "content": "print('hi')", "file_type": "rust"},
                ],
            },
            content_type="application/json",
        )

        assert resp.status_code == 422


@pytest.mark.django_db
class TestCreateVersionFileDelta:
    def test_file_delta_across_versions(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-delta")

        auth_client.post(
            "/api/v1/skills/proc-delta/versions",
            data={
                "content_md": "# v1",
                "files": [
                    {"path": "a.py", "content": "a content", "file_type": "python"},
                    {"path": "b.py", "content": "b content", "file_type": "python"},
                ],
            },
            content_type="application/json",
        )

        resp = auth_client.post(
            "/api/v1/skills/proc-delta/versions",
            data={
                "content_md": "# v2",
                "files": [
                    {"path": "a.py", "content": "a modified", "file_type": "python"},
                    {"path": "c.py", "content": "c content", "file_type": "python"},
                ],
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        resolved_paths = {f["path"] for f in data["files"]}
        assert resolved_paths == {"a.py", "c.py"}

        resp_v1 = auth_client.get("/api/v1/skills/proc-delta/versions/1")
        v1_paths = {f["path"] for f in resp_v1.json()["files"]}
        assert v1_paths == {"a.py", "b.py"}


@pytest.mark.django_db
class TestGetFileContent:
    def test_get_file_content(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-fc")
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        VersionFileFactory(
            version=v1, path="scripts/run.py", content="print('hello')", file_type="python"
        )

        resp = auth_client.get("/api/v1/skills/proc-fc/versions/1/files/scripts/run.py")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "print('hello')"
        assert data["file_type"] == "python"

    def test_get_missing_file_returns_404(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-fc2")
        SkillVersionFactory(skill=skill, version_number=1)

        resp = auth_client.get("/api/v1/skills/proc-fc2/versions/1/files/missing.py")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestFileDiff:
    def test_file_diff_shows_changes(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-fd")
        v1 = SkillVersionFactory(skill=skill, version_number=1, content_md="# v1")
        VersionFileFactory(version=v1, path="run.py", content="v1", file_type="python")
        VersionFileFactory(version=v1, path="utils.py", content="utils", file_type="python")

        v2 = SkillVersionFactory(skill=skill, version_number=2, content_md="# v2")
        VersionFileFactory(version=v2, path="run.py", content="v2 modified", file_type="python")
        VersionFileFactory(
            version=v2, path="utils.py", content="", is_deleted=True, file_type="python"
        )
        VersionFileFactory(version=v2, path="new.py", content="new", file_type="python")

        resp = auth_client.get("/api/v1/skills/proc-fd/versions/2/file-diff")
        assert resp.status_code == 200
        data = resp.json()
        entries_by_path = {e["path"]: e for e in data["entries"]}
        assert entries_by_path["run.py"]["status"] == "modified"
        assert entries_by_path["utils.py"]["status"] == "deleted"
        assert entries_by_path["new.py"]["status"] == "added"

    def test_file_diff_v1_returns_400(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-fd2")
        SkillVersionFactory(skill=skill, version_number=1)

        resp = auth_client.get("/api/v1/skills/proc-fd2/versions/1/file-diff")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestVersionDiffIncludesFileDiff:
    def test_diff_includes_file_diff(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-vfd")
        v1 = SkillVersionFactory(skill=skill, version_number=1, content_md="# v1")
        VersionFileFactory(version=v1, path="run.py", content="v1", file_type="python")
        v2 = SkillVersionFactory(skill=skill, version_number=2, content_md="# v2")
        # Tombstone run.py in v2 so it shows as deleted in the diff
        VersionFileFactory(
            version=v2, path="run.py", content="", is_deleted=True, file_type="python"
        )

        resp = auth_client.get("/api/v1/skills/proc-vfd/versions/2/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert "file_diff" in data
        assert isinstance(data["file_diff"], list)
        assert any(e["path"] == "run.py" and e["status"] == "deleted" for e in data["file_diff"])


@pytest.mark.django_db
class TestExportWithFiles:
    def test_export_includes_support_files(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-exp", status=StatusChoices.PUBLISHED)
        v1 = SkillVersionFactory(skill=skill, version_number=1, content_md="# Export")
        VersionFileFactory(version=v1, path="scripts/run.py", content="print()", file_type="python")
        skill.current_version = v1
        skill.save()

        resp = auth_client.get("/api/v1/skills/proc-exp/export")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert any("SKILL.md" in n for n in names)
        assert any("scripts/run.py" in n for n in names)


@pytest.mark.django_db
class TestImportWithFiles:
    def test_import_extracts_support_files(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-imp")

        skill_md = "---\nname: test-import\n---\n\n# Imported Process\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-imp/SKILL.md", skill_md)
            zf.writestr("proc-imp/scripts/foo.py", "def foo(): pass")
            zf.writestr("proc-imp/references/bar.md", "# Bar")
        buf.seek(0)

        uploaded = SimpleUploadedFile("proc-imp.skill", buf.read(), content_type="application/zip")
        resp = auth_client.post(
            "/api/v1/skills/proc-imp/import",
            data={"file": uploaded},
        )
        assert resp.status_code == 201
        data = resp.json()
        version_number = data["version_number"]

        files_resp = auth_client.get(f"/api/v1/skills/proc-imp/versions/{version_number}/files")
        assert files_resp.status_code == 200
        paths = {f["path"] for f in files_resp.json()}
        assert "scripts/foo.py" in paths
        assert "references/bar.md" in paths

    def test_import_export_preserves_binary_support_file(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(department=dept, slug="proc-binary", status=StatusChoices.PUBLISHED)

        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00binary-image"
        skill_md = "---\nname: binary-import\n---\n\n# Imported Process\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-binary/SKILL.md", skill_md)
            zf.writestr("proc-binary/images/template.png", png_bytes)
        buf.seek(0)

        uploaded = SimpleUploadedFile(
            "proc-binary.skill", buf.read(), content_type="application/zip"
        )
        resp = auth_client.post("/api/v1/skills/proc-binary/import", data={"file": uploaded})
        assert resp.status_code == 201
        version_number = resp.json()["version_number"]

        detail_resp = auth_client.get(
            f"/api/v1/skills/proc-binary/versions/{version_number}/files/images/template.png"
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["file_type"] == "image"
        assert detail["mime_type"] == "image/png"
        assert detail["content"] is None
        assert base64.b64decode(detail["content_base64"]) == png_bytes

        skill.current_version_id = SkillVersion.objects.get(
            skill=skill, version_number=version_number
        ).id
        skill.save(update_fields=["current_version"])

        export_resp = auth_client.get("/api/v1/skills/proc-binary/export")
        assert export_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(export_resp.content)) as zf:
            assert zf.read("proc-binary/images/template.png") == png_bytes

    def test_import_rejects_oversized_support_file(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-large")

        skill_md = "---\nname: large\n---\n\n# Body\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-large/SKILL.md", skill_md)
            zf.writestr("proc-large/assets/too-large.bin", b"x" * (1024 * 1024 + 1))
        buf.seek(0)

        uploaded = SimpleUploadedFile(
            "proc-large.skill", buf.read(), content_type="application/zip"
        )
        resp = auth_client.post("/api/v1/skills/proc-large/import", data={"file": uploaded})

        assert resp.status_code == 413
        assert "assets/too-large.bin" in resp.json()["detail"]
        assert "max per file" in resp.json()["detail"]

    def test_import_rejects_path_traversal_entries(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-imp-path")

        skill_md = "---\nname: test-import\n---\n\n# Imported Process\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-imp-path/SKILL.md", skill_md)
            zf.writestr("proc-imp-path/../secrets.txt", "oops")
        buf.seek(0)

        uploaded = SimpleUploadedFile(
            "proc-imp-path.skill",
            buf.read(),
            content_type="application/zip",
        )
        resp = auth_client.post(
            "/api/v1/skills/proc-imp-path/import",
            data={"file": uploaded},
        )

        assert resp.status_code == 400
        assert "invalid support file path" in resp.json()["detail"].lower()


# ── Koinoflow metadata tests ────────────────────────────────────────────


@pytest.mark.django_db
class TestKoinoflowMetadata:
    def test_create_version_persists_metadata(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta")

        resp = auth_client.post(
            "/api/v1/skills/proc-meta/versions",
            data={
                "content_md": "# Hello",
                "koinoflow_metadata": {
                    "retrieval_keywords": ["deploy", "ship"],
                    "risk_level": "high",
                    "requires_human_approval": True,
                    "prerequisites": ["setup-access"],
                    "audience": ["engineers", "on-call"],
                },
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        md = data["koinoflow_metadata"]
        assert md["retrieval_keywords"] == ["deploy", "ship"]
        assert md["risk_level"] == "high"
        assert md["requires_human_approval"] is True
        assert md["prerequisites"] == ["setup-access"]
        assert md["audience"] == ["engineers", "on-call"]

    def test_create_version_defaults_metadata_when_absent(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-default")

        resp = auth_client.post(
            "/api/v1/skills/proc-meta-default/versions",
            data={"content_md": "# Hello"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        md = resp.json()["koinoflow_metadata"]
        assert md == {
            "retrieval_keywords": [],
            "risk_level": None,
            "requires_human_approval": False,
            "prerequisites": [],
            "audience": [],
        }

    def test_metadata_change_alone_creates_new_version(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-bump")

        auth_client.post(
            "/api/v1/skills/proc-meta-bump/versions",
            data={"content_md": "# Same"},
            content_type="application/json",
        )
        resp = auth_client.post(
            "/api/v1/skills/proc-meta-bump/versions",
            data={
                "content_md": "# Same",
                "koinoflow_metadata": {"risk_level": "critical"},
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["version_number"] == 2
        assert resp.json()["koinoflow_metadata"]["risk_level"] == "critical"

    def test_metadata_never_in_exported_skill_md(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(
            department=dept, slug="proc-meta-export", status=StatusChoices.PUBLISHED
        )
        v1 = SkillVersionFactory(
            skill=skill,
            version_number=1,
            content_md="# Export me",
            frontmatter_yaml="name: proc-meta-export\nallowed-tools: Read Bash(git *)",
            koinoflow_metadata={
                "retrieval_keywords": ["secret"],
                "risk_level": "high",
                "requires_human_approval": True,
                "prerequisites": [],
                "audience": [],
            },
        )
        skill.current_version = v1
        skill.save()

        resp = auth_client.get("/api/v1/skills/proc-meta-export/export")
        assert resp.status_code == 200

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            skill_md_name = next(n for n in zf.namelist() if n.endswith("SKILL.md"))
            skill_md_text = zf.read(skill_md_name).decode("utf-8")

        assert "retrieval_keywords" not in skill_md_text
        assert "risk_level" not in skill_md_text
        assert "requires_human_approval" not in skill_md_text
        # Claude-compat frontmatter IS preserved
        assert "allowed-tools" in skill_md_text

    def test_export_includes_metadata_sidecar(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(
            department=dept, slug="proc-meta-sidecar", status=StatusChoices.PUBLISHED
        )
        v1 = SkillVersionFactory(
            skill=skill,
            version_number=1,
            content_md="# Sidecar",
            koinoflow_metadata={
                "retrieval_keywords": ["alpha"],
                "risk_level": "medium",
                "requires_human_approval": False,
                "prerequisites": ["bravo"],
                "audience": [],
            },
        )
        skill.current_version = v1
        skill.save()

        resp = auth_client.get("/api/v1/skills/proc-meta-sidecar/export")
        assert resp.status_code == 200

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            sidecar_name = next(
                (n for n in zf.namelist() if n.endswith("koinoflow-metadata.json")), None
            )
            assert sidecar_name is not None, "Expected koinoflow-metadata.json in export zip"
            import json as _json

            sidecar_data = _json.loads(zf.read(sidecar_name))
            assert sidecar_data["risk_level"] == "medium"
            assert sidecar_data["retrieval_keywords"] == ["alpha"]
            assert sidecar_data["prerequisites"] == ["bravo"]

    def test_export_empty_metadata_omits_sidecar(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        skill = SkillFactory(
            department=dept, slug="proc-meta-empty", status=StatusChoices.PUBLISHED
        )
        v1 = SkillVersionFactory(
            skill=skill,
            version_number=1,
            content_md="# No metadata",
        )
        skill.current_version = v1
        skill.save()

        resp = auth_client.get("/api/v1/skills/proc-meta-empty/export")
        assert resp.status_code == 200

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert not any("koinoflow-metadata.json" in n for n in names)

    def test_import_without_sidecar_leaves_metadata_empty(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-plain-import")

        skill_md = "---\nname: plain-import\nallowed-tools: Read\n---\n\n# Body\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-meta-plain-import/SKILL.md", skill_md)
        buf.seek(0)

        uploaded = SimpleUploadedFile("proc.skill", buf.read(), content_type="application/zip")
        resp = auth_client.post(
            "/api/v1/skills/proc-meta-plain-import/import",
            data={"file": uploaded},
        )
        assert resp.status_code == 201
        version_number = resp.json()["version_number"]

        v_resp = auth_client.get(f"/api/v1/skills/proc-meta-plain-import/versions/{version_number}")
        md = v_resp.json()["koinoflow_metadata"]
        assert md["retrieval_keywords"] == []
        assert md["risk_level"] is None
        # Claude-compat frontmatter is preserved in frontmatter_yaml
        assert "allowed-tools" in v_resp.json()["frontmatter_yaml"]

    def test_import_with_sidecar_hydrates_metadata(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-sidecar-import")

        skill_md = "---\nname: sidecar-import\n---\n\n# Body\n"
        import json as _json

        sidecar_payload = _json.dumps(
            {
                "retrieval_keywords": ["recovered"],
                "risk_level": "critical",
                "requires_human_approval": True,
                "prerequisites": ["pre"],
                "audience": ["sre"],
            }
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-meta-sidecar-import/SKILL.md", skill_md)
            zf.writestr("proc-meta-sidecar-import/koinoflow-metadata.json", sidecar_payload)
        buf.seek(0)

        uploaded = SimpleUploadedFile("proc.skill", buf.read(), content_type="application/zip")
        resp = auth_client.post(
            "/api/v1/skills/proc-meta-sidecar-import/import",
            data={"file": uploaded},
        )
        assert resp.status_code == 201
        version_number = resp.json()["version_number"]

        v_resp = auth_client.get(
            f"/api/v1/skills/proc-meta-sidecar-import/versions/{version_number}"
        )
        md = v_resp.json()["koinoflow_metadata"]
        assert md["retrieval_keywords"] == ["recovered"]
        assert md["risk_level"] == "critical"
        assert md["requires_human_approval"] is True
        assert md["prerequisites"] == ["pre"]
        assert md["audience"] == ["sre"]

    def test_import_sidecar_not_in_support_files(self, auth_client, admin_membership):
        from django.core.files.uploadedfile import SimpleUploadedFile

        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-sidecar-not-file")

        skill_md = "---\nname: x\n---\n\n# Body\n"
        import json as _json

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("proc-meta-sidecar-not-file/SKILL.md", skill_md)
            zf.writestr(
                "proc-meta-sidecar-not-file/koinoflow-metadata.json",
                _json.dumps({"risk_level": "low"}),
            )
        buf.seek(0)

        uploaded = SimpleUploadedFile("p.skill", buf.read(), content_type="application/zip")
        resp = auth_client.post(
            "/api/v1/skills/proc-meta-sidecar-not-file/import",
            data={"file": uploaded},
        )
        assert resp.status_code == 201
        version_number = resp.json()["version_number"]

        files_resp = auth_client.get(
            f"/api/v1/skills/proc-meta-sidecar-not-file/versions/{version_number}/files"
        )
        paths = {f["path"] for f in files_resp.json()}
        assert "koinoflow-metadata.json" not in paths

    def test_rejects_invalid_risk_level(self, auth_client, admin_membership):
        dept = _make_dept_for_files(admin_membership.workspace)
        SkillFactory(department=dept, slug="proc-meta-invalid")

        resp = auth_client.post(
            "/api/v1/skills/proc-meta-invalid/versions",
            data={
                "content_md": "# x",
                "koinoflow_metadata": {"risk_level": "nuclear"},
            },
            content_type="application/json",
        )
        assert resp.status_code == 422


# ── Revert version tests ─────────────────────────────────────────────────


def _setup_revert_skill(ws, slug="revert-proc"):
    team = TeamFactory(workspace=ws)
    dept = DepartmentFactory(team=team)
    return SkillFactory(department=dept, slug=slug)


@pytest.mark.django_db
class TestRevertVersion:
    def test_creates_new_version_with_target_content(self, auth_client, admin_membership):
        skill = _setup_revert_skill(admin_membership.workspace)
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V2")
        SkillVersionFactory(skill=skill, version_number=3, content_md="# V3")

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version_number"] == 4
        assert data["content_md"] == "# V1"
        assert data["reverted_from_version_number"] == 1
        assert data["change_summary"] == "Reverted to version 1"
        assert SkillVersion.objects.filter(skill=skill).count() == 4

    def test_custom_change_summary_is_preserved(self, auth_client, admin_membership):
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-summary")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V2")

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={"change_summary": "Rolling back broken deploy"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["change_summary"] == "Rolling back broken deploy"

    def test_file_tombstone_on_revert(self, auth_client, admin_membership):
        """Files added after target version must be tombstoned in the revert version."""
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-files")

        # v1: a.py + b.md
        auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions",
            data={
                "content_md": "# V1",
                "files": [
                    {"path": "a.py", "content": "print('a')", "file_type": "python"},
                    {"path": "b.md", "content": "# B", "file_type": "markdown"},
                ],
            },
            content_type="application/json",
        )
        # v2: adds c.sh
        auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions",
            data={
                "content_md": "# V2",
                "files": [
                    {"path": "a.py", "content": "print('a')", "file_type": "python"},
                    {"path": "b.md", "content": "# B", "file_type": "markdown"},
                    {"path": "c.sh", "content": "#!/bin/bash", "file_type": "shell"},
                ],
            },
            content_type="application/json",
        )

        # Revert to v1 → should create v3 where c.sh is tombstoned
        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["version_number"] == 3

        # After revert, the resolved file tree should not include c.sh
        resolved = resolve_files(skill.id, 3)
        assert "c.sh" not in resolved
        assert "a.py" in resolved
        assert "b.md" in resolved

    def test_file_restored_on_revert(self, auth_client, admin_membership):
        """Files deleted after target version must be restored in the revert version."""
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-restore")

        # v1: a.py + b.md
        auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions",
            data={
                "content_md": "# V1",
                "files": [
                    {"path": "a.py", "content": "print('a')", "file_type": "python"},
                    {"path": "b.md", "content": "# B", "file_type": "markdown"},
                ],
            },
            content_type="application/json",
        )
        # v2: removes b.md
        auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions",
            data={
                "content_md": "# V2",
                "files": [
                    {"path": "a.py", "content": "print('a')", "file_type": "python"},
                ],
            },
            content_type="application/json",
        )

        # Revert to v1 → b.md should come back
        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 201
        resolved = resolve_files(skill.id, 3)
        assert "b.md" in resolved
        assert resolved["b.md"].content == "# B"

    def test_identity_rejection(self, auth_client, admin_membership):
        """Revert to a version identical to the latest must return 409."""
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-identical")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V1")

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert "No changes detected" in resp.json()["detail"]

    def test_target_not_found_returns_404(self, auth_client, admin_membership):
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-404")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/99/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_reverting_to_latest_returns_409(self, auth_client, admin_membership):
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-latest")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V2")

        resp = auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/2/revert",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert "already the latest" in resp.json()["detail"]

    def test_reverted_from_version_number_in_list(self, auth_client, admin_membership):
        """reverted_from_version_number must appear in the versions list endpoint."""
        skill = _setup_revert_skill(admin_membership.workspace, slug="revert-list")
        SkillVersionFactory(skill=skill, version_number=1, content_md="# V1")
        SkillVersionFactory(skill=skill, version_number=2, content_md="# V2")

        auth_client.post(
            f"/api/v1/skills/{skill.slug}/versions/1/revert",
            data={},
            content_type="application/json",
        )

        resp = auth_client.get(f"/api/v1/skills/{skill.slug}/versions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        latest = items[0]
        assert latest["version_number"] == 3
        assert latest["reverted_from_version_number"] == 1

        non_revert = items[1]
        assert non_revert["reverted_from_version_number"] is None


def _make_oauth_token(user, scope="skills:read skills:write usage:write"):
    app = Application.objects.create(
        name="Test MCP Client",
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://localhost/callback",
    )
    return AccessToken.objects.create(
        user=user,
        application=app,
        token=f"mcp-tok-{AccessToken.objects.count()}",
        expires=timezone.now() + timedelta(hours=1),
        scope=scope,
    )


@pytest.mark.django_db
class TestCreateVersionAgentSetting:
    """Verify allow_agent_skill_updates gates OAuth-based version creation."""

    def _post_version(self, client, slug, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token.token}"
        return client.post(
            f"/api/v1/skills/{slug}/versions",
            data={
                "content_md": "# Updated",
                "frontmatter_yaml": "",
                "change_summary": "agent edit",
            },
            content_type="application/json",
            **headers,
        )

    def test_oauth_blocked_when_setting_not_set(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, status=StatusChoices.PUBLISHED)
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Original")

        token = _make_oauth_token(admin_membership.user)
        client = Client()
        resp = self._post_version(client, skill.slug, token)
        assert resp.status_code == 403

    def test_oauth_blocked_when_setting_false(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, status=StatusChoices.PUBLISHED)
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Original")
        CoreSettings.objects.create(
            workspace=ws, team=None, department=None, allow_agent_skill_updates=False
        )

        token = _make_oauth_token(admin_membership.user)
        client = Client()
        resp = self._post_version(client, skill.slug, token)
        assert resp.status_code == 403

    def test_oauth_allowed_when_setting_true(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, status=StatusChoices.PUBLISHED)
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Original")
        CoreSettings.objects.create(
            workspace=ws, team=None, department=None, allow_agent_skill_updates=True
        )

        token = _make_oauth_token(admin_membership.user)
        client = Client()
        resp = self._post_version(client, skill.slug, token)
        assert resp.status_code == 201

    def test_session_auth_not_affected_by_setting(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws)
        dept = DepartmentFactory(team=team)
        skill = SkillFactory(department=dept, status=StatusChoices.PUBLISHED)
        SkillVersionFactory(skill=skill, version_number=1, content_md="# Original")
        CoreSettings.objects.create(
            workspace=ws, team=None, department=None, allow_agent_skill_updates=False
        )

        resp = self._post_version(auth_client, skill.slug)
        assert resp.status_code == 201
