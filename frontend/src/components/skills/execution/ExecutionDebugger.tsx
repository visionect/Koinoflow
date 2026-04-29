import * as React from "react"
import {
  ActivityIcon,
  AlertTriangleIcon,
  CodeIcon,
  HistoryIcon,
  PlayIcon,
  Settings2Icon,
  ShieldCheckIcon,
} from "lucide-react"
import { toast } from "sonner"

import {
  useCancelSkillExecutionRun,
  useExecuteSkill,
  useSkillExecutionRun,
  useSkillExecutionRuns,
  useSkillExecutionSpec,
  type SkillSystemKind,
} from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import type { SkillExecutionRun } from "@/types"

import { InputsForm, type InputsFormHandle, type InputsFormValue } from "./InputsForm"
import { RunDetailEmpty, RunDetailView } from "./RunDetailView"
import { RunStatusBadge } from "./RunStatusBadge"
import { RunsHistoryTable } from "./RunsHistoryTable"
import { SkillMiniIde, type SkillMiniIdeHandle } from "./SkillMiniIde"
import { isActiveStatus } from "./runStatus"

type DebuggerTab = "run" | "ide" | "config"

export function ExecutionDebugger({
  open,
  onOpenChange,
  skillSlug,
  skillTitle,
  systemKind,
  canWrite,
  onToggleEnabled,
  toggleEnabledPending,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  skillSlug: string
  skillTitle: string
  systemKind?: SkillSystemKind
  canWrite: boolean
  onToggleEnabled: (enabled: boolean) => void
  toggleEnabledPending: boolean
}) {
  const specQuery = useSkillExecutionSpec(skillSlug, systemKind)
  const runsQuery = useSkillExecutionRuns(skillSlug, systemKind)
  const executeSkill = useExecuteSkill(skillSlug, systemKind)
  const cancelRun = useCancelSkillExecutionRun(skillSlug, systemKind)

  const [tab, setTab] = React.useState<DebuggerTab>("run")
  const [selectedRunId, setSelectedRunId] = React.useState<string | null>(null)
  const [approved, setApproved] = React.useState(false)
  const [hasInputErrors, setHasInputErrors] = React.useState(false)
  const [pendingRunOnSave, setPendingRunOnSave] = React.useState(false)

  const inputsFormRef = React.useRef<InputsFormHandle | null>(null)
  const ideRef = React.useRef<SkillMiniIdeHandle | null>(null)

  const spec = specQuery.data
  const isEnabled = spec?.enabled === true
  const runs = React.useMemo(
    () => runsQuery.data?.items ?? [],
    [runsQuery.data?.items],
  )

  // Auto-select latest run when nothing chosen
  React.useEffect(() => {
    if (selectedRunId === null && runs[0]) {
      setSelectedRunId(runs[0].id)
    }
  }, [runs, selectedRunId])

  // Always tail the active run if there is one
  React.useEffect(() => {
    const active = runs.find((r) => isActiveStatus(r.status))
    if (active && active.id !== selectedRunId) {
      setSelectedRunId(active.id)
    }
  }, [runs, selectedRunId])

  // Live tail of the selected run via dedicated polling hook
  const selectedRunQuery = useSkillExecutionRun(selectedRunId)
  const selectedRun: SkillExecutionRun | null =
    selectedRunQuery.data ??
    (selectedRunId ? runs.find((r) => r.id === selectedRunId) ?? null : null)

  async function handleExecute() {
    if (!isEnabled) {
      toast.error("Enable execution before running.")
      return
    }
    const inputs = inputsFormRef.current?.serialize() ?? null
    if (inputs === null) {
      toast.error("Fix the input validation errors before running.")
      return
    }
    try {
      const run = await executeSkill.mutateAsync({ inputs, approved })
      setSelectedRunId(run.id)
      if (run.status === "pending_approval") {
        toast.info("Execution needs approval. Tick the approval box and run again.")
      } else {
        toast.success(`Execution ${run.status}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start the run")
    }
  }

  function handleRerun(run: SkillExecutionRun) {
    inputsFormRef.current?.setValue(run.inputs as InputsFormValue)
    setApproved(false)
    setTab("run")
    // Defer click so InputsForm reflects the new value before serializing
    window.setTimeout(() => void handleExecute(), 50)
  }

  async function handleCancel(run: SkillExecutionRun) {
    try {
      await cancelRun.mutateAsync(run.id)
      toast.success("Run cancelled")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not cancel run")
    }
  }

  function handleSavedAndRun() {
    setPendingRunOnSave(true)
    setTab("run")
    // Wait briefly for spec/version to refresh
    window.setTimeout(() => {
      setPendingRunOnSave(false)
      void handleExecute()
    }, 400)
  }

  function handleClose(next: boolean) {
    if (!next && ideRef.current?.isDirty()) {
      const ok = window.confirm("You have unsaved code edits. Discard them?")
      if (!ok) return
    }
    onOpenChange(next)
  }

  const activeRun = runs.find((r) => isActiveStatus(r.status)) ?? null

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="flex h-[92vh] max-h-[92vh] w-[min(1280px,96vw)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
        showCloseButton
      >
        <DialogHeader className="flex flex-row items-start justify-between gap-3 border-b px-5 py-3">
          <div className="space-y-0.5">
            <DialogTitle className="flex items-center gap-2 text-base">
              <ShieldCheckIcon className="size-4 text-primary" />
              Sandbox debugger
              <span className="text-muted-foreground">·</span>
              <span className="font-normal text-muted-foreground">{skillTitle}</span>
            </DialogTitle>
            <p className="text-xs text-muted-foreground">
              Run the skill in an isolated executor, inspect logs and output, and patch the code in
              place when something breaks.
            </p>
          </div>
          <div className="mr-9 flex items-center gap-3">
            {activeRun ? (
              <RunStatusBadge status={activeRun.status} />
            ) : runs[0] ? (
              <RunStatusBadge status={runs[0].status} />
            ) : null}
            <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-2 py-1">
              <Switch
                checked={isEnabled}
                disabled={!canWrite || !spec || toggleEnabledPending}
                onCheckedChange={(checked) => onToggleEnabled(checked)}
                aria-label="Enable sandbox execution"
              />
              <span className="text-xs">
                {isEnabled ? "Sandbox enabled" : "Sandbox disabled"}
              </span>
            </div>
          </div>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as DebuggerTab)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="border-b bg-muted/20 px-5">
            <TabsList className="h-9 gap-1">
              <TabsTrigger value="run" className="gap-1.5">
                <PlayIcon className="size-3.5" /> Run &amp; inspect
                {activeRun ? <Badge variant="secondary" className="ml-1 h-4 px-1 text-[9px]">live</Badge> : null}
              </TabsTrigger>
              <TabsTrigger value="ide" className="gap-1.5">
                <CodeIcon className="size-3.5" /> Edit code
              </TabsTrigger>
              <TabsTrigger value="config" className="gap-1.5">
                <Settings2Icon className="size-3.5" /> Configuration
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value="run"
            className="m-0 min-h-0 flex-1 overflow-hidden data-[state=inactive]:hidden"
            forceMount
          >
            <ScrollArea className="h-full">
              <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                <div className="space-y-4">
                  <div className="rounded-lg border bg-card p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-sm font-semibold">Run inputs</h3>
                      {!isEnabled ? (
                        <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
                          Sandbox disabled
                        </Badge>
                      ) : null}
                    </div>
                    {spec ? (
                      <InputsForm
                        ref={inputsFormRef}
                        schema={spec.input_schema}
                        onChange={(_value, hasErrors) => setHasInputErrors(hasErrors)}
                      />
                    ) : (
                      <p className="text-xs text-muted-foreground">Loading execution spec…</p>
                    )}

                    <div className="mt-3 space-y-2">
                      <label className="flex items-start gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={approved}
                          onChange={(event) => setApproved(event.target.checked)}
                          className="mt-0.5 size-3.5 accent-primary"
                        />
                        <span>
                          I have approval for this exact execution if the skill's risk policy
                          requires it.
                        </span>
                      </label>
                      <Button
                        type="button"
                        size="default"
                        disabled={
                          !isEnabled ||
                          executeSkill.isPending ||
                          activeRun !== null ||
                          hasInputErrors ||
                          pendingRunOnSave
                        }
                        onClick={() => void handleExecute()}
                        className="w-full gap-2"
                      >
                        <PlayIcon className="size-4" />
                        {executeSkill.isPending || pendingRunOnSave
                          ? "Starting…"
                          : activeRun
                            ? "A run is in progress"
                            : "Run skill in sandbox"}
                      </Button>
                    </div>
                  </div>

                  {spec ? <SpecSummary spec={spec} /> : null}
                </div>

                <div className="flex min-h-0 flex-col">
                  <div className="mb-2 flex items-center justify-between">
                    <h3 className="flex items-center gap-2 text-sm font-semibold">
                      <ActivityIcon className="size-4" /> Run detail
                    </h3>
                    {selectedRun ? (
                      <span className="text-[11px] text-muted-foreground">
                        {selectedRunQuery.isFetching ? "refreshing…" : ""}
                      </span>
                    ) : null}
                  </div>
                  {selectedRun ? (
                    <RunDetailView
                      run={selectedRun}
                      onRerun={handleRerun}
                      onCancel={(run) => void handleCancel(run)}
                      cancelPending={cancelRun.isPending}
                      rerunPending={executeSkill.isPending}
                    />
                  ) : (
                    <RunDetailEmpty />
                  )}
                </div>
              </div>

              <div className="border-t bg-muted/20 p-5">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <HistoryIcon className="size-4" /> Run history
                  </h3>
                  <span className="text-[11px] text-muted-foreground">
                    {runs.length} run{runs.length === 1 ? "" : "s"} · auto-refreshes while a run is
                    active
                  </span>
                </div>
                <RunsHistoryTable
                  runs={runs}
                  selectedRunId={selectedRunId}
                  onSelect={(id) => setSelectedRunId(id)}
                  isLoading={runsQuery.isLoading}
                />
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent
            value="ide"
            className="m-0 min-h-0 flex-1 overflow-hidden data-[state=inactive]:hidden"
            forceMount
          >
            <ScrollArea className="h-full">
              <div className="space-y-3 p-5">
                <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
                  <AlertTriangleIcon className="size-4 shrink-0 text-amber-500" />
                  <p>
                    Edits create a new <strong>draft version</strong> when you save. Use{" "}
                    <strong>Save &amp; rerun</strong> to test fixes immediately. Publish from the
                    skill page when ready.
                  </p>
                </div>
                <SkillMiniIde
                  ref={ideRef}
                  skillSlug={skillSlug}
                  versionNumber={spec?.version_number ?? null}
                  systemKind={systemKind}
                  canWrite={canWrite}
                  onSavedAndRun={handleSavedAndRun}
                  latestRunId={selectedRun?.id ?? runs[0]?.id ?? null}
                />
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent
            value="config"
            className="m-0 min-h-0 flex-1 overflow-hidden data-[state=inactive]:hidden"
            forceMount
          >
            <ScrollArea className="h-full">
              <div className="space-y-3 p-5">
                {spec ? <SpecDetail spec={spec} /> : null}
                <p className="text-xs text-muted-foreground">
                  Edit limits, network policy, and entrypoint from the skill detail page settings.
                </p>
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function SpecSummary({ spec }: { spec: NonNullable<ReturnType<typeof useSkillExecutionSpec>["data"]> }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Sandbox configuration
      </h4>
      <div className="grid gap-1.5 text-xs">
        <SpecRow label="Runtime" value={`${spec.runtime} · ${spec.latency_class}`} />
        <SpecRow label="Entrypoint" value={spec.entrypoint_path} mono />
        <SpecRow label="Timeout" value={`${spec.limits.timeout_seconds}s`} />
        <SpecRow label="Memory" value={`${spec.limits.memory_mb} MB`} />
        <SpecRow label="Daily cap" value={`${spec.limits.max_runs_per_day} runs`} />
        <SpecRow label="Concurrency" value={`${spec.limits.max_concurrent_runs} parallel`} />
        <SpecRow
          label="Egress"
          value={
            spec.network.policy === "none"
              ? "No network"
              : spec.network.allowed.length > 0
                ? spec.network.allowed.join(", ")
                : "Allowlist empty"
          }
        />
      </div>
    </div>
  )
}

function SpecDetail({ spec }: { spec: NonNullable<ReturnType<typeof useSkillExecutionSpec>["data"]> }) {
  return (
    <div className="space-y-3">
      <SpecSummary spec={spec} />
      <div className="rounded-lg border bg-card p-3">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Input schema
        </h4>
        <pre className="max-h-[200px] overflow-auto rounded border bg-muted/40 p-2 font-mono text-[11px]">
          {JSON.stringify(spec.input_schema ?? {}, null, 2)}
        </pre>
      </div>
      <div className="rounded-lg border bg-card p-3">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Output schema
        </h4>
        <pre className="max-h-[200px] overflow-auto rounded border bg-muted/40 p-2 font-mono text-[11px]">
          {JSON.stringify(spec.output_schema ?? {}, null, 2)}
        </pre>
      </div>
    </div>
  )
}

function SpecRow({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b py-1 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("text-right text-foreground", mono ? "font-mono text-[11px]" : "")}>
        {value}
      </span>
    </div>
  )
}
