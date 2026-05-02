"""Sandbox analytics aggregation and API endpoint."""

from datetime import timedelta

from django.db.models import (
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
    Q,
)
from django.db.models.functions import TruncDate
from django.utils import timezone
from ninja import Router
from ninja.schema import Schema

from apps.accounts.auth import api_or_session
from apps.common.throttles import ReadThrottle
from apps.orgs.models import Membership
from apps.skills.models import SkillExecutionRun

router = Router(tags=["sandbox-analytics"])


# ── Schemas ───────────────────────────────────────────────────────────────


class SandboxAnalyticsKpi(Schema):
    adoption_rate: float
    active_skills_count: int
    total_runs_24h: int
    total_runs_7d: int
    ai_edit_success_rate: float
    mean_time_to_fix_ms: float | None
    debugger_sessions_count: int
    mean_debugger_duration_ms: float | None


class MostDebuggedSkill(Schema):
    skill_slug: str
    skill_title: str
    debugger_session_count: int
    last_debugged_at: str | None
    failure_count: int


class RunStatusBreakdown(Schema):
    succeeded: int
    failed: int
    timeout: int
    cancelled: int


class DailyRunTrend(Schema):
    date: str
    runs: int
    failures: int


class SandboxAnalyticsOut(Schema):
    kpis: SandboxAnalyticsKpi
    most_debugged_skills: list[MostDebuggedSkill]
    run_status_breakdown: RunStatusBreakdown
    daily_runs_trend: list[DailyRunTrend]


# ── Helpers ───────────────────────────────────────────────────────────────


def _get_sandbox_runs_qs(workspace, since):
    """Return sandbox-enabled skill execution runs within the date range."""
    return SkillExecutionRun.objects.filter(
        workspace=workspace,
        skill__execution_enabled=True,
        created_at__gte=since,
    ).select_related("skill", "version", "agent", "user")


