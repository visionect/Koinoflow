# Implementation Plan

## Overview
Add a "Sandbox" tab to the existing Usage Analytics dashboard that displays sandbox-specific analytics: adoption rate, AI edit success rate, mean time to fix, debugger session duration, and most-debugged skills. This requires new backend API endpoints to aggregate sandbox execution data, new frontend types, a new analytics widget components, and integration into the existing UsageDashboardPage tabs.

The existing analytics page (`UsageDashboardPage`) already uses a `Tabs` component with "Analytics" and "Activity Log" tabs. We will add a "Sandbox" tab that queries dedicated sandbox analytics endpoints. The sandbox execution data already exists in `SkillExecutionRun` model but is not exposed through analytics aggregations.

## Types

### New Frontend Types (frontend/src/types/index.ts)

Add the following interfaces for sandbox analytics:

```typescript
export interface SandboxAnalyticsKpi {
  adoption_rate: number          // % of workspace users who've used sandbox
  active_skills_count: number    // skills with at least one sandbox run
  total_runs_24h: number
  total_runs_7d: number
  ai_edit_success_rate: number   // % of AI-edited skills that succeed on rerun
  mean_time_to_fix_ms: number | null  // mean time from failure → AI edit → success
  debugger_sessions_count: number
  mean_debugger_duration_ms: number | null  // mean debugger session duration
}

export interface MostDebuggedSkill {
  skill_slug: string
  skill_title: string
  debugger_session_count: number
  last_debugged_at: string | null
  failure_count: number
}

export interface SandboxAnalyticsOut {
  kpis: SandboxAnalyticsKpi
  most_debugged_skills: MostDebuggedSkill[]
  run_status_breakdown: {
    succeeded: number
    failed: number
    timeout: number
    cancelled: number
  }
  daily_runs_trend: Array<{ date: string; runs: number; failures: number }>
}
```

### New Backend Schema (backend/apps/skills/api.py)

Mirror the frontend types as Django Ninja `Schema` classes in the same file where `SandboxOverviewOut` already exists.

## Files

### New Files

1. **`backend/apps/skills/sandbox_analytics.py`** — Dedicated module for sandbox analytics aggregation logic. Contains the query functions and view function for the sandbox analytics endpoint. Keeps `api.py` from growing further.

2. **`frontend/src/components/analytics/SandboxAnalyticsWidgets.tsx`** — React components for sandbox analytics visualization: KPI strip, AI edit success rate gauge, most-debugged skills list, daily runs trend chart.

### Modified Files

1. **`backend/apps/skills/api.py`** — Register the new router from `sandbox_analytics.py` at the end of the file (after existing sandbox endpoints). Add URL prefix `/sandbox/analytics`.

2. **`backend/apps/skills/apps.py`** — No changes needed (router registration is in api.py).

3. **`frontend/src/types/index.ts`** — Add `SandboxAnalyticsKpi`, `MostDebuggedSkill`, `SandboxAnalyticsOut` interfaces.

4. **`frontend/src/api/client.ts`** — Add `useSandboxAnalytics` React Query hook. Add query key `sandbox.analytics`.

5. **`frontend/src/pages/usage/UsageDashboardPage.tsx`** — Add "Sandbox" tab to the existing `Tabs` component. Import and render `SandboxAnalyticsContent` component in the new tab's `TabsContent`.

6. **`frontend/src/routes.tsx`** — No changes needed (sandbox analytics lives under the existing usage route).

## Functions

### Backend Functions

1. **`sandbox_analytics(request)`** — `GET /api/v1/sandbox/analytics?days=30` in `backend/apps/skills/sandbox_analytics.py`
   - Filters `SkillExecutionRun` to sandbox runs only (runs where the skill has `execution_enabled=True` and the run was initiated from the sandbox UI context)
   - Computes all KPIs:
     - **Adoption rate**: Count distinct users who ran at least one sandbox skill in period / total workspace users
     - **AI edit success rate**: Count runs with status "succeeded" where the run's `inputs` contain an `ai_edited` flag (set when a skill is re-run after AI edit) / total runs that were preceded by a failure
     - **Mean time to fix**: For each failure→AI edit→success chain, compute time from failure's `finished_at` to successful run's `started_at`, then average
     - **Debugger session duration**: Derived from runs where `inputs.debugger_session=true`, compute `finished_at - started_at`
     - **Most-debugged skills**: Group debugger sessions by skill, count sessions per skill, return top 10
   - Returns `SandboxAnalyticsOut`

