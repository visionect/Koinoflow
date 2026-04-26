import re
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Max
from django.db.models.functions import TruncDate
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import require_role
from apps.common.throttles import ReadThrottle, UsageLogThrottle
from apps.orgs.enums import RoleChoices
from apps.orgs.models import SYSTEM_KIND_AGENTS, get_effective_settings
from apps.skills.enums import StatusChoices
from apps.skills.models import Skill
from apps.usage.enums import ClientType
from apps.usage.models import UsageEvent

router = Router(tags=["usage"])

_CLIENT_SUFFIX_RE = re.compile(r"\s*\((koinoflow|unverified|local|verified)\)$", re.IGNORECASE)


def _oauth_client_name(request) -> str | None:
    token = getattr(request, "oauth_token", None)
    if token is None:
        return None
    app = getattr(token, "application", None)
    if app is None:
        return None
    return _CLIENT_SUFFIX_RE.sub("", app.name).strip() or None


# ── Schemas ──────────────────────────────────────────────────────────────


class UsageEventOut(Schema):
    id: str
    skill_title: str
    skill_slug: str
    version_number: int
    client_id: str
    client_type: str
    tool_name: str
    called_at: str


class UsageListOut(Schema):
    items: list[UsageEventOut]
    count: int


class SkillUsageSummary(Schema):
    skill_slug: str
    skill_title: str
    total_calls: int
    last_called_at: str | None
    unique_clients: int
    client_type_breakdown: dict[str, int]


class UsageSummaryListOut(Schema):
    items: list[SkillUsageSummary]
    count: int


class CreateUsageEventIn(Schema):
    skill_id: str
    version_number: int
    client_id: str = "unknown"
    client_type: str = ClientType.UNKNOWN
    tool_name: str = ""

    def model_post_init(self, __context):
        if not self.client_type or len(self.client_type) > 100:
            self.client_type = ClientType.UNKNOWN


# ── Helpers ──────────────────────────────────────────────────────────────


def _usage_event_out(event):
    return {
        "id": str(event.id),
        "skill_title": event.skill.title,
        "skill_slug": event.skill.slug,
        "version_number": event.version_number,
        "client_id": event.client_id,
        "client_type": event.client_type,
        "tool_name": event.tool_name,
        "called_at": event.called_at.isoformat(),
    }


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/usage", response=UsageListOut, auth=api_or_session, throttle=[ReadThrottle()])
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def list_usage(
    request,
    skill: str | None = None,
    client_type: str | None = None,
    days: int = 30,
    limit: int = 50,
    offset: int = 0,
):
    workspace = request.workspace
    days = max(1, min(days, 365))
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    since = timezone.now() - timedelta(days=days)

    qs = (
        UsageEvent.objects.filter(
            skill__department__team__workspace=workspace,
            skill__department__system_kind="",
            agent__isnull=True,
            called_at__gte=since,
        )
        .select_related("skill")
        .order_by("-called_at")
    )
    if skill:
        qs = qs.filter(skill__slug=skill)
    if client_type:
        qs = qs.filter(client_type=client_type)

    count = qs.count()
    items = [_usage_event_out(e) for e in qs[offset : offset + limit]]
    return {"items": items, "count": count}


