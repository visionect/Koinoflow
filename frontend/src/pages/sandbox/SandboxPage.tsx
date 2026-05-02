import * as React from "react"
import {
  AlertTriangleIcon,
  CalendarIcon,
  CheckIcon,
  ExternalLinkIcon,
  PlayIcon,
  SearchIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
  XIcon,
} from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { useSandboxOverview, type SkillSystemKind } from "@/api/client"
import { ExecutionDebugger } from "@/components/skills/execution/ExecutionDebugger"
import { RunStatusDot } from "@/components/skills/execution/RunStatusBadge"
import {
  formatRunDuration,
  runStatusLabel,
} from "@/components/skills/execution/runStatus"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath, formatRelativeDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { SandboxSkillSummary } from "@/types"

type DebuggerTarget = {
  skillSlug: string
  skillTitle: string
  systemKind?: SkillSystemKind
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  team_manager: "Team manager",
  member: "Member",
  viewer: "Viewer",
}

const TIME_PERIODS = [
  { value: 1, label: "24h" },
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
] as const

export function SandboxPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const overviewQuery = useSandboxOverview()
  const { isAdmin } = useAuth()
  const [query, setQuery] = React.useState("")
  const [statusFilter, setStatusFilter] = React.useState<"all" | "failing" | "active" | "untested">(
    "all",
  )
  const [timePeriod, setTimePeriod] = React.useState(1)
  const [target, setTarget] = React.useState<DebuggerTarget | null>(null)
  const searchInputRef = React.useRef<HTMLInputElement>(null)
  const activeFilterRef = React.useRef<HTMLButtonElement>(null)

  const overview = overviewQuery.data
  const skills = React.useMemo(() => overview?.skills ?? [], [overview?.skills])

  // Keyboard shortcut: Ctrl/Cmd+K to focus search
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
      if (e.key === "Escape") {
        searchInputRef.current?.blur()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  const filtered = React.useMemo(() => {
    let items = skills
    const q = query.trim().toLowerCase()
    if (q) {
      items = items.filter(
        (s) =>
          s.title.toLowerCase().includes(q) ||
          s.slug.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.team_name.toLowerCase().includes(q),
      )
    }
    if (statusFilter === "failing") {
      items = items.filter((s) => s.failures_24h > 0)
    } else if (statusFilter === "active") {
      items = items.filter((s) => {
        const status = s.latest_run?.status
        return status === "queued" || status === "running" || status === "pending_approval"
      })
    } else if (statusFilter === "untested") {
      items = items.filter((s) => s.latest_run === null)
    }
    return items
  }, [skills, query, statusFilter])

  const totalRuns = skills.reduce((acc, s) => acc + (s.runs_24h ?? 0), 0)
  const totalFailures = skills.reduce((acc, s) => acc + (s.failures_24h ?? 0), 0)

  const hasActiveFilter = statusFilter !== "all" || query !== ""

  return (
    <div className="space-y-4 sm:space-y-6">
      <PageHeader
        title="Sandbox"
        description="Test executable skills in an isolated runner. Inspect logs, patch code in place with AI, and re-run without leaving the page."
        action={
          isAdmin ? (
            <Button asChild variant="outline" size="sm" className="gap-2">
              <Link to={buildWorkspacePath(workspace, "/settings")}>
                <SlidersHorizontalIcon className="size-4" />
                Sandbox access settings
              </Link>
            </Button>
          ) : undefined
        }
      />

      {overview && !overview.can_use_sandbox ? (
        <div
          className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-900 dark:text-amber-100"
          role="alert"
          aria-live="polite"
        >
          <AlertTriangleIcon className="mt-0.5 size-5 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">Sandbox access is restricted</p>
            <p className="text-xs">
              Your workspace requires the{" "}
              <strong>{ROLE_LABELS[overview.workspace_min_role] ?? overview.workspace_min_role}</strong>{" "}
              role to use the sandbox. Your role:{" "}
              <strong>
                {overview.user_role ? (ROLE_LABELS[overview.user_role] ?? overview.user_role) : "—"}
              </strong>
              . Ask an admin to lower the threshold or grant you access.
            </p>
          </div>
        </div>
      ) : null}

      {/* Summary Stats - synced with analytics naming */}
      <div className="grid gap-2 sm:grid-cols-3">
        <SummaryStat
          label="Executable skills"
          value={skills.length}
          hint="Skills with sandbox enabled"
          ariaLabel={`${skills.length} skills available in the sandbox`}
        />
        <SummaryStat
          label="Total runs"
          value={totalRuns}
          hint={`${skills.filter((s) => (s.runs_24h ?? 0) > 0).length} skills exercised in the last 24 hours`}
          ariaLabel={`${totalRuns} total runs in the last 24 hours`}
        />
        <SummaryStat
          label="Failures"
          value={totalFailures}
          tone={totalFailures > 0 ? "danger" : "success"}
          hint={
            totalFailures > 0
              ? `${skills.filter((s) => s.failures_24h > 0).length} skills with errors`
              : "All recent runs healthy"
          }
          ariaLabel={`${totalFailures} failures in the last 24 hours`}
        />
      </div>

      {/* Controls: Search + Filters + Time Period */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-0">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            ref={searchInputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by skill, team, or description (⌘K)"
            className="h-9 pl-9"
            aria-label="Search sandbox skills"
            role="searchbox"
          />
          {query && (
            <button
              type="button"
              className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setQuery("")}
              aria-label="Clear search"
            >
              <XIcon className="size-3" />
            </button>
          )}
        </div>

        {/* Time Period Selector */}
        <div className="flex items-center gap-2 shrink-0">
          <CalendarIcon className="size-3.5 text-muted-foreground hidden sm:block" aria-hidden />
          <div
            className="inline-flex rounded-md border border-border bg-background p-0.5"
            role="radiogroup"
            aria-label="Time period"
          >
            {TIME_PERIODS.map((period) => (
              <button
                key={period.value}
                type="button"
                role="radio"
                aria-checked={timePeriod === period.value}
                className={cn(
                  "rounded-sm px-2.5 py-1 text-xs font-medium transition-all",
                  timePeriod === period.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
                onClick={() => setTimePeriod(period.value)}
              >
                {period.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Status filters">
        <FilterChip
          label="All"
          active={statusFilter === "all"}
          onClick={() => setStatusFilter("all")}
          ref={statusFilter === "all" ? activeFilterRef : undefined}
          ariaLabel="Show all skills"
        />
        <FilterChip
          label="Active"
          active={statusFilter === "active"}
          onClick={() => setStatusFilter("active")}
          ariaLabel="Show only active skills"
        />
        <FilterChip
          label={`Failing (${skills.filter((s) => s.failures_24h > 0).length})`}
          active={statusFilter === "failing"}
          tone="danger"
          onClick={() => setStatusFilter("failing")}
          ariaLabel="Show only failing skills"
        />
        <FilterChip
          label="Untested"
          active={statusFilter === "untested"}
          onClick={() => setStatusFilter("untested")}
          ariaLabel="Show only untested skills"
        />
        {hasActiveFilter && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => {
              setStatusFilter("all")
              setQuery("")
            }}
            aria-label="Clear all filters"
          >
            <XIcon className="size-3" />
            Clear
          </Button>
        )}
      </div>

      {/* Results count */}
      {hasActiveFilter && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          Showing {filtered.length} of {skills.length} skills
        </p>
      )}

      {/* Loading State */}
      {overviewQuery.isLoading ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">Loading sandbox…</CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState
          allCount={skills.length}
          filterActive={hasActiveFilter}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((skill) => (
            <SandboxSkillCard
              key={skill.id}
              skill={skill}
              workspace={workspace}
              onOpenDebugger={() =>
                setTarget({
                  skillSlug: skill.slug,
                  skillTitle: skill.title,
                  systemKind:
                    skill.system_kind === "agents"
                      ? ("agents" as SkillSystemKind)
                      : undefined,
                })
              }
              disabled={!overview?.can_use_sandbox}
            />
          ))}
        </div>
      )}

      {/* Debugger Modal */}
      {target ? (
        <ExecutionDebugger
          open={true}
          onOpenChange={(open) => {
            if (!open) setTarget(null)
          }}
          skillSlug={target.skillSlug}
          skillTitle={target.skillTitle}
          systemKind={target.systemKind}
          canWrite={true}
          onToggleEnabled={() => {
            // Toggling from the sandbox debugger is intentionally a no-op here:
            // sandbox enable/disable lives on the skill detail page where ownership
            // and risk policies are visible. Keep this consistent so we don't
            // surprise admins.
          }}
          toggleEnabledPending={false}
        />
      ) : null}
    </div>
  )
}

// ── Skill Card ──────────────────────────────────────────────────────────

function SandboxSkillCard({
  skill,
  workspace,
  onOpenDebugger,
  disabled,
}: {
  skill: SandboxSkillSummary
  workspace: string | undefined
  onOpenDebugger: () => void
  disabled: boolean
}) {
  const latest = skill.latest_run
  const tone = skill.failures_24h > 0 ? "danger" : "neutral"
  const hasError = latest?.error_message != null && latest.error_message !== ""

  return (
    <Card
      className={cn(
        "group flex flex-col transition hover:border-primary/40 hover:shadow-sm",
        tone === "danger" && "border-l-2 border-l-destructive",
      )}
      aria-label={`Sandbox card for ${skill.title}`}
    >
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        {/* Header: Title + Badge */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <Link
              to={buildWorkspacePath(
                workspace,
                skill.system_kind === "agents"
                  ? `/agents/skills/${skill.slug}`
                  : `/skills/${skill.slug}`,
              )}
              className="text-sm font-semibold hover:underline block truncate"
              aria-label={`Open ${skill.title} skill page`}
            >
              {skill.title}
            </Link>
            <p className="text-[11px] text-muted-foreground truncate" aria-label={`${skill.team_name} team, ${skill.department_name} department`}>
              {skill.team_name} · {skill.department_name}
            </p>
          </div>
          <Badge
            variant="outline"
            className="gap-1 text-[10px] shrink-0"
            aria-label="Sandbox enabled"
          >
            <ShieldCheckIcon className="size-3" aria-hidden />
            <span className="hidden sm:inline">Sandbox</span>
          </Badge>
        </div>

        {/* Description */}
        {skill.description ? (
          <p className="line-clamp-2 text-xs text-muted-foreground" aria-hidden>
            {skill.description}
          </p>
        ) : null}

        {/* Metrics Row */}
        <div className="flex flex-wrap gap-1.5 text-[11px] text-muted-foreground" aria-label="Run statistics">
          <span className="inline-flex items-center rounded-md border bg-muted/40 px-2 py-0.5">
            <span className="font-medium text-foreground">{skill.runs_24h}</span>
            <span className="ml-0.5">runs</span>
          </span>
          {skill.failures_24h > 0 ? (
            <span className="inline-flex items-center rounded-md border border-destructive/40 bg-destructive/10 px-2 py-0.5 text-xs text-destructive font-medium">
              <span aria-label={`${skill.failures_24h} failures`}>{skill.failures_24h} fail{skill.failures_24h === 1 ? "" : "s"}</span>
            </span>
          ) : null}
        </div>

        {/* Latest Run Status */}
        {latest ? (
          <div
            className={cn(
              "rounded-md border p-2 text-[11px]",
              hasError
                ? "border-destructive/30 bg-destructive/5"
                : "border-border bg-muted/20",
            )}
            aria-label={`Latest run: ${runStatusLabel(latest.status)}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-medium">
                <RunStatusDot status={latest.status} aria-hidden />
                <span className="truncate">{runStatusLabel(latest.status)}</span>
              </span>
              <span className="shrink-0 text-muted-foreground tabular-nums">
                {formatRunDuration(latest.duration_ms)}
              </span>
            </div>
            <p className="mt-0.5 text-muted-foreground truncate">
              {formatRelativeDate(latest.created_at)} · {latest.caller_label}
            </p>
            {hasError ? (
              <p className="mt-1 line-clamp-2 text-xs text-destructive font-medium" role="alert">
                {latest.error_message}
              </p>
            ) : null}
          </div>
        ) : (
          <div
            className="rounded-md border border-dashed border-border/60 p-2 text-[11px] text-muted-foreground"
            aria-label="This skill has not been run yet"
          >
            Never run yet
          </div>
        )}

        {/* Actions */}
        <div className="mt-auto flex items-center gap-2 pt-1">
          <Button
            type="button"
            size="sm"
            className="flex-1 gap-2"
            onClick={onOpenDebugger}
            disabled={disabled}
            aria-label={`Open debugger for ${skill.title}`}
          >
            <PlayIcon className="size-3.5" />
            Open debugger
          </Button>
          <Button
            asChild
            size="icon-sm"
            variant="ghost"
            aria-label={`Open ${skill.title} skill page in new tab`}
          >
            <Link
              to={buildWorkspacePath(
                workspace,
                skill.system_kind === "agents"
                  ? `/agents/skills/${skill.slug}`
                  : `/skills/${skill.slug}`,
              )}
            >
              <ExternalLinkIcon className="size-4" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Summary Stat Card ──────────────────────────────────────────────────

function SummaryStat({
  label,
  value,
  hint,
  tone = "neutral",
  ariaLabel,
}: {
  label: string
  value: number
  hint?: string
  tone?: "neutral" | "success" | "danger"
  ariaLabel?: string
}) {
  const toneClasses: Record<typeof tone, string> = {
    neutral: "text-foreground",
    success: "text-emerald-600 dark:text-emerald-400",
    danger: "text-destructive",
  }
  const iconMap: Record<typeof tone, React.ReactNode> = {
    neutral: null,
    success: <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" aria-hidden />,
    danger: <AlertTriangleIcon className="size-4 text-destructive" aria-hidden />,
  }
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          {iconMap[tone]}
        </div>
        <p
          className={cn("text-2xl font-semibold tabular-nums", toneClasses[tone])}
          aria-label={ariaLabel}
        >
          {value}
        </p>
        {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  )
}

// ── Filter Chip ─────────────────────────────────────────────────────────

const FilterChip = React.forwardRef<
  HTMLButtonElement,
  {
    label: string
    active: boolean
    onClick: () => void
    tone?: "danger"
    ariaLabel?: string
  }
>(({ label, active, onClick, tone, ariaLabel }, ref) => (
  <button
    ref={ref}
    type="button"
    onClick={onClick}
    className={cn(
      "inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      active
        ? tone === "danger"
          ? "border-destructive/60 bg-destructive/10 text-destructive shadow-sm"
          : "border-primary bg-primary text-primary-foreground shadow-sm"
        : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
    )}
    role="radio"
    aria-pressed={active}
    aria-label={ariaLabel || label}
  >
    {active && tone !== "danger" && <CheckIcon className="size-3" aria-hidden />}
    {label}
  </button>
))
FilterChip.displayName = "FilterChip"

// ── Empty State ─────────────────────────────────────────────────────────

function EmptyState({
  allCount,
  filterActive,
}: {
  allCount: number
  filterActive: boolean
}) {
  if (allCount === 0) {
    return (
      <Card>
        <CardContent className="space-y-3 p-6 text-center sm:p-8">
          <div className="mx-auto flex size-10 sm:size-12 items-center justify-center rounded-full bg-muted">
            <ShieldCheckIcon className="size-5 sm:size-6 text-muted-foreground/60" aria-hidden />
          </div>
          <p className="text-base sm:text-lg font-medium">No executable skills yet</p>
          <p className="mx-auto max-w-md text-xs sm:text-sm text-muted-foreground">
            Open any skill and toggle <strong>Sandboxed execution</strong> on. It will appear here
            as soon as it's enabled.
          </p>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="mt-2"
          >
            <Link to={buildWorkspacePath(undefined, "/skills")}>
              Browse skills
              <ExternalLinkIcon className="ml-1.5 size-3.5" aria-hidden />
            </Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-6 text-center sm:p-8">
        <ShieldCheckIcon className="mx-auto size-8 sm:size-10 text-muted-foreground/60" aria-hidden />
        <p className="text-base sm:text-lg font-medium">
          {filterActive ? "No matching skills" : "No skills to show"}
        </p>
        <p className="mx-auto max-w-md text-xs sm:text-sm text-muted-foreground">
          {filterActive
            ? "Try clearing your search or switching back to &lsquo;All&rsquo;."
            : "All executable skills appear here when they are run."}
        </p>
        {filterActive && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 text-destructive hover:text-destructive"
            onClick={() => {
              window.location.hash = ""
              // Trigger a page refresh to clear filters
              window.location.href = window.location.pathname
            }}
          >
            <XIcon className="mr-1.5 size-3.5" />
            Clear all filters
          </Button>
        )}
      </CardContent>
    </Card>
  )
}