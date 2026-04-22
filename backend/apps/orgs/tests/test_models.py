import pytest
from django.db import IntegrityError

from apps.accounts.tests.factories import UserFactory
from apps.orgs.enums import EntityType
from apps.orgs.models import ApiKey, CoreSlug
from apps.orgs.tests.factories import (
    DepartmentFactory,
    MembershipFactory,
    TeamFactory,
    WorkspaceFactory,
)


@pytest.mark.django_db
class TestWorkspace:
    def test_slug_unique(self):
        WorkspaceFactory(slug="acme")
        with pytest.raises(IntegrityError):
            CoreSlug.objects.create(
                entity_type=EntityType.WORKSPACE,
                entity_id="00000000-0000-0000-0000-000000000001",
                slug="acme",
            )

    def test_str(self):
        ws = WorkspaceFactory(name="Acme Corp")
        assert str(ws) == "Acme Corp"


@pytest.mark.django_db
class TestTeam:
    def test_slug_unique_within_workspace(self):
        ws = WorkspaceFactory()
        TeamFactory(workspace=ws, slug="engineering")
        with pytest.raises(IntegrityError):
            CoreSlug.objects.create(
                entity_type=EntityType.TEAM,
                entity_id="00000000-0000-0000-0000-000000000001",
                slug="engineering",
                scope_workspace=ws,
            )

    def test_slug_reusable_across_workspaces(self):
        t1 = TeamFactory(slug="engineering")
        t2 = TeamFactory(slug="engineering")
        assert t1.workspace != t2.workspace


@pytest.mark.django_db
class TestDepartment:
    def test_slug_unique_within_team(self):
        team = TeamFactory()
        DepartmentFactory(team=team, slug="backend")
        with pytest.raises(IntegrityError):
            CoreSlug.objects.create(
                entity_type=EntityType.DEPARTMENT,
                entity_id="00000000-0000-0000-0000-000000000001",
                slug="backend",
                scope_team=team,
            )

    def test_slug_reusable_across_teams(self):
        d1 = DepartmentFactory(slug="backend")
        d2 = DepartmentFactory(slug="backend")
        assert d1.team != d2.team


@pytest.mark.django_db
class TestMembership:
    def test_unique_user_workspace(self):
        user = UserFactory()
        ws = WorkspaceFactory()
        MembershipFactory(user=user, workspace=ws)
        with pytest.raises(IntegrityError):
            MembershipFactory(user=user, workspace=ws)


@pytest.mark.django_db
class TestApiKey:
    def test_generate_prefix(self):
        raw_key, key_hash, key_prefix = ApiKey.generate()
        assert raw_key.startswith("kf_")
        assert key_prefix == raw_key[:10]

    def test_hash_deterministic(self):
        raw_key = "kf_test-key-12345"
        assert ApiKey.hash_key(raw_key) == ApiKey.hash_key(raw_key)

    def test_hash_matches_generate(self):
        raw_key, key_hash, _ = ApiKey.generate()
        assert ApiKey.hash_key(raw_key) == key_hash
