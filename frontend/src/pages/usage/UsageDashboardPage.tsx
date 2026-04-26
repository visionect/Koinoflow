import * as React from "react"

import {
  AlertTriangleIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  CheckCircle2Icon,
  ChevronLeftIcon,
  ChevronRightIcon,
  InfoIcon,
  MinusIcon,
  TrendingUpIcon,
  WrenchIcon,
} from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { useUsageAnalytics, useUsageEvents, useUsageSummary } from "@/api/client"
import { ClientBadge } from "@/components/shared/ClientBadge"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { buildWorkspacePath, formatRelativeDate } from "@/lib/format"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { ClientBreakdown, CoverageGap, ToolBreakdown, UsageKpis } from "@/types"

const PERIOD_OPTIONS = [
  { value: 7, label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
]

const CLIENT_CHART_COLORS: Record<string, string> = {
  "Claude Code": "#8b5cf6",
  "Claude.ai": "#7c3aed",
  Cursor: "#2563eb",
  "Windsurf Editor": "#06b6d4",
  "Zed Editor": "#ea580c",
  "GitHub Copilot CLI": "#16a34a",
  Cline: "#eab308",
  ChatGPT: "#059669",
  "Gemini CLI": "#0284c7",
  "OpenAI Codex": "#e11d48",
  "Visual Studio Code": "#2563eb",
  "REST API": "#64748b",
  MCP: "#6366f1",
  "MCP (local)": "#6366f1",
  Web: "#64748b",
  Unknown: "#94a3b8",
}

function getClientColor(clientType: string): string {
  return CLIENT_CHART_COLORS[clientType] ?? "#94a3b8"
}

const PAGE_SIZE = 20

function GlossaryHint({ text }: { text: string }) {
  return (
    <span
      className="inline-flex cursor-help items-center text-muted-foreground/70 hover:text-muted-foreground"
      title={text}
      aria-label={text}
    >
      <InfoIcon className="size-3.5" aria-hidden />
    </span>
  )
}

// ── Coverage Score Widget ──────────────────────────────────────────────

function CoverageScoreWidget({
  consumed,
  published,
  percentage,
  loading,
}: {
  consumed: number
  published: number
  percentage: number
  loading: boolean
}) {
  const chartData = [{ value: percentage, fill: "var(--color-primary)" }]

  return (
    <Card className="flex flex-col items-center justify-center">
      <CardHeader className="pb-2 text-center">
        <CardDescription className="inline-flex items-center justify-center gap-1">
          AI Coverage Score
          <GlossaryHint text="Share of published skills that have been retrieved at least once by an AI client in the selected period." />
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-2 pb-6">
        {loading ? (
          <Skeleton className="size-40 rounded-full" />
        ) : (
          <div className="relative size-40">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                cx="50%"
                cy="50%"
                innerRadius="78%"
                outerRadius="100%"
                startAngle={90}
                endAngle={-270}
                data={chartData}
                barSize={12}
              >
                <RadialBar
                  dataKey="value"
                  cornerRadius={6}
                  background={{ fill: "var(--muted)" }}
                  isAnimationActive={false}
                />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold tracking-tight">{Math.round(percentage)}%</span>
            </div>
          </div>
        )}
        <p className="text-sm text-muted-foreground">
          {consumed} of {published} published skills consumed
        </p>
      </CardContent>
    </Card>
  )
}

// ── Stale but Relied On Widget ─────────────────────────────────────────

function StaleReliedOnWidget({
  items,
  loading,
  workspace,
}: {
  items: Array<{
    skill_slug: string
    skill_title: string
    days_since_review: number
    call_count: number
    owner_email: string | null
    owner_first_name: string | null
  }>
  loading: boolean
  workspace: string | undefined
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start gap-3">
        <div className="rounded-lg bg-amber-500/10 p-2 text-amber-600 dark:text-amber-400">
          <AlertTriangleIcon className="size-5" />
        </div>
        <div className="flex-1">
          <CardTitle className="flex items-center gap-2">
            Stale but Relied On
            <GlossaryHint text="Skills that AI clients retrieve often but haven't been validated recently. Prioritize these for review." />
          </CardTitle>
          <CardDescription>High-traffic skills overdue for validation</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <CheckCircle2Icon className="size-8 text-emerald-500" />
            <p className="font-medium text-emerald-700 dark:text-emerald-400">All clear</p>
            <p className="text-sm text-muted-foreground">No stale high-traffic skills found</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.skill_slug}
                className="flex items-center gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={buildWorkspacePath(workspace, `/skills/${item.skill_slug}`)}
                    className="block truncate font-medium text-foreground hover:text-primary"
                  >
                    {item.skill_title}
                  </Link>
                  {item.owner_first_name && (
                    <span className="text-xs text-muted-foreground">
                      Owner: {item.owner_first_name}
                    </span>
                  )}
                </div>
                <Badge
                  variant="secondary"
                  className="shrink-0 border-transparent bg-amber-500/10 text-amber-700 dark:text-amber-400"
                >
                  {item.days_since_review}d stale
                </Badge>
                <span className="shrink-0 text-sm font-medium tabular-nums text-muted-foreground">
                  {item.call_count.toLocaleString()} calls
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── AI Consumption Trend Widget ────────────────────────────────────────

function ConsumptionTrendWidget({
  data,
  loading,
}: {
  data: Array<{ date: string; count: number }>
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <TrendingUpIcon className="size-5" />
        </div>
        <div className="flex-1">
          <CardTitle className="flex items-center gap-2">
            AI Consumption Trend
            <GlossaryHint text="Count of skill retrievals per day across all AI clients. A retrieval is logged every time a client fetches a skill." />
          </CardTitle>
          <CardDescription>Daily skill retrieval volume</CardDescription>
        </div>
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
            <AreaChart data={data} margin={{ left: -10, right: 8, top: 4 }}>
              <defs>
                <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
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
                labelFormatter={(label) => {
                  const v = typeof label === "string" ? label : String(label ?? "")
                  return new Date(v).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })
                }}
                contentStyle={{
                  borderRadius: "8px",
                  border: "1px solid var(--border)",
                  background: "var(--popover)",
                  color: "var(--popover-foreground)",
                }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="var(--primary)"
                strokeWidth={2}
                fill="url(#trendGradient)"
                dot={{ r: 3, fill: "var(--primary)" }}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

// ── Client Adoption Breakdown Widget ───────────────────────────────────

function ClientAdoptionWidget({ data, loading }: { data: ClientBreakdown[]; loading: boolean }) {
  const totalCalls = data.reduce((sum, d) => sum + d.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Client Adoption
          <GlossaryHint text="Breakdown of retrievals by AI client (Claude, Cursor, custom MCP, …) for the selected period." />
        </CardTitle>
        <CardDescription>AI tool usage across your organization</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="mx-auto h-[200px] w-[200px] rounded-full" />
        ) : data.length === 0 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            No client data yet
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <div className="relative h-[200px] w-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="count"
                    nameKey="client_type"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {data.map((entry) => (
                      <Cell key={entry.client_type} fill={getClientColor(entry.client_type)} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid var(--border)",
                      background: "var(--popover)",
                      color: "var(--popover-foreground)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold">{totalCalls.toLocaleString()}</span>
                <span className="text-xs text-muted-foreground">total calls</span>
              </div>
            </div>
            <div className="w-full space-y-2">
              {data.map((entry) => (
                <div key={entry.client_type} className="flex items-center gap-3">
                  <div
                    className="size-3 shrink-0 rounded-full"
                    style={{ backgroundColor: getClientColor(entry.client_type) }}
                  />
                  <ClientBadge clientType={entry.client_type} />
                  <span className="ml-auto text-sm tabular-nums text-muted-foreground">
                    {entry.count.toLocaleString()}
                  </span>
                  <span className="w-12 text-right text-sm tabular-nums text-muted-foreground">
                    {entry.percentage}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Top Consumed Skills Widget ──────────────────────────────────────

function TopSkillsWidget({
  data,
  loading,
  workspace,
}: {
  data: Array<{ slug: string; title: string; calls: number }>
  loading: boolean
  workspace: string | undefined
}) {
  const navigate = useNavigate()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Top Consumed Skills
          <GlossaryHint text="Skills with the most AI retrievals in the selected period. Click a bar label to open the skill." />
        </CardTitle>
        <CardDescription>Most retrieved skills by AI clients</CardDescription>
      </CardHeader>
      <CardContent className="h-[340px]">
        {loading ? (
          <Skeleton className="h-full w-full" />
        ) : data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No skill usage yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 12, right: 12 }}>
              <YAxis
                dataKey="title"
                type="category"
                width={160}
                tick={(props) => {
                  const { x, y, payload } = props as {
                    x: number | string
                    y: number | string
                    payload: { value: string; index: number }
                  }
                  const item = data[payload.index]
                  const label =
                    payload.value.length > 22 ? `${payload.value.slice(0, 22)}...` : payload.value
                  return (
                    <text
                      x={x}
                      y={y}
                      dy={4}
                      textAnchor="end"
                      fill="currentColor"
                      className="cursor-pointer text-xs hover:underline"
                      role="link"
                      tabIndex={0}
                      onClick={() =>
                        item?.slug
                          ? navigate(buildWorkspacePath(workspace, `/skills/${item.slug}`))
                          : undefined
                      }
                      onKeyDown={(event) => {
                        if ((event.key === "Enter" || event.key === " ") && item?.slug) {
                          event.preventDefault()
                          navigate(buildWorkspacePath(workspace, `/skills/${item.slug}`))
                        }
                      }}
                    >
                      {label}
                    </text>
                  )
                }}
              />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  borderRadius: "8px",
                  border: "1px solid var(--border)",
                  background: "var(--popover)",
                  color: "var(--popover-foreground)",
                }}
              />
              <Bar dataKey="calls" radius={[0, 6, 6, 0]} fill="var(--primary)" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

// ── KPI Strip Widget ──────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sublabel,
  trend,
  hint,
  loading,
}: {
  label: string
  value: string
  sublabel?: React.ReactNode
  trend?: { pct: number | null; direction: "up" | "down" | "flat" }
  hint?: string
  loading: boolean
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-5">
        <div className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground">
          <span>{label}</span>
          {hint && <GlossaryHint text={hint} />}
        </div>
        {loading ? (
          <Skeleton className="mt-1 h-8 w-20" />
        ) : (
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold tabular-nums">{value}</span>
            {trend && (
              <span
                className={`inline-flex items-center gap-0.5 text-xs font-medium ${
                  trend.direction === "up"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : trend.direction === "down"
                      ? "text-rose-600 dark:text-rose-400"
                      : "text-muted-foreground"
                }`}
              >
                {trend.direction === "up" && <ArrowUpIcon className="size-3" />}
                {trend.direction === "down" && <ArrowDownIcon className="size-3" />}
                {trend.direction === "flat" && <MinusIcon className="size-3" />}
                {trend.pct === null ? "—" : `${Math.abs(trend.pct).toFixed(0)}%`}
              </span>
            )}
          </div>
        )}
        {sublabel && !loading && <span className="text-xs text-muted-foreground">{sublabel}</span>}
      </CardContent>
    </Card>
  )
}

function KpiStripWidget({ kpis, loading }: { kpis: UsageKpis | undefined; loading: boolean }) {
  const current = kpis?.total_calls ?? 0
  const previous = kpis?.total_calls_previous ?? 0
  let deltaPct: number | null
  let direction: "up" | "down" | "flat"
  if (previous === 0) {
    deltaPct = current === 0 ? 0 : null
    direction = current === 0 ? "flat" : "up"
  } else {
    deltaPct = ((current - previous) / previous) * 100
    direction = deltaPct > 0.5 ? "up" : deltaPct < -0.5 ? "down" : "flat"
  }

  const peakSublabel = kpis?.peak_day_date
    ? new Date(kpis.peak_day_date).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      })
    : "No activity yet"

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="Total retrievals"
        value={current.toLocaleString()}
        trend={{ pct: deltaPct, direction }}
        sublabel="vs previous period"
        hint="All AI retrievals in the selected period, compared against the equal-length prior period."
        loading={loading}
      />
      <KpiCard
        label="Active AI clients"
        value={(kpis?.active_clients ?? 0).toLocaleString()}
        sublabel="Distinct client identifiers"
        hint="Number of distinct client_id values observed — each usually represents one machine or agent instance."
        loading={loading}
      />
      <KpiCard
        label="Skills touched"
        value={(kpis?.skills_touched ?? 0).toLocaleString()}
        sublabel="Retrieved at least once"
        hint="Count of distinct skills that have been retrieved in the selected period."
        loading={loading}
      />
      <KpiCard
        label="Peak day"
        value={(kpis?.peak_day_count ?? 0).toLocaleString()}
        sublabel={peakSublabel}
        hint="The single busiest day in the selected period, by retrieval count."
        loading={loading}
      />
    </div>
  )
}

// ── Coverage Gap Widget ───────────────────────────────────────────────

function CoverageGapWidget({
  items,
  loading,
  workspace,
}: {
  items: CoverageGap[]
  loading: boolean
  workspace: string | undefined
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Coverage Gap
          <GlossaryHint text="Published skills that have not been retrieved by any AI client in the selected period. Candidates for promotion, rewriting, or retirement." />
        </CardTitle>
        <CardDescription>Published skills with zero AI retrievals</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <CheckCircle2Icon className="size-8 text-emerald-500" />
            <p className="font-medium text-emerald-700 dark:text-emerald-400">Full coverage</p>
            <p className="text-sm text-muted-foreground">
              Every published skill has been retrieved at least once
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.skill_slug}
                className="flex items-center gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={buildWorkspacePath(workspace, `/skills/${item.skill_slug}`)}
                    className="block truncate font-medium text-foreground hover:text-primary"
                  >
                    {item.skill_title}
                  </Link>
                  {item.owner_first_name && (
                    <span className="text-xs text-muted-foreground">
                      Owner: {item.owner_first_name}
                    </span>
                  )}
                </div>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {item.days_since_published}d since publish
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Tool-call Mix Widget ──────────────────────────────────────────────

const TOOL_COLORS = [
  "#6366f1",
  "#06b6d4",
  "#16a34a",
  "#eab308",
  "#ea580c",
  "#e11d48",
  "#8b5cf6",
  "#64748b",
]

function ToolMixWidget({ data, loading }: { data: ToolBreakdown[]; loading: boolean }) {
  const totalCalls = data.reduce((sum, d) => sum + d.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <WrenchIcon className="size-4 text-muted-foreground" />
          Tool-call Mix
          <GlossaryHint text="Breakdown of retrievals by the specific tool invoked (e.g. get_skill, search_skills). REST means direct HTTP calls without MCP tool routing." />
        </CardTitle>
        <CardDescription>How AI clients reach your skills</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className="flex h-[180px] items-center justify-center text-sm text-muted-foreground">
            No tool data yet
          </div>
        ) : (
          <div className="space-y-3">
            {data.map((entry, i) => {
              const color = TOOL_COLORS[i % TOOL_COLORS.length]
              const widthPct = totalCalls ? (entry.count / totalCalls) * 100 : 0
              return (
                <div key={entry.tool_name} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 truncate">
                      <span
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: color }}
                      />
                      <span className="truncate font-mono text-xs">{entry.tool_name}</span>
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {entry.count.toLocaleString()}{" "}
                      <span className="text-xs">({entry.percentage}%)</span>
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${Math.max(widthPct, 2)}%`, backgroundColor: color }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Activity Log Tab ───────────────────────────────────────────────────

const ALL_FILTER = "__all__"

function ActivityLogTab({ period, workspace }: { period: number; workspace: string | undefined }) {
  const [page, setPage] = React.useState(0)
  const [skillFilter, setSkillFilter] = React.useState<string>(ALL_FILTER)
  const [clientFilter, setClientFilter] = React.useState<string>(ALL_FILTER)

  const eventsQuery = useUsageEvents({
    days: period,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    skill: skillFilter !== ALL_FILTER ? skillFilter : undefined,
    client_type: clientFilter !== ALL_FILTER ? clientFilter : undefined,
  })

  const summaryQuery = useUsageSummary(period)

  React.useEffect(() => {
    setPage(0)
  }, [skillFilter, clientFilter, period])

  const events = eventsQuery.data?.items ?? []
  const totalCount = eventsQuery.data?.count ?? 0
  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  const skillSlugs = React.useMemo(() => {
    if (!summaryQuery.data) return []
    return summaryQuery.data.map((s) => ({
      slug: s.skill_slug,
      title: s.skill_title,
    }))
  }, [summaryQuery.data])

  const clientTypes = React.useMemo(() => {
    if (!summaryQuery.data) return []
    const types = new Set<string>()
    for (const s of summaryQuery.data) {
      for (const ct of Object.keys(s.client_type_breakdown)) {
        types.add(ct)
      }
    }
    return Array.from(types).sort()
  }, [summaryQuery.data])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <Select value={skillFilter} onValueChange={setSkillFilter}>
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="All skills" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_FILTER}>All skills</SelectItem>
            {skillSlugs.map((p) => (
              <SelectItem key={p.slug} value={p.slug}>
                {p.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={clientFilter} onValueChange={setClientFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All clients" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_FILTER}>All clients</SelectItem>
            {clientTypes.map((ct) => (
              <SelectItem key={ct} value={ct}>
                {ct}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {(skillFilter !== ALL_FILTER || clientFilter !== ALL_FILTER) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSkillFilter(ALL_FILTER)
              setClientFilter(ALL_FILTER)
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          {eventsQuery.isLoading ? (
            <div className="space-y-2 p-6">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : events.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No events match the current filters
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Skill</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Tool</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event) => (
                  <TableRow key={event.id}>
                    <TableCell>
                      <Link
                        className="font-medium text-foreground hover:text-primary"
                        to={buildWorkspacePath(workspace, `/skills/${event.skill_slug}`)}
                      >
                        {event.skill_title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-0.5">
                        <ClientBadge clientType={event.client_type} />
                        {event.client_id && event.client_id !== "unknown" && (
                          <span className="text-xs text-muted-foreground">{event.client_id}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs text-muted-foreground">
                        {event.tool_name || "\u2014"}
                      </span>
                    </TableCell>
                    <TableCell>v{event.version_number}</TableCell>
                    <TableCell>{formatRelativeDate(event.called_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {page * PAGE_SIZE + 1}&ndash;
            {Math.min((page + 1) * PAGE_SIZE, totalCount)} of {totalCount.toLocaleString()} events
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeftIcon className="mr-1 size-4" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
              <ChevronRightIcon className="ml-1 size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────

export function UsageDashboardPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const [period, setPeriod] = React.useState(30)

  const analyticsQuery = useUsageAnalytics(period)
  const summaryQuery = useUsageSummary(period)

  if (analyticsQuery.isError) {
    return (
      <ErrorState
        message={
          analyticsQuery.error instanceof Error
            ? analyticsQuery.error.message
            : "Unable to load analytics"
        }
        onRetry={() => {
          void analyticsQuery.refetch()
        }}
      />
    )
  }

  const analytics = analyticsQuery.data
  const topSkills = (summaryQuery.data ?? []).slice(0, 10).map((row) => ({
    slug: row.skill_slug,
    title: row.skill_title,
    calls: row.total_calls,
  }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Understand how AI clients consume your operational knowledge."
        action={
          <Select value={String(period)} onValueChange={(value) => setPeriod(Number(value))}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Select a period" />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      <Tabs defaultValue="analytics">
        <TabsList>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="activity">Activity Log</TabsTrigger>
        </TabsList>

        <TabsContent value="analytics" className="space-y-6 pt-4">
          {!analyticsQuery.isLoading &&
          analytics &&
          analytics.coverage.published_count === 0 &&
          analytics.daily_trend.length === 0 ? (
            <EmptyState
              title="No usage data yet"
              description="Publish a skill and connect an AI client to start collecting analytics."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button asChild>
                    <Link to={buildWorkspacePath(workspace, "/skills")}>Go to skills</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to={buildWorkspacePath(workspace, "/settings/mcp")}>
                      Connect MCP client
                    </Link>
                  </Button>
                </div>
              }
            />
          ) : !analyticsQuery.isLoading &&
            analytics &&
            analytics.coverage.published_count > 0 &&
            analytics.daily_trend.every((day) => day.count === 0) ? (
            <EmptyState
              title="No AI traffic yet"
              description="You have published skills, but no AI client has retrieved them in this period. Connect an MCP client to start measuring adoption."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button asChild>
                    <Link to={buildWorkspacePath(workspace, "/settings/mcp")}>
                      Connect MCP client
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to={buildWorkspacePath(workspace, "/settings/keys")}>Create API key</Link>
                  </Button>
                </div>
              }
            />
          ) : (
            <>
              <KpiStripWidget kpis={analytics?.kpis} loading={analyticsQuery.isLoading} />

              <div className="grid gap-4 md:grid-cols-[1fr_2fr]">
                <CoverageScoreWidget
                  consumed={analytics?.coverage.consumed_count ?? 0}
                  published={analytics?.coverage.published_count ?? 0}
                  percentage={analytics?.coverage.percentage ?? 0}
                  loading={analyticsQuery.isLoading}
                />
                <StaleReliedOnWidget
                  items={analytics?.stale_but_relied_on ?? []}
                  loading={analyticsQuery.isLoading}
                  workspace={workspace}
                />
              </div>

              <ConsumptionTrendWidget
                data={analytics?.daily_trend ?? []}
                loading={analyticsQuery.isLoading}
              />

              <div className="grid gap-4 xl:grid-cols-2">
                <ClientAdoptionWidget
                  data={analytics?.client_breakdown ?? []}
                  loading={analyticsQuery.isLoading}
                />
                <ToolMixWidget
                  data={analytics?.tool_breakdown ?? []}
                  loading={analyticsQuery.isLoading}
                />
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <TopSkillsWidget
                  data={topSkills}
                  loading={summaryQuery.isLoading}
                  workspace={workspace}
                />
                <CoverageGapWidget
                  items={analytics?.coverage_gap ?? []}
                  loading={analyticsQuery.isLoading}
                  workspace={workspace}
                />
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="activity" className="pt-4">
          <ActivityLogTab period={period} workspace={workspace} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
