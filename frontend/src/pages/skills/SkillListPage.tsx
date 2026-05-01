import * as React from "react"

import {
  AlertTriangleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ExternalLinkIcon,
  FilePlusIcon,
  PlayIcon,
  PlusIcon,
  SearchIcon,
  ShieldCheckIcon,
  UploadIcon,
} from "lucide-react"
import { Link, useParams, useSearchParams } from "react-router-dom"

import { useDepartments, useSandboxOverview, useSkills, useTeams, type SkillSystemKind } from "@/api/client"
import { DiscoveryEmbeddingStatusBadge } from "@/components/skills/DiscoveryEmbeddingStatusBadge"
import { ExecutionDebugger } from "@/components/skills/execution/ExecutionDebugger"
import { RunStatusDot } from "@/components/skills/execution/RunStatusBadge"
import {
  formatRunDuration,
  runStatusLabel,
} from "@/components/skills/execution/runStatus"
import { SkillCreateDialog } from "@/components/skills/SkillCreateDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { useAuth } from "@/hooks/useAuth"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { type SkillImportData, useSkillImport } from "@/hooks/use-skill-import"
import { buildWorkspacePath, formatRelativeDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { SandboxSkillSummary } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const PAGE_SIZE = 20

type DebuggerTarget = {
  skillSlug: string
  skillTitle: string
  systemKind?: SkillSystemKind
}

export function SkillListPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isEditor, isAdmin } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [createOpen, setCreateOpen] = React.useState(false)
  const [importData, setImportData] = React.useState<SkillImportData | null>(null)

  const view = searchParams.get("view") === "executable" ? "executable" : "catalog"

  const { fileInput, openFilePicker } = useSkillImport((data) => {
    setImportData(data)
    setCreateOpen(true)
  })

  function setView(v: string) {
    const next = new URLSearchParams(searchParams)
    if (v === "executable") {
      next.set("view", "executable")
    } else {
      next.delete("view")
    }
    next.delete("page")
    setSearchParams(next)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="All skills"
        description="Search, filter, and manage the operating procedures available across the workspace."
        action={
          isEditor ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button>
                  <PlusIcon />
                  New skill
                  <ChevronDownIcon className="ml-1 size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() => {
                    setImportData(null)
                    setCreateOpen(true)
                  }}
                >
                  <FilePlusIcon className="mr-2 size-4" />
                  Create from scratch
                </DropdownMenuItem>
                <DropdownMenuItem onClick={openFilePicker}>
                  <UploadIcon className="mr-2 size-4" />
                  Import .skill file
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null
        }
      />

      <Tabs value={view} onValueChange={setView}>
        <TabsList variant="line">
          <TabsTrigger value="catalog">Catalog</TabsTrigger>
          <TabsTrigger value="executable">
            <ShieldCheckIcon className="size-3.5" />
            Executable
          </TabsTrigger>
        </TabsList>

        <TabsContent value="catalog">
          <CatalogView
            workspace={workspace}
            searchParams={searchParams}
            setSearchParams={setSearchParams}
          />
        </TabsContent>

        <TabsContent value="executable">
          <ExecutableView workspace={workspace} isAdmin={isAdmin} />
        </TabsContent>
      </Tabs>

      {fileInput}

      <SkillCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        workspaceSlug={workspace}
        importData={importData}
        onImportConsumed={() => setImportData(null)}
      />
    </div>
  )
}

// ── Catalog tab (original skill list) ────────────────────────────────────