@router.get(
    "/usage/summary",
    response=UsageSummaryListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def usage_summary(request, days: int = 30, limit: int = 50, offset: int = 0):
    workspace = request.workspace
    days = max(1, min(days, 365))
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    since = timezone.now() - timedelta(days=days)

    processes = (
        Skill.objects.filter(
            department__team__workspace=workspace,
            department__system_kind="",
            usage_events__called_at__gte=since,
            usage_events__agent__isnull=True,
        )
        .annotate(
            total_calls=Count("usage_events"),
            last_called_at=Max("usage_events__called_at"),
            unique_clients=Count("usage_events__client_id", distinct=True),
        )
        .filter(total_calls__gt=0)
        .order_by("-total_calls")
    )

    count = processes.count()
    page = list(processes[offset : offset + limit])
    page_ids = [p.id for p in page]

    breakdown_qs = (
        UsageEvent.objects.filter(skill_id__in=page_ids, called_at__gte=since, agent__isnull=True)
        .values("skill_id", "client_type")
        .annotate(count=Count("id"))
    )
    breakdown_map = defaultdict(dict)
    for row in breakdown_qs:
        breakdown_map[row["skill_id"]][row["client_type"]] = row["count"]

    items = []
    for p in page:
        items.append(
            {
                "skill_slug": p.slug,
                "skill_title": p.title,
                "total_calls": p.total_calls,
                "last_called_at": p.last_called_at.isoformat() if p.last_called_at else None,
                "unique_clients": p.unique_clients,
                "client_type_breakdown": breakdown_map.get(p.id, {}),
            }
        )
    return {"items": items, "count": count}


# ── Analytics schemas ─────────────────────────────────────────────────


class CoverageOut(Schema):
    consumed_count: int
    published_count: int
    percentage: float


class StaleReliedOnOut(Schema):
    skill_slug: str
    skill_title: str
    days_since_review: int
    call_count: int
    owner_email: str | None
    owner_first_name: str | None


class DailyTrendOut(Schema):
    date: str
    count: int


class ClientBreakdownOut(Schema):
    client_type: str
    count: int
    percentage: float


class KpiOut(Schema):
    total_calls: int
    total_calls_previous: int
    active_clients: int
    processes_touched: int
    peak_day_date: str | None
    peak_day_count: int


class CoverageGapOut(Schema):
    skill_slug: str
    skill_title: str
    owner_first_name: str | None
    days_since_published: int


class ToolBreakdownOut(Schema):
    tool_name: str
    count: int
    percentage: float


class UsageAnalyticsOut(Schema):
    coverage: CoverageOut
    stale_but_relied_on: list[StaleReliedOnOut]
    daily_trend: list[DailyTrendOut]
    client_breakdown: list[ClientBreakdownOut]
    kpis: KpiOut
    coverage_gap: list[CoverageGapOut]
    tool_breakdown: list[ToolBreakdownOut]


@router.get(
    "/usage/analytics",
    response=UsageAnalyticsOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def usage_analytics(request, days: int = 30):
    workspace = request.workspace
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)

    ws_filter = dict(
        skill__department__team__workspace=workspace,
        skill__department__system_kind="",
        agent__isnull=True,
        called_at__gte=since,
    )

    published_count = Skill.objects.filter(
        department__team__workspace=workspace,
        department__system_kind="",
        status=StatusChoices.PUBLISHED,
    ).count()
    consumed_count = UsageEvent.objects.filter(**ws_filter).values("skill_id").distinct().count()
    coverage_pct = (consumed_count / published_count * 100) if published_count else 0.0

    stale_processes = (
        Skill.objects.filter(
            department__team__workspace=workspace,
            department__system_kind="",
            status=StatusChoices.PUBLISHED,
            usage_events__called_at__gte=since,
            usage_events__agent__isnull=True,
        )
        .select_related("owner", "department__team")
        .annotate(call_count=Count("usage_events"))
        .filter(call_count__gt=0)
        .order_by("-call_count")[:20]
    )

    now = timezone.now()
    stale_items = []
    audit_cache: dict = {}
    for p in stale_processes:
        dept = p.department
        cache_key = (dept.team.workspace_id, dept.team_id, dept.id)
        if cache_key not in audit_cache:
            effective = get_effective_settings(
                dept.team.workspace_id, team_id=dept.team_id, department_id=dept.id
            )
            audit_cache[cache_key] = effective.get("skill_audit")
        rule = audit_cache[cache_key]
        if rule is None:
            continue
        if p.last_reviewed_at and p.last_reviewed_at >= now - timedelta(days=rule.period_days):
            continue
        days_since = (now - p.last_reviewed_at).days if p.last_reviewed_at else rule.period_days
        stale_items.append(
            {
                "skill_slug": p.slug,
                "skill_title": p.title,
                "days_since_review": days_since,
                "call_count": p.call_count,
                "owner_email": p.owner.email if p.owner else None,
                "owner_first_name": p.owner.first_name if p.owner else None,
            }
        )
        if len(stale_items) >= 5:
            break

    daily_trend = list(
        UsageEvent.objects.filter(**ws_filter)
        .annotate(date=TruncDate("called_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    daily_trend_out = [
        {"date": row["date"].isoformat(), "count": row["count"]} for row in daily_trend
    ]

    client_rows = list(
        UsageEvent.objects.filter(**ws_filter)
        .values("client_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    total_calls = sum(r["count"] for r in client_rows)
    client_breakdown = [
        {
            "client_type": r["client_type"],
            "count": r["count"],
            "percentage": round(r["count"] / total_calls * 100, 1) if total_calls else 0.0,
        }
        for r in client_rows
    ]

    # KPIs
    total_calls = sum(r["count"] for r in daily_trend)
    previous_since = since - timedelta(days=days)
    total_calls_previous = UsageEvent.objects.filter(
        skill__department__team__workspace=workspace,
        skill__department__system_kind="",
        agent__isnull=True,
        called_at__gte=previous_since,
        called_at__lt=since,
    ).count()
    active_clients = UsageEvent.objects.filter(**ws_filter).values("client_id").distinct().count()
    if daily_trend:
        peak = max(daily_trend, key=lambda r: r["count"])
        peak_day_date = peak["date"].isoformat()
        peak_day_count = peak["count"]
    else:
        peak_day_date = None
        peak_day_count = 0

    kpis = {
        "total_calls": total_calls,
        "total_calls_previous": total_calls_previous,
        "active_clients": active_clients,
        "processes_touched": consumed_count,
        "peak_day_date": peak_day_date,
        "peak_day_count": peak_day_count,
    }

    # Coverage gap: published processes with zero retrievals in period
    consumed_ids = (
        UsageEvent.objects.filter(**ws_filter).values_list("skill_id", flat=True).distinct()
    )
    gap_processes = (
        Skill.objects.filter(
            department__team__workspace=workspace,
            department__system_kind="",
            status=StatusChoices.PUBLISHED,
        )
        .exclude(id__in=list(consumed_ids))
        .select_related("owner")
        .order_by("created_at")[:10]
    )
    coverage_gap = [
        {
            "skill_slug": p.slug,
            "skill_title": p.title,
            "owner_first_name": p.owner.first_name if p.owner else None,
            "days_since_published": (now - p.created_at).days,
        }
        for p in gap_processes
    ]

    # Tool mix
    tool_rows = list(
        UsageEvent.objects.filter(**ws_filter)
        .values("tool_name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    tool_breakdown = [
        {
            "tool_name": r["tool_name"] if r["tool_name"] else "REST",
            "count": r["count"],
            "percentage": round(r["count"] / total_calls * 100, 1) if total_calls else 0.0,
        }
        for r in tool_rows
    ]

    return {
        "coverage": {
            "consumed_count": consumed_count,
            "published_count": published_count,
            "percentage": round(coverage_pct, 1),
        },
        "stale_but_relied_on": stale_items,
        "daily_trend": daily_trend_out,
        "client_breakdown": client_breakdown,
        "kpis": kpis,
        "coverage_gap": coverage_gap,
        "tool_breakdown": tool_breakdown,
    }


@router.post("/usage", auth=api_or_session, throttle=[UsageLogThrottle()])
def log_usage_event(request, payload: CreateUsageEventIn):
    workspace = request.workspace
    agent = getattr(request, "agent", None)
    try:
        skill = Skill.objects.get(
            id=payload.skill_id,
            department__team__workspace=workspace,
        )
    except Skill.DoesNotExist:
        raise HttpError(404, "Skill not found")

    if agent is not None:
        from apps.agents.selectors import skills_for_agent

        if not skills_for_agent(agent).filter(id=skill.id).exists():
            raise HttpError(404, "Skill not found")
    elif skill.department.system_kind == SYSTEM_KIND_AGENTS:
        raise HttpError(404, "Skill not found")

    client_type = payload.client_type
    if agent is not None:
        client_type = "Agent"
    if client_type == ClientType.MCP:
        resolved = _oauth_client_name(request)
        if resolved:
            client_type = resolved

    UsageEvent.objects.create(
        skill=skill,
        agent=agent,
        version_number=payload.version_number,
        client_id=payload.client_id,
        client_type=client_type,
        tool_name=payload.tool_name,
    )
    return {"ok": True}
