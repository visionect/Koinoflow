import * as React from "react"

import {
  ActivityIcon,
  BugIcon,
  ClockIcon,
  FlameIcon,
  GaugeIcon,
  RocketIcon,
  TargetIcon,
  TrendingDownIcon,
  TrendingUpIcon,
  UsersIcon,
  WrenchIcon,
} from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type {
  DailyRunTrend,
  MostDebuggedSkill,
  RunStatusBreakdown,
  SandboxAnalyticsKpi,
} from "@/types"

// ── Helpers ──────────────────────────────────────────────────────────────

function formatMs(ms: number | null): string {
  if (ms === null || ms < 0) return "—"
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

// ── KPI Strip Widget ────────────────────────────────────────────────────

function SandboxKpiCard({
  label,
  value,
  sublabel,
  icon: Icon,
  loading,
  color = "text-primary",
}: {
  label: string
  value: string
  sublabel?: string
  icon: React.ComponentType<{ className?: string }>
  loading: boolean
  color?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-5">
        <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
          <Icon className="size-3.5" />
          <span>{label}</span>
        </div>
        {loading ? (
          <Skeleton className="mt-1 h-8 w-20" />
        ) : (
          <span className={`text-2xl font-bold tabular-nums ${color}`}>{value}</span>
        )}
        {sublabel && !loading && (
          <span className="text-xs text-muted-foreground">{sublabel}</span>
        )}
      </CardContent>
    </Card>
  )
}

function SandboxKpiStrip({
  kpis,
  loading,
}: {
  kpis: SandboxAnalyticsKpi | undefined
  loading: boolean
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <SandboxKpiCard
        label="Adoption Rate"
        value={kpis ? formatPercent(kpis.adoption_rate) : "—"}
        sublabel="Users who ran at least one sandbox"
        icon={UsersIcon}
        loading={loading}
        color="text-emerald-600 dark:text-emerald-400"
      />
      <SandboxKpiCard
        label="Active Skills"
        value={kpis ? String(kpis.active_skills_count) : "—"}
        sublabel="Skills with at least one run"
        icon={WrenchIcon}
        loading={loading}
      />
      <SandboxKpiCard
        label="AI Edit Success Rate"
        value={kpis ? formatPercent(kpis.ai_edit_success_rate) : "—"}
        sublabel="Failure → edit → success chain"
        icon={TargetIcon}
        loading={loading}
        color="text-blue-600 dark:text-blue-400"
      />
      <SandboxKpiCard
        label="Mean Time to Fix"
        value={kpis ? formatMs(kpis.mean_time_to_fix_ms) : "—"}
        sublabel="From failure to successful re-run"
        icon={RocketIcon}
        loading={loading}
        color="text-amber-600 dark:text-amber-400"
      />
      <SandboxKpiCard
        label="Debugger Sessions"
        value={kpis ? String(kpis.debugger_sessions_count) : "—"}
        sublabel="Runs with AI edit in the last 24h"
        icon={BugIcon}
        loading={loading}
      />
      <SandboxKpiCard
        label="Mean Debugger Duration"
        value={kpis ? formatMs(kpis.mean_debugger_duration_ms) : "—"}
        sublabel="Average session length"
        icon={ClockIcon}
        loading={loading}
      />
      <SandboxKpiCard
        label="Runs (24h)"
        value={kpis ? String(kpis.total_runs_24h) : "—"}
        sublabel="Total sandbox runs in last 24 hours"
        icon={ActivityIcon}
        loading={loading}
      />
      <SandboxKpiCard
        label="Runs (7d)"
        value={kpis ? String(kpis.total_runs_7d) : "—"}
        sublabel="Total sandbox runs in last 7 days"
        icon={TrendingUpIcon}
        loading={loading}
      />
    </div>
  )
}

// ── Most Debugged Skills Widget ─────────────────────────────────────────

function MostDebuggedSkillsWidget({
  items,
  loading,
}: {
  items: MostDebuggedSkill[]
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start gap-3">
        <div className="rounded-lg bg-orange-500/10 p-2 text-orange-600 dark:text-orange-400">
          <FlameIcon className="size-5" />
        </div>
        <div className="flex-1">
          <CardTitle className="flex items-center gap-2">
            Most-Debugged Skills
            <span className="text-xs font-normal text-muted-foreground">
              (last 24 hours)
            </span>
          </CardTitle>
          <CardDescription>Skills with the most AI debugging sessions</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <BugIcon className="size-8 text-muted-foreground/50" />
            <p className="font-medium text-muted-foreground">No debugging activity</p>
            <p className="text-sm text-muted-foreground">
              No AI debugging sessions detected in the last 24 hours
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item, index) => (
              <div
                key={item.skill_slug}
                className="flex items-center gap-3 rounded-lg border p-3"
              >
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-foreground">{item.skill_title}</p>
                  <p className="text-xs text-muted-foreground font-mono">{item.skill_slug}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="secondary"
                    className="shrink-0 border-transparent bg-orange-500/10 text-orange-700 dark:text-orange-400"
                  >
                    <BugIcon className="mr-1 size-3" />
                    {item.debugger_session_count}
                  </Badge>
                  {item.failure_count > 0 && (
                    <Badge
                      variant="secondary"
                      className="shrink-0 border-transparent bg-red-500/10 text-red-700 dark:text-red-400"
                    >
                      <TrendingDownIcon className="mr-1 size-3" />
                      {item.failure_count}
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Run Status Breakdown Widget ─────────────────────────────────────────

function RunStatusBreakdownWidget({
  breakdown,
  loading,
}: {
  breakdown: RunStatusBreakdown | undefined
  loading: boolean
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Run Status Breakdown</CardTitle>
          <CardDescription>Distribution of sandbox run outcomes</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[200px] w-full" />
        </CardContent>
      </Card>
    )
  }

  const total =
    (breakdown?.succeeded ?? 0) +
    (breakdown?.failed ?? 0) +
    (breakdown?.timeout ?? 0) +
    (breakdown?.cancelled ?? 0)

  if (total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Run Status Breakdown</CardTitle>
          <CardDescription>Distribution of sandbox run outcomes</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
            No runs in this period
          </div>
        </CardContent>
      </Card>
    )
  }

  const safeBreakdown: RunStatusBreakdown = breakdown ?? {
    succeeded: 0,
    failed: 0,
    timeout: 0,
    cancelled: 0,
  }
  const data = [
    { name: "Succeeded", value: safeBreakdown.succeeded, color: "var(--success)" },
    { name: "Failed", value: safeBreakdown.failed, color: "var(--destructive)" },
    { name: "Timeout", value: safeBreakdown.timeout, color: "#eab308" },
    { name: "Cancelled", value: safeBreakdown.cancelled, color: "#64748b" },
  ].filter((d) => d.value > 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Run Status Breakdown</CardTitle>
        <CardDescription>Distribution of sandbox run outcomes</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {data.map((entry) => {
            const pct = total > 0 ? (entry.value / total) * 100 : 0
            return (
              <div key={entry.name} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: entry.color }}
                    />
                    <span className="font-medium">{entry.name}</span>
                  </span>
                  <span className="tabular-nums text-muted-foreground">
                    {entry.value.toLocaleString()} ({pct.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: entry.color }}
                  />
                </div>
              </div>
            )
          })}
          <div className="pt-2 text-center text-sm text-muted-foreground">
            Total: {total.toLocaleString()} runs
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Daily Runs Trend Widget ─────────────────────────────────────────────

function DailyRunsTrendWidget({
  data,
  loading,
}: {
  data: DailyRunTrend[]
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GaugeIcon className="size-4 text-muted-foreground" />
          Daily Run Volume
        </CardTitle>
        <CardDescription>Sandbox execution activity over time</CardDescription>
      </CardHeader>
      <CardContent className="h-[260px]">
        {loading ? (
          <Skeleton className="h-full w-full" />
        ) : data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No activity in this period
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ left: -10, right: 8, top: 4 }}>
              <defs>
                <linearGradient id="runBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => {
                  const d = new Date(v)
                  return `${d.getMonth() + 1}/${d.getDate()}`
                }}
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  borderRadius: "8px",
                  border: "1px solid var(--border)",
                  background: "var(--popover)",
                  color: "var(--popover-foreground)",
                }}
                formatter={(value: unknown) => [
                  typeof value === "number" ? value.toLocaleString() : String(value ?? 0),
                  "Runs",
                ]}
              />
              <Bar
                dataKey="runs"
                fill="url(#runBarGradient)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

export {
  SandboxKpiStrip,
  MostDebuggedSkillsWidget,
  RunStatusBreakdownWidget,
  DailyRunsTrendWidget,
}