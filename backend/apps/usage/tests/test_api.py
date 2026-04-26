from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.orgs.models import ApiKey, CoreSettings, SkillAuditRule
from apps.orgs.tests.factories import (
    DepartmentFactory,
    TeamFactory,
)
from apps.skills.enums import StatusChoices
from apps.skills.tests.factories import SkillFactory
from apps.usage.models import UsageEvent


@pytest.mark.django_db
class TestLogUsageEvent:
    def test_log_usage_event(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")

        raw_key, key_hash, key_prefix = ApiKey.generate()
        ApiKey.objects.create(
            workspace=ws,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="mcp-key",
        )

        client = Client()
        resp = client.post(
            "/api/v1/usage",
            data={
                "skill_id": str(skill.id),
                "version_number": 1,
                "client_id": "machine-42",
                "client_type": "MCP",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        event = UsageEvent.objects.first()
        assert event.skill == skill
        assert event.version_number == 1
        assert event.client_id == "machine-42"
        assert event.client_type == "MCP"

    def test_log_usage_event_with_session_auth(self, auth_client, admin_membership):
        """Session auth should work for POST /usage."""
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")

        resp = auth_client.post(
            "/api/v1/usage",
            data={
                "skill_id": str(skill.id),
                "version_number": 1,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


@pytest.mark.django_db
class TestListUsage:
    def test_list_usage_events(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy")
        UsageEvent.objects.create(
            skill=skill,
            version_number=1,
            client_id="m1",
            client_type="Cursor",
        )
        UsageEvent.objects.create(
            skill=skill,
            version_number=1,
            client_id="m2",
            client_type="Claude Desktop",
        )

        resp = auth_client.get("/api/v1/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2


@pytest.mark.django_db
class TestUsageSummary:
    def test_usage_summary_aggregation(self, auth_client, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="frontend")
        skill = SkillFactory(department=dept, slug="deploy", title="Deploy")
        UsageEvent.objects.create(
            skill=skill, version_number=1, client_id="m1", client_type="Cursor"
        )
        UsageEvent.objects.create(
            skill=skill, version_number=1, client_id="m2", client_type="Cursor"
        )
        UsageEvent.objects.create(
            skill=skill, version_number=2, client_id="m1", client_type="Claude Desktop"
        )

        resp = auth_client.get("/api/v1/usage/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
        summary = data["items"][0]
        assert summary["skill_slug"] == "deploy"
        assert summary["total_calls"] == 3
        assert summary["unique_clients"] == 2
        assert summary["client_type_breakdown"]["Cursor"] == 2
        assert summary["client_type_breakdown"]["Claude Desktop"] == 1


@pytest.mark.django_db
class TestUsageAnalytics:
    def _setup_workspace(self, admin_membership):
        ws = admin_membership.workspace
        team = TeamFactory(workspace=ws, slug="eng")
        dept = DepartmentFactory(team=team, slug="devops")

        rule = SkillAuditRule.objects.create(workspace=ws, period_days=90)
        CoreSettings.objects.create(workspace=ws, skill_audit=rule)

        return ws, team, dept

    def test_analytics_coverage(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)
        SkillFactory(department=dept, slug="onboarding", status=StatusChoices.PUBLISHED)
        SkillFactory(department=dept, slug="draft-proc", status=StatusChoices.DRAFT)

        UsageEvent.objects.create(skill=p1, version_number=1, client_id="m1", client_type="Cursor")

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        data = resp.json()

        cov = data["coverage"]
        assert cov["published_count"] == 2
        assert cov["consumed_count"] == 1
        assert cov["percentage"] == 50.0

    def test_analytics_stale_but_relied_on(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        stale_date = timezone.now() - timedelta(days=120)
        p1 = SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=stale_date,
            owner=admin_membership.user,
        )
        fresh = SkillFactory(
            department=dept,
            slug="fresh-proc",
            status=StatusChoices.PUBLISHED,
            last_reviewed_at=timezone.now(),
        )

        for _ in range(5):
            UsageEvent.objects.create(
                skill=p1, version_number=1, client_id="m1", client_type="Cursor"
            )
        UsageEvent.objects.create(
            skill=fresh, version_number=1, client_id="m1", client_type="Cursor"
        )

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        data = resp.json()

        stale = data["stale_but_relied_on"]
        assert len(stale) == 1
        assert stale[0]["skill_slug"] == "deploy"
        assert stale[0]["call_count"] == 5
        assert stale[0]["days_since_review"] == 120

    def test_analytics_daily_trend(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        today = timezone.now()
        yesterday = today - timedelta(days=1)
        UsageEvent.objects.create(skill=p1, version_number=1, client_id="m1", client_type="Cursor")
        event2 = UsageEvent.objects.create(
            skill=p1, version_number=1, client_id="m2", client_type="Claude Code"
        )
        UsageEvent.objects.filter(pk=event2.pk).update(called_at=yesterday)

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        data = resp.json()

        trend = data["daily_trend"]
        assert len(trend) == 2
        total = sum(d["count"] for d in trend)
        assert total == 2

    def test_analytics_client_breakdown(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        for _ in range(3):
            UsageEvent.objects.create(
                skill=p1, version_number=1, client_id="m1", client_type="Cursor"
            )
        UsageEvent.objects.create(
            skill=p1, version_number=1, client_id="m2", client_type="Claude Code"
        )

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        data = resp.json()

        breakdown = data["client_breakdown"]
        assert len(breakdown) == 2
        cursor_entry = next(b for b in breakdown if b["client_type"] == "Cursor")
        assert cursor_entry["count"] == 3
        assert cursor_entry["percentage"] == 75.0

    def test_analytics_empty_workspace(self, auth_client, admin_membership):
        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        data = resp.json()

        assert data["coverage"]["published_count"] == 0
        assert data["coverage"]["consumed_count"] == 0
        assert data["coverage"]["percentage"] == 0.0
        assert data["stale_but_relied_on"] == []
        assert data["daily_trend"] == []
        assert data["client_breakdown"] == []
        assert data["kpis"]["total_calls"] == 0
        assert data["kpis"]["total_calls_previous"] == 0
        assert data["kpis"]["active_clients"] == 0
        assert data["kpis"]["processes_touched"] == 0
        assert data["kpis"]["peak_day_date"] is None
        assert data["kpis"]["peak_day_count"] == 0
        assert data["coverage_gap"] == []
        assert data["tool_breakdown"] == []

    def test_analytics_kpis(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        # 3 current-period events from 2 distinct clients
        UsageEvent.objects.create(skill=p1, version_number=1, client_id="m1", client_type="Cursor")
        UsageEvent.objects.create(skill=p1, version_number=1, client_id="m1", client_type="Cursor")
        UsageEvent.objects.create(
            skill=p1, version_number=1, client_id="m2", client_type="Claude Code"
        )

        # 1 event in the previous period (40 days ago)
        prev = UsageEvent.objects.create(
            skill=p1, version_number=1, client_id="m3", client_type="Cursor"
        )
        UsageEvent.objects.filter(pk=prev.pk).update(called_at=timezone.now() - timedelta(days=40))

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]

        assert kpis["total_calls"] == 3
        assert kpis["total_calls_previous"] == 1
        assert kpis["active_clients"] == 2
        assert kpis["processes_touched"] == 1
        assert kpis["peak_day_date"] is not None
        assert kpis["peak_day_count"] == 3

    def test_analytics_coverage_gap(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(
            department=dept,
            slug="deploy",
            status=StatusChoices.PUBLISHED,
            owner=admin_membership.user,
        )
        p2 = SkillFactory(
            department=dept,
            slug="onboarding",
            status=StatusChoices.PUBLISHED,
        )
        SkillFactory(department=dept, slug="draft-proc", status=StatusChoices.DRAFT)

        UsageEvent.objects.create(skill=p1, version_number=1, client_id="m1", client_type="Cursor")

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        gap = resp.json()["coverage_gap"]

        assert len(gap) == 1
        assert gap[0]["skill_slug"] == p2.slug
        assert gap[0]["days_since_published"] >= 0

    def test_analytics_tool_breakdown(self, auth_client, admin_membership):
        ws, team, dept = self._setup_workspace(admin_membership)

        p1 = SkillFactory(department=dept, slug="deploy", status=StatusChoices.PUBLISHED)

        for _ in range(3):
            UsageEvent.objects.create(
                skill=p1,
                version_number=1,
                client_id="m1",
                client_type="MCP",
                tool_name="get_skill",
            )
        UsageEvent.objects.create(
            skill=p1,
            version_number=1,
            client_id="m1",
            client_type="MCP",
            tool_name="search_processes",
        )
        # Empty tool_name → bucketed as REST
        UsageEvent.objects.create(
            skill=p1, version_number=1, client_id="m1", client_type="REST API"
        )

        resp = auth_client.get("/api/v1/usage/analytics?days=30")
        assert resp.status_code == 200
        tools = resp.json()["tool_breakdown"]

        by_tool = {t["tool_name"]: t for t in tools}
        assert by_tool["get_skill"]["count"] == 3
        assert by_tool["get_skill"]["percentage"] == 60.0
        assert by_tool["search_processes"]["count"] == 1
        assert by_tool["REST"]["count"] == 1