function CatalogView({
  workspace,
  searchParams,
  setSearchParams,
}: {
  workspace: string | undefined
  searchParams: URLSearchParams
  setSearchParams: (p: URLSearchParams) => void
}) {
  const team = searchParams.get("team") ?? ""
  const department = searchParams.get("department") ?? ""
  const status = searchParams.get("status") ?? ""
  const search = searchParams.get("search") ?? ""
  const page = Number(searchParams.get("page") ?? "1")
  const safePage = Number.isNaN(page) || page < 1 ? 1 : page

  const debouncedSearch = useDebouncedValue(search, 300)

  const teamsQuery = useTeams()
  const departmentsQuery = useDepartments(team || undefined)
  const skillsQuery = useSkills({
    team: team || undefined,
    department: department || undefined,
    status: status === "draft" || status === "published" ? status : undefined,
    search: debouncedSearch || undefined,
    limit: PAGE_SIZE,
    offset: (safePage - 1) * PAGE_SIZE,
  })

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)

    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }

    if (key !== "page") {
      next.set("page", "1")
    }

    setSearchParams(next)
  }

  const totalPages = Math.max(1, Math.ceil((skillsQuery.data?.count ?? 0) / PAGE_SIZE))

  return (
    <div className="space-y-6 pt-4">
      <div className="grid gap-3 rounded-2xl border bg-card p-4 md:grid-cols-2 xl:grid-cols-4">
        <Select
          value={team}
          onValueChange={(value) => setParam("team", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by team" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All teams</SelectItem>
            {teamsQuery.data?.map((teamItem) => (
              <SelectItem key={teamItem.id} value={teamItem.slug}>
                {teamItem.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={department}
          onValueChange={(value) => setParam("department", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by department" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All departments</SelectItem>
            {departmentsQuery.data?.map((departmentItem) => (
              <SelectItem key={departmentItem.id} value={departmentItem.slug}>
                {departmentItem.team_name} / {departmentItem.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={status}
          onValueChange={(value) => setParam("status", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="published">Published</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
          </SelectContent>
        </Select>

        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search skills..."
            value={search}
            onChange={(event) => setParam("search", event.target.value)}
          />
        </div>
      </div>

      {skillsQuery.isError ? (
        <ErrorState
          message={
            skillsQuery.error instanceof Error
              ? skillsQuery.error.message
              : "Unable to load skills"
          }
          onRetry={() => void skillsQuery.refetch()}
        />
      ) : skillsQuery.isLoading || !skillsQuery.data ? (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[34%]">Title</TableHead>
                <TableHead className="w-[20%]">Team / Department</TableHead>
                <TableHead className="w-[12%]">Status</TableHead>
                <TableHead className="w-[12%]">Review</TableHead>
                <TableHead className="w-[13%]">Discovery</TableHead>
                <TableHead className="w-[9%]">Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Array.from({ length: 5 }).map((_, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-2/3" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-16" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-20" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-24" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-10" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : skillsQuery.data?.items?.length ? (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-2xl border bg-card">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[34%]">Title</TableHead>
                  <TableHead className="w-[20%]">Team / Department</TableHead>
                  <TableHead className="w-[12%]">Status</TableHead>
                  <TableHead className="w-[12%]">Review</TableHead>
                  <TableHead className="w-[13%]">Discovery</TableHead>
                  <TableHead className="w-[9%]">Version</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skillsQuery.data.items.map((skill) => {
                  const rowHref = buildWorkspacePath(workspace, `/skills/${skill.slug}`)
                  return (
                    <TableRow
                      key={skill.id}
                      className="group cursor-pointer transition-colors hover:bg-muted/40"
                    >
                      <TableCell className="relative p-0">
                        <Link
                          to={rowHref}
                          className="flex min-w-0 items-center gap-2 px-4 py-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <div className="min-w-0">
                            <span className="block truncate font-medium text-foreground">
                              {skill.title}
                            </span>
                            <p className="mt-1 truncate text-xs text-muted-foreground">
                              {skill.description || "No description yet"}
                            </p>
                          </div>
                        </Link>
                      </TableCell>
                      <TableCell className="truncate text-sm text-muted-foreground">
                        {skill.team_name} / {skill.department_name}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={skill.status} />
                      </TableCell>
                      <TableCell>
                        {skill.needs_audit ? (
                          <TooltipProvider delayDuration={200}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge
                                  variant="outline"
                                  className="gap-1 border-destructive/40 text-destructive"
                                >
                                  <AlertTriangleIcon className="size-3" aria-hidden />
                                  Needs validation
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>
                                  The owner hasn&rsquo;t re-confirmed this skill is still
                                  accurate.
                                </p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : (
                          <span className="text-xs text-muted-foreground">&mdash;</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <DiscoveryEmbeddingStatusBadge
                          status={skill.discovery_embedding_status}
                          compact
                        />
                      </TableCell>
                      <TableCell className="truncate text-sm text-muted-foreground">
                        {skill.current_version_number
                          ? `v${skill.current_version_number}`
                          : "Unpublished"}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {(safePage - 1) * PAGE_SIZE + 1} to{" "}
              {Math.min(safePage * PAGE_SIZE, skillsQuery.data.count)} of{" "}
              {skillsQuery.data.count}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={safePage <= 1}
                onClick={() => setParam("page", String(safePage - 1))}
              >
                <ChevronLeftIcon />
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={safePage >= totalPages}
                onClick={() => setParam("page", String(safePage + 1))}
              >
                Next
                <ChevronRightIcon />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState
          title="No skills found"
          description="Adjust your filters or create a new skill to start building a reusable operations library."
        />
      )}
    </div>
  )
}

// ── Executable tab (sandbox view) ────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  team_manager: "Team manager",
  member: "Member",
  viewer: "Viewer",
}

function ExecutableView({
  workspace,
  isAdmin,
}: {
  workspace: string | undefined
  isAdmin: boolean
}) {
  const overviewQuery = useSandboxOverview()
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
    <div className="space-y-6 pt-4">
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
              .{" "}
              {isAdmin ? (
                <Link
                  to={buildWorkspacePath(workspace, "/settings")}
                  className="underline hover:no-underline"
                >
                  Change in settings
                </Link>
              ) : (
                "Ask an admin to lower the threshold or grant you access."
              )}
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
        <SandboxEmptyState
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
          onToggleEnabled={() => {}}
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

function SandboxEmptyState({
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