2. **`_compute_adoption_rate(workspace, since)`** — Helper that counts distinct sandbox users vs total workspace members.

3. **`_compute_ai_edit_success_rate(workspace, since)`** — Helper that identifies AI-edited runs and their outcomes.

4. **`_compute_mean_time_to_fix(workspace, since)`** — Helper that chains failure→edit→success runs and computes durations.

5. **`_compute_debugger_stats(workspace, since)`** — Helper that filters debugger sessions and computes duration stats.

6. **`_compute_most_debugged_skills(workspace, since, limit=10)`** — Helper that groups debugger sessions by skill.

### Frontend Functions

1. **`SandboxAnalyticsContent({ period, workspace })`** — Main sandbox analytics panel component. Fetches data via `useSandboxAnalytics`, renders KPI strip and charts.

2. **`SandboxKpiStrip({ kpis, loading })`** — Horizontal strip of sandbox KPI cards (adoption rate, AI edit success rate, mean time to fix, debugger sessions).

3. **`AiEditSuccessWidget({ kpis, loading })`** — Gauge/progress bar showing AI edit success rate.

4. **`MostDebuggedSkillsWidget({ skills, loading, workspace })`** — List of most-debugged skills with session counts.

5. **`DailyRunsTrendWidget({ data, loading })`** — Area chart showing daily sandbox runs and failures over time.

### Frontend API Hook

1. **`useSandboxAnalytics(days?: number)`** — React Query hook in `frontend/src/api/client.ts` that calls `/sandbox/analytics?days=X`.

## Classes

No new classes needed. Existing patterns reuse:
- `SkillExecutionRun` model for execution data
- `Tabs`/`TabsContent`/`TabsTrigger` from shadcn/ui for tab navigation
- Card-based widget pattern already established in `UsageDashboardPage.tsx`

## Dependencies

### Backend
- No new Python packages needed. Uses existing Django ORM annotations (`Count`, `Avg`, `TruncDate`, `Cast`, `ExpressionWrapper`, `F`) already imported in `api.py` and `usage/api.py`.
- May need `django.db.models.ExpressionWrapper` and `django.db.models.fields.DurationField` for mean time to fix computation (already available in Django core).

### Frontend
- No new npm packages. Uses existing `recharts` (Area, AreaChart, Bar, BarChart) already imported in `UsageDashboardPage.tsx`.
- Uses existing `lucide-react` icons already available.

## Testing

### Backend Tests (`backend/apps/skills/tests/test_sandbox_analytics.py`)

1. Test `sandbox_analytics` endpoint returns correct structure with empty data.
2. Test with sandbox runs: verify adoption rate calculation.
3. Test AI edit success rate with mixed success/failure runs.
4. Test mean time to fix with failure→edit→success chains.
5. Test debugger session duration aggregation.
6. Test most-debugged skills ranking.
7. Test date range filtering (7d, 30d, 90d).
8. Test permission enforcement (workspace-scoped data).

### Frontend Tests

1. Test `SandboxAnalyticsContent` renders with loading state.
2. Test `SandboxAnalyticsContent` renders with data.
3. Test `SandboxKpiStrip` displays correct values.
4. Test `MostDebuggedSkillsWidget` renders skill list with links.
5. Test period selector changes analytics data.

## Implementation Order

1. **Backend: Create `sandbox_analytics.py`** — Add schema classes and the `sandbox_analytics` view function with all helper functions.
2. **Backend: Register router in `api.py`** — Import and include the sandbox analytics router.
3. **Frontend: Add types** — Add `SandboxAnalyticsKpi`, `MostDebuggedSkill`, `SandboxAnalyticsOut` to `frontend/src/types/index.ts`.
4. **Frontend: Add API hook** — Add `useSandboxAnalytics` hook to `frontend/src/api/client.ts`.
5. **Frontend: Create widget components** — Create `SandboxAnalyticsWidgets.tsx` with all visualization components.
6. **Frontend: Add sandbox tab to UsageDashboardPage** — Add "Sandbox" tab and integrate widget components.
7. **Backend: Add tests** — Write comprehensive backend tests.
8. **Frontend: Add tests** — Write frontend component tests.