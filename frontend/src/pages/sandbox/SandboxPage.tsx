import * as React from "react"
import {
  AlertTriangleIcon,
  ExternalLinkIcon,
  PlayIcon,
  SearchIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
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

export function SandboxPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const overviewQuery = useSandboxOverview()
  const { isAdmin } = useAuth()
  const [query, setQuery] = React.useState("")
  const [statusFilter, setStatusFilter] = React.useState<"all" | "failing" | "active" | "untested">(
    "all",
  )
  const [target, setTarget] = React.useState<DebuggerTarget | null>(null)

  const overview = overviewQuery.data
  const skills = React.useMemo(() => overview?.skills ?? [], [overview?.skills])

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

  const totalRuns24h = skills.reduce((acc, s) => acc + (s.runs_24h ?? 0), 0)
  const totalFailures24h = skills.reduce((acc, s) => acc + (s.failures_24h ?? 0), 0)

  return (
    <div className="space-y-6">
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
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-900 dark:text-amber-100">
          <AlertTriangleIcon className="mt-0.5 size-5 shrink-0" />
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

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryStat
          label="Executable skills"
          value={skills.length}
          hint="Skills with sandbox enabled"
        />
        <SummaryStat
          label="Runs · last 24h"
          value={totalRuns24h}
          hint={`${skills.filter((s) => (s.runs_24h ?? 0) > 0).length} skills exercised`}
        />
        <SummaryStat
          label="Failures · last 24h"
          value={totalFailures24h}
          tone={totalFailures24h > 0 ? "danger" : "success"}
          hint={
            totalFailures24h > 0
              ? `${skills.filter((s) => s.failures_24h > 0).length} skills with errors`
              : "All recent runs healthy"
          }
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[260px]">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by skill, team, or description"
            className="h-9 pl-9"
          />
        </div>
        <FilterChip
          label="All"
          active={statusFilter === "all"}
          onClick={() => setStatusFilter("all")}
        />
        <FilterChip
          label="Active"
          active={statusFilter === "active"}
          onClick={() => setStatusFilter("active")}
        />
        <FilterChip
          label={`Failing (${skills.filter((s) => s.failures_24h > 0).length})`}
          active={statusFilter === "failing"}
          tone="danger"
          onClick={() => setStatusFilter("failing")}
        />
        <FilterChip
          label="Untested"
          active={statusFilter === "untested"}
          onClick={() => setStatusFilter("untested")}
        />
      </div>

      {overviewQuery.isLoading ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">Loading sandbox…</CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState
          allCount={skills.length}
          filterActive={statusFilter !== "all" || query !== ""}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
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

  return (
    <Card
      className={cn(
        "group flex flex-col transition hover:border-primary/40 hover:shadow-sm",
        tone === "danger" ? "border-destructive/30" : "",
      )}
    >
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <Link
              to={buildWorkspacePath(
                workspace,
                skill.system_kind === "agents"
                  ? `/agents/skills/${skill.slug}`
                  : `/skills/${skill.slug}`,
              )}
              className="text-sm font-semibold hover:underline"
            >
              {skill.title}
            </Link>
            <p className="text-[11px] text-muted-foreground">
              {skill.team_name} · {skill.department_name}
            </p>
          </div>
          <Badge variant="outline" className="gap-1 text-[10px]">
            <ShieldCheckIcon className="size-3" />
            Sandbox
          </Badge>
        </div>

        {skill.description ? (
          <p className="line-clamp-2 text-xs text-muted-foreground">{skill.description}</p>
        ) : null}

        <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-md border bg-muted/40 px-2 py-1">
            {skill.runs_24h} run{skill.runs_24h === 1 ? "" : "s"} · 24h
          </span>
          {skill.failures_24h > 0 ? (
            <span className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-destructive">
              {skill.failures_24h} failure{skill.failures_24h === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>

        {latest ? (
          <div className="rounded-md border bg-muted/30 p-2 text-[11px]">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-medium">
                <RunStatusDot status={latest.status} />
                {runStatusLabel(latest.status)}
              </span>
              <span className="text-muted-foreground">
                {formatRunDuration(latest.duration_ms)}
              </span>
            </div>
            <p className="mt-0.5 text-muted-foreground">
              {formatRelativeDate(latest.created_at)} · {latest.caller_label}
            </p>
            {latest.error_message ? (
              <p className="mt-1 line-clamp-2 text-destructive">{latest.error_message}</p>
            ) : null}
          </div>
        ) : (
          <p className="rounded-md border border-dashed p-2 text-[11px] text-muted-foreground">
            Never run yet.
          </p>
        )}

        <div className="mt-auto flex items-center gap-2 pt-1">
          <Button
            type="button"
            size="sm"
            className="flex-1 gap-2"
            onClick={onOpenDebugger}
            disabled={disabled}
          >
            <PlayIcon className="size-3.5" />
            Open debugger
          </Button>
          <Button asChild size="icon-sm" variant="ghost" aria-label="Open skill page">
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

function SummaryStat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string
  value: number
  hint?: string
  tone?: "neutral" | "success" | "danger"
}) {
  const toneClasses: Record<typeof tone, string> = {
    neutral: "text-foreground",
    success: "text-emerald-600 dark:text-emerald-400",
    danger: "text-destructive",
  }
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={cn("text-2xl font-semibold", toneClasses[tone])}>{value}</p>
        {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  )
}

function FilterChip({
  label,
  active,
  onClick,
  tone,
}: {
  label: string
  active: boolean
  onClick: () => void
  tone?: "danger"
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs",
        active
          ? tone === "danger"
            ? "border-destructive/60 bg-destructive/10 text-destructive"
            : "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background hover:bg-muted",
      )}
    >
      {label}
    </button>
  )
}

function EmptyState({
  allCount,
  filterActive,
}: {
  allCount: number
  filterActive: boolean
}) {
  return (
    <Card>
      <CardContent className="space-y-2 p-8 text-center">
        <ShieldCheckIcon className="mx-auto size-8 text-muted-foreground/60" />
        <p className="text-sm font-medium">
          {allCount === 0
            ? "No executable skills yet"
            : filterActive
              ? "Nothing matches your filters"
              : "No skills to show"}
        </p>
        <p className="mx-auto max-w-md text-xs text-muted-foreground">
          {allCount === 0
            ? "Open any skill and toggle 'Sandboxed execution' on. It will appear here as soon as it's enabled."
            : "Try clearing the search or switching back to 'All'."}
        </p>
      </CardContent>
    </Card>
  )
}