def _compute_adoption_rate(workspace, since):
    """Count distinct users who ran at least one sandbox skill in period / total workspace
    members."""
    sandbox_users = (
        SkillExecutionRun.objects.filter(
            workspace=workspace,
            skill__execution_enabled=True,
            created_at__gte=since,
            user__isnull=False,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    total_members = (
        Membership.objects.filter(workspace=workspace)
        .values_list("user_id", flat=True)
        .distinct()
        .count()
    )
    if total_members == 0:
        return 0.0
    return round(len(sandbox_users) / total_members * 100, 1)


def _compute_ai_edit_success_rate(workspace, since):
    """
    AI edit success rate: percentage of runs where the inputs contain ai_edited=true
    and the run succeeded.
    """
    ai_edited_runs = _get_sandbox_runs_qs(workspace, since).filter(inputs__ai_edited=True)
    total_ai_edited = ai_edited_runs.count()
    if total_ai_edited == 0:
        return 0.0
    succeeded = ai_edited_runs.filter(status=SkillExecutionRun.StatusChoices.SUCCEEDED).count()
    return round(succeeded / total_ai_edited * 100, 1)


def _compute_mean_time_to_fix(workspace, since):
    """
    For each failure→AI edit→success chain, compute time from failure's finished_at
    to the next successful run's started_at, then average.
    """
    # Get failed runs
    failed_runs = list(
        _get_sandbox_runs_qs(workspace, since)
        .filter(
            status__in=[
                SkillExecutionRun.StatusChoices.FAILED,
                SkillExecutionRun.StatusChoices.TIMEOUT,
            ]
        )
        .filter(finished_at__isnull=False)
        .order_by("skill_id", "finished_at")
    )

    if not failed_runs:
        return None

    fix_durations = []
    for failed_run in failed_runs:
        # Find the next successful run for the same skill that was ai_edited
        next_success = (
            SkillExecutionRun.objects.filter(
                skill=failed_run.skill,
                workspace=workspace,
                created_at__gt=failed_run.created_at,
                status=SkillExecutionRun.StatusChoices.SUCCEEDED,
                inputs__ai_edited=True,
                started_at__isnull=False,
            )
            .order_by("created_at")
            .first()
        )
        if next_success and next_success.started_at and failed_run.finished_at:
            duration = (next_success.started_at - failed_run.finished_at).total_seconds() * 1000
            if duration >= 0:
                fix_durations.append(duration)

    if not fix_durations:
        return None
    return round(sum(fix_durations) / len(fix_durations), 1)


def _compute_debugger_stats(workspace, since):
    """Filter debugger sessions and compute duration stats."""
    debugger_runs = _get_sandbox_runs_qs(workspace, since).filter(inputs__debugger_session=True)

    count = debugger_runs.count()
    if count == 0:
        return 0, None

    durations = list(
        debugger_runs.annotate(
            duration_ms=ExpressionWrapper(
                (F("finished_at") - F("started_at")) * 86400000,
                output_field=DurationField(),
            )
        )
        .filter(finished_at__isnull=False, started_at__isnull=False)
        .values_list("duration_ms", flat=True)
    )

    # Convert DurationField to milliseconds
    durations_ms = []
    for d in durations:
        if d is not None:
            durations_ms.append(d.total_seconds() * 1000)

    mean_duration = round(sum(durations_ms) / len(durations_ms), 1) if durations_ms else None
    return count, mean_duration


def _compute_most_debugged_skills(workspace, since, limit=10):
    """Group debugger sessions by skill."""
    debugger_runs = _get_sandbox_runs_qs(workspace, since).filter(inputs__debugger_session=True)

    skills_data = (
        debugger_runs.values("skill_id", "skill__slug", "skill__title")
        .annotate(
            session_count=Count("id"),
            last_debugged_at=Max("created_at"),
            failure_count=Count(
                "id",
                filter=Q(
                    status__in=[
                        SkillExecutionRun.StatusChoices.FAILED,
                        SkillExecutionRun.StatusChoices.TIMEOUT,
                    ]
                ),
            ),
        )
        .order_by("-session_count")[:limit]
    )

    return [
        {
            "skill_slug": row["skill__slug"],
            "skill_title": row["skill__title"],
            "debugger_session_count": row["session_count"],
            "last_debugged_at": row["last_debugged_at"].isoformat()
            if row["last_debugged_at"]
            else None,
            "failure_count": row["failure_count"],
        }
        for row in skills_data
    ]


# ── Endpoint ──────────────────────────────────────────────────────────────


@router.get(
    "/sandbox/analytics",
    response=SandboxAnalyticsOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def sandbox_analytics(request, days: int = 30):
    """Sandbox analytics endpoint.

    Returns sandbox-specific analytics metrics including adoption rate,
    AI edit success rate, mean time to fix, debugger session duration,
    and most-debugged skills.
    """
    workspace = request.workspace
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)

    # 24h and 7d run counts
    since_24h = timezone.now() - timedelta(hours=24)
    since_7d = timezone.now() - timedelta(days=7)
    total_runs_24h = _get_sandbox_runs_qs(workspace, since_24h).count()
    total_runs_7d = _get_sandbox_runs_qs(workspace, since_7d).count()

    # Active skills count
    active_skills_count = (
        SkillExecutionRun.objects.filter(
            workspace=workspace,
            skill__execution_enabled=True,
            created_at__gte=since,
        )
        .values_list("skill_id", flat=True)
        .distinct()
        .count()
    )

    # Adoption rate
    adoption_rate = _compute_adoption_rate(workspace, since)

    # AI edit success rate
    ai_edit_success_rate = _compute_ai_edit_success_rate(workspace, since)

    # Mean time to fix
    mean_time_to_fix_ms = _compute_mean_time_to_fix(workspace, since)

    # Debugger stats
    debugger_sessions_count, mean_debugger_duration_ms = _compute_debugger_stats(workspace, since)

    # Most debugged skills
    most_debugged_skills = _compute_most_debugged_skills(workspace, since)

    # Run status breakdown
    status_counts = (
        _get_sandbox_runs_qs(workspace, since).values("status").annotate(count=Count("id"))
    )
    status_map = {row["status"]: row["count"] for row in status_counts}

    # Daily runs trend
    daily_trend = list(
        _get_sandbox_runs_qs(workspace, since)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(
            runs=Count("id"),
            failures=Count(
                "id",
                filter=Q(
                    status__in=[
                        SkillExecutionRun.StatusChoices.FAILED,
                        SkillExecutionRun.StatusChoices.TIMEOUT,
                    ]
                ),
            ),
        )
        .order_by("date")
    )
    daily_runs_trend = [
        {
            "date": row["date"].isoformat(),
            "runs": row["runs"],
            "failures": row["failures"],
        }
        for row in daily_trend
    ]

    kpis = SandboxAnalyticsKpi(
        adoption_rate=adoption_rate,
        active_skills_count=active_skills_count,
        total_runs_24h=total_runs_24h,
        total_runs_7d=total_runs_7d,
        ai_edit_success_rate=ai_edit_success_rate,
        mean_time_to_fix_ms=mean_time_to_fix_ms,
        debugger_sessions_count=debugger_sessions_count,
        mean_debugger_duration_ms=mean_debugger_duration_ms,
    )

    return SandboxAnalyticsOut(
        kpis=kpis,
        most_debugged_skills=most_debugged_skills,
        run_status_breakdown=RunStatusBreakdown(
            succeeded=status_map.get(SkillExecutionRun.StatusChoices.SUCCEEDED, 0),
            failed=status_map.get(SkillExecutionRun.StatusChoices.FAILED, 0),
            timeout=status_map.get(SkillExecutionRun.StatusChoices.TIMEOUT, 0),
            cancelled=status_map.get(SkillExecutionRun.StatusChoices.CANCELLED, 0),
        ),
        daily_runs_trend=daily_runs_trend,
    )
