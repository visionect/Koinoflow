from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.billing.enums import SubscriptionStatus
from apps.billing.models import WorkspaceSubscription
from apps.orgs.enums import EntityType, InvitationStatus, RoleChoices
from apps.orgs.models import CoreSlug, Membership, PendingInvitation
from apps.orgs.tests.factories import (
    DepartmentFactory,
    MembershipFactory,
    PendingInvitationFactory,
    TeamFactory,
    WorkspaceFactory,
)
from apps.processes.enums import VisibilityChoices
from apps.processes.tests.factories import ProcessFactory


def _get_slug(entity_type, entity_id):
    return CoreSlug.objects.get(entity_type=entity_type, entity_id=entity_id).slug


@pytest.mark.django_db
class TestCreateWorkspace:
    def test_create_workspace(self):
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "Acme Corp", "slug": "acme-corp"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Corp"
        assert data["slug"] == "acme-corp"
        assert Membership.objects.filter(user=user, role=RoleChoices.ADMIN).exists()
        assert CoreSlug.objects.filter(entity_type=EntityType.WORKSPACE, slug="acme-corp").exists()

    def test_create_workspace_duplicate_slug_auto_suffixes(self):
        WorkspaceFactory(slug="taken-slug")
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "Dupe", "slug": "taken-slug"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "taken-slug-1"

    def test_create_workspace_duplicate_slug_increments(self):
        WorkspaceFactory(slug="acme")
        WorkspaceFactory(slug="acme-1")
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "Third", "slug": "acme"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "acme-2"

    @override_settings(ENABLE_BILLING=True)
    def test_create_workspace_creates_trial_subscription(self):
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "Trial Co", "slug": "trial-co"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        workspace = Membership.objects.get(user=user).workspace
        ws_sub = WorkspaceSubscription.objects.select_related("subscription__customer").get(
            workspace=workspace
        )
        sub = ws_sub.subscription
        assert sub.status == SubscriptionStatus.IN_TRIAL
        assert sub.trial_start is not None
        assert sub.trial_end is not None
        assert (sub.trial_end - sub.trial_start).days == 30
        assert sub.customer.email == user.email

    @override_settings(ENABLE_BILLING=False)
    def test_create_workspace_skips_subscription_when_billing_disabled(self):
        user = UserFactory()
        client = Client()
        client.force_login(user)
        resp = client.post(
            "/api/v1/workspaces",
            data={"name": "OSS Co", "slug": "oss-co"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        workspace = Membership.objects.get(user=user).workspace
        assert not WorkspaceSubscription.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
class TestGetWorkspace:
    def test_get_workspace(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        slug = _get_slug(EntityType.WORKSPACE, ws.id)
        resp = auth_client.get(f"/api/v1/workspaces/{slug}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == slug

    def test_get_workspace_wrong_slug(self, auth_client):
        resp = auth_client.get("/api/v1/workspaces/nonexistent")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestListTeams:
    def test_list_teams(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        TeamFactory(workspace=ws, name="Engineering", slug="engineering")
        TeamFactory(workspace=ws, name="Product", slug="product")
        other_ws = WorkspaceFactory()
        TeamFactory(workspace=other_ws, name="Other Team", slug="other-team")

        resp = auth_client.get("/api/v1/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2
        names = {t["name"] for t in data["items"]}
        assert names == {"Engineering", "Product"}

    def test_list_teams_includes_department_count(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        DepartmentFactory(team=team, slug="frontend")
        DepartmentFactory(team=team, slug="backend")

        resp = auth_client.get("/api/v1/teams")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["department_count"] == 2


@pytest.mark.django_db
class TestCreateTeam:
    def test_create_team(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/teams",
            data={"name": "Engineering", "slug": "engineering"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Engineering"
        assert CoreSlug.objects.filter(
            entity_type=EntityType.TEAM,
            slug="engineering",
            scope_workspace=admin_membership.workspace,
        ).exists()

    def test_create_team_duplicate_slug_auto_suffixes(self, auth_client, admin_membership):
        TeamFactory(workspace=admin_membership.workspace, slug="engineering")
        resp = auth_client.post(
            "/api/v1/teams",
            data={"name": "Eng 2", "slug": "engineering"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "engineering-1"

    def test_create_team_member_forbidden(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.post(
            "/api/v1/teams",
            data={"name": "Nope", "slug": "nope"},
            content_type="application/json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestGetTeam:
    def test_get_team_with_departments(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        DepartmentFactory(team=team, slug="frontend", name="Frontend")

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "eng"
        assert len(data["departments"]) == 1
        assert data["departments"][0]["slug"] == "frontend"

    def test_department_process_count_includes_team_wide_from_sibling(
        self, auth_client, admin_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        backend = DepartmentFactory(team=team, slug="backend")
        DepartmentFactory(team=team, slug="frontend")
        # Team-wide process owned by backend — should appear in frontend's count too
        ProcessFactory(department=backend, visibility=VisibilityChoices.TEAM)

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        depts = {d["slug"]: d for d in resp.json()["departments"]}
        assert depts["backend"]["process_count"] == 1
        assert depts["frontend"]["process_count"] == 1

    def test_department_process_count_includes_workspace_wide_from_sibling(
        self, auth_client, admin_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        backend = DepartmentFactory(team=team, slug="backend")
        DepartmentFactory(team=team, slug="frontend")
        ProcessFactory(department=backend, visibility=VisibilityChoices.WORKSPACE)

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        depts = {d["slug"]: d for d in resp.json()["departments"]}
        assert depts["backend"]["process_count"] == 1
        assert depts["frontend"]["process_count"] == 1

    def test_department_process_count_excludes_department_scoped_from_sibling(
        self, auth_client, admin_membership
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        backend = DepartmentFactory(team=team, slug="backend")
        DepartmentFactory(team=team, slug="frontend")
        ProcessFactory(department=backend, visibility=VisibilityChoices.DEPARTMENT)

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        depts = {d["slug"]: d for d in resp.json()["departments"]}
        assert depts["backend"]["process_count"] == 1
        assert depts["frontend"]["process_count"] == 0

    def test_department_process_count_excludes_team_wide_from_other_team(
        self, auth_client, admin_membership
    ):
        ws = admin_membership.workspace
        team_a = TeamFactory(workspace=ws, slug="eng")
        team_b = TeamFactory(workspace=ws, slug="ops")
        DepartmentFactory(team=team_a, slug="backend")
        dept_b = DepartmentFactory(team=team_b, slug="infra")
        # Team-wide process in team_b should not bleed into team_a
        ProcessFactory(department=dept_b, visibility=VisibilityChoices.TEAM)

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        depts = {d["slug"]: d for d in resp.json()["departments"]}
        assert depts["backend"]["process_count"] == 0

    def test_department_process_count_with_shared_with(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        backend = DepartmentFactory(team=team, slug="backend")
        frontend = DepartmentFactory(team=team, slug="frontend")
        process = ProcessFactory(department=backend, visibility=VisibilityChoices.DEPARTMENT)
        process.shared_with.add(frontend)

        resp = auth_client.get("/api/v1/teams/eng")
        assert resp.status_code == 200
        depts = {d["slug"]: d for d in resp.json()["departments"]}
        assert depts["backend"]["process_count"] == 1
        assert depts["frontend"]["process_count"] == 1


@pytest.mark.django_db
class TestUpdateTeam:
    def test_update_team_name(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        TeamFactory(workspace=ws, slug="eng", name="Old Name")

        resp = auth_client.patch(
            "/api/v1/teams/eng",
            data={"name": "New Name"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"


@pytest.mark.django_db
class TestDeleteTeam:
    def test_delete_team(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        TeamFactory(workspace=ws, slug="eng")

        resp = auth_client.delete("/api/v1/teams/eng")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert not CoreSlug.objects.filter(
            entity_type=EntityType.TEAM, slug="eng", scope_workspace=ws
        ).exists()


@pytest.mark.django_db
class TestListDepartments:
    def test_list_departments(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        DepartmentFactory(team=team, slug="frontend", name="Frontend")
        DepartmentFactory(team=team, slug="backend", name="Backend")

        resp = auth_client.get("/api/v1/departments")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    def test_list_departments_filter_by_team(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        eng = TeamFactory(workspace=ws, slug="eng")
        prod = TeamFactory(workspace=ws, slug="prod")
        DepartmentFactory(team=eng, slug="frontend")
        DepartmentFactory(team=prod, slug="design")

        resp = auth_client.get("/api/v1/departments?team=eng")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["team_slug"] == "eng"


@pytest.mark.django_db
class TestCreateDepartment:
    def test_create_department(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        TeamFactory(workspace=ws, slug="eng")

        resp = auth_client.post(
            "/api/v1/departments",
            data={"team_slug": "eng", "name": "Frontend", "slug": "frontend"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Frontend"
        assert resp.json()["team_slug"] == "eng"

    def test_create_department_with_owner(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        TeamFactory(workspace=ws, slug="eng")
        owner = admin_membership.user

        resp = auth_client.post(
            "/api/v1/departments",
            data={
                "team_slug": "eng",
                "name": "Frontend",
                "slug": "frontend",
                "owner_id": str(owner.id),
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["owner"]["email"] == owner.email

    def test_create_department_duplicate_slug_auto_suffixes(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.post(
            "/api/v1/departments",
            data={"team_slug": "eng", "name": "Dupe", "slug": "frontend"},
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "frontend-1"


@pytest.mark.django_db
class TestUpdateDepartment:
    def test_update_department_name(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend", name="Old")

        resp = auth_client.patch(
            f"/api/v1/departments/{dept.id}",
            data={"name": "New Name"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"


@pytest.mark.django_db
class TestDeleteDepartment:
    def test_delete_department(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.delete(f"/api/v1/departments/{dept.id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


@pytest.mark.django_db
class TestGetDepartment:
    def test_get_department(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend", name="Frontend")

        resp = auth_client.get(f"/api/v1/departments/{dept.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Frontend"
        assert data["slug"] == "frontend"
        assert data["team_slug"] == "eng"
        assert "process_count" in data

    def test_get_department_not_found(self, auth_client, admin_membership):
        import uuid

        resp = auth_client.get(f"/api/v1/departments/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_department_wrong_workspace(self, auth_client, admin_membership):
        other_ws = WorkspaceFactory()
        team = TeamFactory(workspace=other_ws, slug="other-team")
        dept = DepartmentFactory(team=team, slug="other-dept")

        resp = auth_client.get(f"/api/v1/departments/{dept.id}")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestListMembers:
    def test_list_members_admin_sees_all(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")
        m2 = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        m2.departments.add(dept)

        resp = auth_client.get("/api/v1/members")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2
        emails = {m["email"] for m in data["items"]}
        assert admin_membership.user.email in emails
        assert m2.user.email in emails

    def test_list_members_team_manager_sees_team_members(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")
        tm = MembershipFactory(workspace=ws, role=RoleChoices.TEAM_MANAGER, team=team)

        member_in_team = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        member_in_team.departments.add(dept)

        other_team = TeamFactory(workspace=ws, slug="sales")
        other_dept = DepartmentFactory(team=other_team, slug="accounts")
        member_outside = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        member_outside.departments.add(other_dept)

        client = Client()
        client.force_login(tm.user)
        resp = client.get("/api/v1/members")
        assert resp.status_code == 200
        emails = {m["email"] for m in resp.json()["items"]}
        assert tm.user.email in emails
        assert member_in_team.user.email in emails
        assert member_outside.user.email not in emails

    def test_list_members_member_sees_peers(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")

        m1 = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        m1.departments.add(dept)
        m2 = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        m2.departments.add(dept)

        other_dept = DepartmentFactory(team=team, slug="be")
        m3 = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)
        m3.departments.add(other_dept)

        client = Client()
        client.force_login(m1.user)
        resp = client.get("/api/v1/members")
        assert resp.status_code == 200
        emails = {m["email"] for m in resp.json()["items"]}
        assert m1.user.email in emails
        assert m2.user.email in emails
        assert m3.user.email not in emails

    def test_list_members_excludes_other_workspaces(self, auth_client, admin_membership):
        other_ws = WorkspaceFactory()
        MembershipFactory(workspace=other_ws, role=RoleChoices.ADMIN)

        resp = auth_client.get("/api/v1/members")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1


@pytest.mark.django_db
class TestCoreSettings:
    def test_get_settings_empty(self, auth_client, admin_membership):
        resp = auth_client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["require_review_before_publish"] is None
        assert data["enable_version_history"] is None
        assert data["enable_api_access"] is None

    def test_upsert_workspace_settings(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        resp = auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "require_review_before_publish": True,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["require_review_before_publish"] is True
        assert data["team_id"] is None
        assert data["department_id"] is None

    def test_settings_inheritance(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "enable_api_access": True,
            },
            content_type="application/json",
        )
        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "team_id": str(team.id),
                "enable_api_access": False,
            },
            content_type="application/json",
        )

        resp = auth_client.get(f"/api/v1/settings?team_id={team.id}&department_id={dept.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enable_api_access"] is False

    def test_settings_dept_requires_team(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        resp = auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "department_id": str(dept.id),
            },
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_upsert_settings_with_process_audit(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import ProcessAuditRuleFactory

        ws = admin_membership.workspace
        rule = ProcessAuditRuleFactory(workspace=ws, period_days=30)

        resp = auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "process_audit_id": str(rule.id),
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["process_audit"]["id"] == str(rule.id)
        assert data["process_audit"]["period_days"] == 30

    def test_clear_process_audit_setting(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import ProcessAuditRuleFactory

        ws = admin_membership.workspace
        rule = ProcessAuditRuleFactory(workspace=ws, period_days=30)

        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "process_audit_id": str(rule.id),
            },
            content_type="application/json",
        )

        resp = auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "process_audit_id": "",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["process_audit"] is None

    def test_effective_settings_inherits_process_audit(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import ProcessAuditRuleFactory

        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        rule = ProcessAuditRuleFactory(workspace=ws, period_days=60)

        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "process_audit_id": str(rule.id),
            },
            content_type="application/json",
        )

        resp = auth_client.get(f"/api/v1/settings?team_id={team.id}&department_id={dept.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["process_audit"]["id"] == str(rule.id)
        assert data["process_audit"]["period_days"] == 60

    def test_effective_settings_process_audit_none_by_default(
        self,
        auth_client,
        admin_membership,
    ):
        resp = auth_client.get("/api/v1/settings")
        assert resp.status_code == 200
        assert resp.json()["process_audit"] is None

    def test_get_settings_includes_require_change_summary(self, auth_client, admin_membership):
        resp = auth_client.get("/api/v1/settings")
        assert resp.status_code == 200
        assert resp.json()["require_change_summary"] is None

    def test_upsert_require_change_summary(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        resp = auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "require_change_summary": True,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["require_change_summary"] is True

    def test_require_change_summary_inheritance(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")

        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "require_change_summary": True,
            },
            content_type="application/json",
        )
        auth_client.patch(
            "/api/v1/settings",
            data={
                "workspace_id": str(ws.id),
                "team_id": str(team.id),
                "require_change_summary": False,
            },
            content_type="application/json",
        )

        resp = auth_client.get(f"/api/v1/settings?team_id={team.id}&department_id={dept.id}")
        assert resp.status_code == 200
        assert resp.json()["require_change_summary"] is False


@pytest.mark.django_db
class TestAuditRules:
    def test_list_audit_rules_empty(self, auth_client, admin_membership):
        resp = auth_client.get("/api/v1/audit-rules")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "count": 0}

    def test_create_audit_rule(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/audit-rules",
            data={"period_days": 30},
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["period_days"] == 30
        assert "id" in data

    def test_create_audit_rule_invalid_period(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/audit-rules",
            data={"period_days": 0},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_list_audit_rules_returns_created(self, auth_client, admin_membership):
        auth_client.post(
            "/api/v1/audit-rules",
            data={"period_days": 30},
            content_type="application/json",
        )
        auth_client.post(
            "/api/v1/audit-rules",
            data={"period_days": 90},
            content_type="application/json",
        )
        resp = auth_client.get("/api/v1/audit-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["period_days"] == 30
        assert data["items"][1]["period_days"] == 90

    def test_delete_audit_rule(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/audit-rules",
            data={"period_days": 30},
            content_type="application/json",
        )
        rule_id = resp.json()["id"]

        resp = auth_client.delete(f"/api/v1/audit-rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        resp = auth_client.get("/api/v1/audit-rules")
        assert resp.json() == {"items": [], "count": 0}

    def test_delete_audit_rule_not_found(self, auth_client, admin_membership):
        import uuid

        resp = auth_client.delete(f"/api/v1/audit-rules/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_member_cannot_create_audit_rule(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.post(
            "/api/v1/audit-rules",
            data={"period_days": 30},
            content_type="application/json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestInviteMember:
    def test_invite_returns_generic_200_for_new_email(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/members",
            data={"email": "newuser@example.com", "role": "member"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Invitation sent"
        assert PendingInvitation.objects.filter(email="newuser@example.com").exists()

    def test_invite_returns_generic_200_for_existing_member(
        self,
        auth_client,
        admin_membership,
    ):
        ws = admin_membership.workspace
        existing = MembershipFactory(workspace=ws, role=RoleChoices.MEMBER)

        resp = auth_client.post(
            "/api/v1/members",
            data={"email": existing.user.email, "role": "member"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Invitation sent"
        assert not PendingInvitation.objects.filter(email=existing.user.email).exists()

    def test_invite_returns_generic_200_for_nonexistent_email(
        self,
        auth_client,
        admin_membership,
    ):
        resp = auth_client.post(
            "/api/v1/members",
            data={"email": "nobody@nowhere.com", "role": "member"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Invitation sent"
        assert PendingInvitation.objects.filter(email="nobody@nowhere.com").exists()

    def test_no_email_enumeration_same_response(self, auth_client, admin_membership):
        """Both existing and non-existing emails get the same response."""
        UserFactory(email="exists@example.com")
        resp1 = auth_client.post(
            "/api/v1/members",
            data={"email": "exists@example.com", "role": "member"},
            content_type="application/json",
        )
        resp2 = auth_client.post(
            "/api/v1/members",
            data={"email": "doesnotexist@example.com", "role": "member"},
            content_type="application/json",
        )
        assert resp1.status_code == resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_invite_duplicate_pending_returns_200(self, auth_client, admin_membership):
        auth_client.post(
            "/api/v1/members",
            data={"email": "dup@example.com", "role": "member"},
            content_type="application/json",
        )
        resp = auth_client.post(
            "/api/v1/members",
            data={"email": "dup@example.com", "role": "member"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert (
            PendingInvitation.objects.filter(
                email="dup@example.com", status=InvitationStatus.PENDING
            ).count()
            == 1
        )

    def test_invite_creates_pending_invitation_with_team(
        self,
        auth_client,
        admin_membership,
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")

        resp = auth_client.post(
            "/api/v1/members",
            data={
                "email": "tm@example.com",
                "role": "team_manager",
                "team_id": str(team.id),
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        inv = PendingInvitation.objects.get(email="tm@example.com")
        assert inv.role == RoleChoices.TEAM_MANAGER
        assert inv.team_id == team.id

    def test_invite_creates_pending_invitation_with_departments(
        self,
        auth_client,
        admin_membership,
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")

        resp = auth_client.post(
            "/api/v1/members",
            data={
                "email": "dev@example.com",
                "role": "member",
                "department_ids": [str(dept.id)],
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        inv = PendingInvitation.objects.get(email="dev@example.com")
        assert list(inv.departments.values_list("id", flat=True)) == [dept.id]

    def test_invite_invalid_role_returns_400(self, auth_client, admin_membership):
        resp = auth_client.post(
            "/api/v1/members",
            data={"email": "x@example.com", "role": "superuser"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_team_manager_can_only_invite_members(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")
        tm = MembershipFactory(workspace=ws, role=RoleChoices.TEAM_MANAGER, team=team)

        client = Client()
        client.force_login(tm.user)
        resp = client.post(
            "/api/v1/members",
            data={
                "email": "x@example.com",
                "role": "admin",
                "department_ids": [str(dept.id)],
            },
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_member_cannot_invite(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.post(
            "/api/v1/members",
            data={"email": "x@example.com", "role": "member"},
            content_type="application/json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestInvitationEndpoints:
    def test_list_invitations_admin(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        PendingInvitationFactory(workspace=ws, email="a@example.com")
        PendingInvitationFactory(workspace=ws, email="b@example.com")

        resp = auth_client.get("/api/v1/invitations")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    def test_list_invitations_excludes_cancelled(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        PendingInvitationFactory(workspace=ws, email="a@example.com")
        PendingInvitationFactory(
            workspace=ws,
            email="b@example.com",
            status=InvitationStatus.CANCELLED,
        )

        resp = auth_client.get("/api/v1/invitations")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_cancel_invitation(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        inv = PendingInvitationFactory(workspace=ws, email="a@example.com")

        resp = auth_client.delete(f"/api/v1/invitations/{inv.id}")
        assert resp.status_code == 200
        inv.refresh_from_db()
        assert inv.status == InvitationStatus.CANCELLED

    def test_cancel_invitation_not_found(self, auth_client, admin_membership):
        import uuid

        resp = auth_client.delete(f"/api/v1/invitations/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_accept_invitation(self, admin_membership):
        ws = admin_membership.workspace
        user = UserFactory(email="invited@example.com")
        inv = PendingInvitationFactory(
            workspace=ws,
            email="invited@example.com",
            role="member",
        )

        client = Client()
        client.force_login(user)
        resp = client.post(f"/api/v1/invitations/{inv.token}/accept")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Invitation accepted"
        assert Membership.objects.filter(workspace=ws, user=user).exists()
        inv.refresh_from_db()
        assert inv.status == InvitationStatus.ACCEPTED

    def test_accept_invitation_expired(self, admin_membership):
        ws = admin_membership.workspace
        user = UserFactory(email="expired@example.com")
        inv = PendingInvitationFactory(
            workspace=ws,
            email="expired@example.com",
            expires_at=timezone.now() - timedelta(hours=1),
        )

        client = Client()
        client.force_login(user)
        resp = client.post(f"/api/v1/invitations/{inv.token}/accept")
        assert resp.status_code == 410
        inv.refresh_from_db()
        assert inv.status == InvitationStatus.EXPIRED

    def test_accept_invitation_wrong_email(self, admin_membership):
        ws = admin_membership.workspace
        user = UserFactory(email="wrong@example.com")
        inv = PendingInvitationFactory(
            workspace=ws,
            email="right@example.com",
        )

        client = Client()
        client.force_login(user)
        resp = client.post(f"/api/v1/invitations/{inv.token}/accept")
        assert resp.status_code == 403

    def test_accept_invitation_creates_membership_with_role_and_team(
        self,
        admin_membership,
    ):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="fe")
        user = UserFactory(email="tm@example.com")
        inv = PendingInvitationFactory(
            workspace=ws,
            email="tm@example.com",
            role="team_manager",
            team=team,
        )
        inv.departments.add(dept)

        client = Client()
        client.force_login(user)
        resp = client.post(f"/api/v1/invitations/{inv.token}/accept")
        assert resp.status_code == 200
        m = Membership.objects.get(workspace=ws, user=user)
        assert m.role == RoleChoices.TEAM_MANAGER
        assert m.team_id == team.id
        assert dept.id in set(m.departments.values_list("id", flat=True))

    def test_accept_invitation_already_member(self, admin_membership):
        ws = admin_membership.workspace
        user = admin_membership.user
        inv = PendingInvitationFactory(
            workspace=ws,
            email=user.email,
        )

        client = Client()
        client.force_login(user)
        resp = client.post(f"/api/v1/invitations/{inv.token}/accept")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "You are already a member of this workspace"
        inv.refresh_from_db()
        assert inv.status == InvitationStatus.ACCEPTED

    def test_member_cannot_list_invitations(self, member_membership):
        client = Client()
        client.force_login(member_membership.user)
        resp = client.get("/api/v1/invitations")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestStalenessAlertRules:
    def test_list_rules_empty(self, auth_client, admin_membership):
        resp = auth_client.get("/api/v1/staleness-alert-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_create_rule(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        resp = auth_client.post(
            "/api/v1/staleness-alert-rules",
            data={
                "workspace_id": str(ws.id),
                "period_days": 30,
                "notify_admins": True,
                "notify_team_managers": False,
                "notify_process_owner": True,
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["period_days"] == 30
        assert data["notify_admins"] is True
        assert data["notify_team_managers"] is False
        assert data["notify_process_owner"] is True

    def test_update_rule(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import StalenessAlertRuleFactory

        ws = admin_membership.workspace
        rule = StalenessAlertRuleFactory(workspace=ws, period_days=30)
        resp = auth_client.patch(
            f"/api/v1/staleness-alert-rules/{rule.id}",
            data={"period_days": 60, "notify_team_managers": True},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 60
        assert data["notify_team_managers"] is True
        assert data["notify_admins"] is True

    def test_delete_rule(self, auth_client, admin_membership):
        from apps.orgs.models import StalenessAlertRule
        from apps.orgs.tests.factories import StalenessAlertRuleFactory

        ws = admin_membership.workspace
        rule = StalenessAlertRuleFactory(workspace=ws)
        resp = auth_client.delete(f"/api/v1/staleness-alert-rules/{rule.id}")
        assert resp.status_code == 200
        assert not StalenessAlertRule.objects.filter(id=rule.id).exists()

    def test_cannot_access_other_workspace_rule(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import StalenessAlertRuleFactory, WorkspaceFactory

        other_ws = WorkspaceFactory()
        rule = StalenessAlertRuleFactory(workspace=other_ws)
        resp = auth_client.patch(
            f"/api/v1/staleness-alert-rules/{rule.id}",
            data={"period_days": 99},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_upsert_settings_with_staleness_alert(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import StalenessAlertRuleFactory

        ws = admin_membership.workspace
        rule = StalenessAlertRuleFactory(workspace=ws, period_days=45)
        resp = auth_client.patch(
            "/api/v1/settings",
            data={"workspace_id": str(ws.id), "staleness_alert_id": str(rule.id)},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["staleness_alert"]["id"] == str(rule.id)
        assert data["staleness_alert"]["period_days"] == 45

    def test_clear_staleness_alert_setting(self, auth_client, admin_membership):
        from apps.orgs.tests.factories import StalenessAlertRuleFactory

        ws = admin_membership.workspace
        rule = StalenessAlertRuleFactory(workspace=ws)
        auth_client.patch(
            "/api/v1/settings",
            data={"workspace_id": str(ws.id), "staleness_alert_id": str(rule.id)},
            content_type="application/json",
        )
        resp = auth_client.patch(
            "/api/v1/settings",
            data={"workspace_id": str(ws.id), "staleness_alert_id": ""},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["staleness_alert"] is None

    def test_member_cannot_create_rule(self, member_membership):
        ws = member_membership.workspace
        client = Client()
        client.force_login(member_membership.user)
        resp = client.post(
            "/api/v1/staleness-alert-rules",
            data={
                "workspace_id": str(ws.id),
                "period_days": 30,
                "notify_admins": True,
                "notify_team_managers": False,
                "notify_process_owner": False,
            },
            content_type="application/json",
        )
        assert resp.status_code == 403
