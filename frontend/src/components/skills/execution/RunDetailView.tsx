import * as React from "react"
import {
  AlertTriangleIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  RotateCwIcon,
  ScrollTextIcon,
  SquareIcon,
  Trash2Icon,
} from "lucide-react"
import { toast } from "sonner"

import { useSkillExecutionRunLogs, useSkillExecutionRunOutput } from "@/api/client"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { ScrollArea } from "@/components/ui/scroll-area"
import { formatDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { SkillExecutionRun } from "@/types"

import { RunStatusBadge } from "./RunStatusBadge"
import { formatRunDuration, isActiveStatus } from "./runStatus"

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function CopyButton({
  value,
  label,
  className,
}: {
  value: string | null | undefined
  label?: string
  className?: string
}) {
  const [copied, setCopied] = React.useState(false)

  async function handleCopy() {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("Could not copy to clipboard")
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={handleCopy}
      disabled={!value}
      className={cn("h-7 gap-1 px-2 text-xs", className)}
    >
      {copied ? (
        <>
          <CheckIcon className="size-3" /> Copied
        </>
      ) : (
        <>
          <CopyIcon className="size-3" /> {label ?? "Copy"}
        </>
      )}
    </Button>
  )
}

function StatField({
  label,
  value,
  mono,
  copy,
}: {
  label: string
  value: React.ReactNode
  mono?: boolean
  copy?: string | null
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b py-1.5 text-xs last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1">
        <span
          className={cn(
            "max-w-[260px] truncate text-right text-foreground",
            mono ? "font-mono text-[11px]" : "",
          )}
          title={typeof value === "string" ? value : undefined}
        >
          {value}
        </span>
        {copy ? <CopyButton value={copy} label="" className="h-5 w-5 p-0" /> : null}
      </span>
    </div>
  )
}

function LogsPanel({
  runId,
  isActive,
}: {
  runId: string
  isActive: boolean
}) {
  const logsQuery = useSkillExecutionRunLogs(runId, { isActive })
  const [autoScroll, setAutoScroll] = React.useState(true)
  const scrollRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    if (!autoScroll) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [logsQuery.data?.logs, autoScroll])

  const logs = logsQuery.data
  const lines = logs?.logs ? logs.logs.split("\n") : []

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5">
        <div className="flex items-center gap-2 text-xs font-medium">
          <ScrollTextIcon className="size-3.5" />
          <span>Stderr / logs</span>
          {logs?.truncated ? (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-300">
              Tail only
            </span>
          ) : null}
          {isActive ? (
            <span className="text-[10px] text-muted-foreground">live · refreshing every 3s</span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(event) => setAutoScroll(event.target.checked)}
              className="size-3 accent-primary"
            />
            Auto-scroll
          </label>
          <CopyButton value={logs?.logs ?? ""} label="Copy logs" />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void logsQuery.refetch()}
            disabled={logsQuery.isFetching}
            className="h-7 gap-1 px-2 text-xs"
          >
            <RotateCwIcon className={cn("size-3", logsQuery.isFetching ? "animate-spin" : "")} />
            Refresh
          </Button>
        </div>
      </div>
      <ScrollArea className="h-[260px] bg-background">
        <div ref={scrollRef} className="h-[260px] overflow-y-auto">
          {logsQuery.isLoading ? (
            <p className="p-3 text-xs text-muted-foreground">Loading logs…</p>
          ) : !logs?.available ? (
            <p className="p-3 text-xs text-muted-foreground">
              {logs?.source === "missing"
                ? "Logs file not yet uploaded — check back when the run reports a logs URI."
                : logs?.source === "unavailable"
                  ? "Log proxy is not configured on this server."
                  : logs?.source === "unsupported"
                    ? "This skill backend does not produce GCS-stored logs."
                    : "No logs available for this run yet."}
            </p>
          ) : lines.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">No log output captured.</p>
          ) : (
            <pre className="p-3 font-mono text-[11px] leading-relaxed text-foreground/90">
              {lines.map((line, idx) => (
                <div key={idx} className="grid grid-cols-[2.5rem_1fr] gap-2">
                  <span className="select-none text-right text-muted-foreground/60">{idx + 1}</span>
                  <span className="whitespace-pre-wrap break-all">{line}</span>
                </div>
              ))}
            </pre>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

function FullOutputPanel({
  fetchFullOutput,
  onLoad,
  query,
}: {
  fetchFullOutput: boolean
  onLoad: () => void
  query: ReturnType<typeof useSkillExecutionRunOutput>
}) {
  if (!fetchFullOutput) {
    return (
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        <span>Output exceeded the inline preview cap. Load it to view in the app.</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onLoad}
          className="h-7 gap-1 text-xs"
        >
          <DownloadIcon className="size-3" /> Load full output
        </Button>
      </div>
    )
  }
  if (query.isLoading) {
    return (
      <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        Loading output…
      </p>
    )
  }
  if (query.isError) {
    return (
      <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-destructive">
        Could not load output. Try again later.
      </p>
    )
  }
  const data = query.data
  if (!data) return null
  if (data.source === "too_large") {
    const json =
      typeof data.output === "string"
        ? data.output
        : data.output != null
          ? JSON.stringify(data.output, null, 2)
          : ""
    return (
      <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        Output is {formatBytes(data.size_bytes)} — too large to display inline.
        {json ? " Showing the inline copy below; full payload is retained for the run’s lifetime." : ""}
      </p>
    )
  }
  if (data.source === "missing") {
    return (
      <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        Output file is not yet available — the run may still be finalizing.
      </p>
    )
  }
  if (!data.available) {
    return (
      <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        Output is not available for this run.
      </p>
    )
  }
  const formatted =
    typeof data.output === "string"
      ? data.output
      : data.output != null
        ? JSON.stringify(data.output, null, 2)
        : ""
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>Full output · {formatBytes(data.size_bytes)}</span>
      </div>
      <pre className="max-h-[360px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed">
        {formatted}
      </pre>
    </div>
  )
}

export function RunDetailView({
  run,
  onRerun,
  onCancel,
  cancelPending,
  rerunPending,
}: {
  run: SkillExecutionRun
  onRerun: (run: SkillExecutionRun) => void
  onCancel: (run: SkillExecutionRun) => void
  cancelPending: boolean
  rerunPending: boolean
}) {
  const [showInputs, setShowInputs] = React.useState(false)
  const [showOutput, setShowOutput] = React.useState(true)
  const [showResource, setShowResource] = React.useState(false)
  const [fetchFullOutput, setFetchFullOutput] = React.useState(false)
  const isActive = isActiveStatus(run.status)

  const needsLargeOutputFetch = !run.output && Boolean(run.output_uri)
  const fullOutputQuery = useSkillExecutionRunOutput(run.id, {
    enabled: needsLargeOutputFetch && fetchFullOutput,
  })

  const exitCode =
    typeof run.resource_usage?.exit_code === "number"
      ? (run.resource_usage.exit_code as number)
      : null
  const backendLabel =
    typeof run.resource_usage?.backend === "string"
      ? (run.resource_usage.backend as string)
      : typeof run.resource_usage?.executor === "string"
        ? (run.resource_usage.executor as string)
        : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <RunStatusBadge status={run.status} />
          <span className="text-xs text-muted-foreground">
            {formatDateTime(run.created_at)} · {run.caller_label}
          </span>
          {run.version_number ? (
            <span className="rounded bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
              v{run.version_number}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <CopyButton value={run.id} label="Run ID" />
          {run.cancellable ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onCancel(run)}
              disabled={cancelPending}
              className="h-7 gap-1 text-xs"
            >
              <SquareIcon className="size-3" />
              {cancelPending ? "Cancelling…" : "Cancel run"}
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="default"
            onClick={() => onRerun(run)}
            disabled={rerunPending}
            className="h-7 gap-1 text-xs"
          >
            <RotateCwIcon className="size-3" />
            {rerunPending ? "Starting…" : "Rerun"}
          </Button>
        </div>
      </div>

      {run.error_message ? (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">{run.status === "timeout" ? "Timed out" : "Error"}</p>
            <p className="whitespace-pre-wrap break-words">{run.error_message}</p>
          </div>
        </div>
      ) : null}

      {run.requires_approval ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
          <p className="font-medium">Approval required</p>
          <p>
            Review the inputs below, then click "Rerun" with the approval checkbox to release this
            execution.
          </p>
        </div>
      ) : null}

      <div className="rounded-lg border">
        <div className="grid grid-cols-2 gap-x-4 px-3">
          <StatField
            label="Started"
            value={run.started_at ? formatDateTime(run.started_at) : "—"}
          />
          <StatField
            label="Finished"
            value={run.finished_at ? formatDateTime(run.finished_at) : "—"}
          />
          <StatField label="Duration" value={formatRunDuration(run.duration_ms)} />
          <StatField label="Exit code" value={exitCode ?? "—"} />
          <StatField label="Backend" value={backendLabel ?? "—"} />
          <StatField label="Caller" value={run.caller_type} />
        </div>
      </div>

      <Collapsible open={showInputs} onOpenChange={setShowInputs}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
          >
            {showInputs ? (
              <ChevronDownIcon className="size-3" />
            ) : (
              <ChevronRightIcon className="size-3" />
            )}
            Inputs
            <CopyButton
              value={JSON.stringify(run.inputs, null, 2)}
              label=""
              className="h-5 w-5 p-0"
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="mt-1 max-h-[200px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed">
            {JSON.stringify(run.inputs ?? {}, null, 2)}
          </pre>
        </CollapsibleContent>
      </Collapsible>

      <Collapsible open={showOutput} onOpenChange={setShowOutput}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
          >
            {showOutput ? (
              <ChevronDownIcon className="size-3" />
            ) : (
              <ChevronRightIcon className="size-3" />
            )}
            Output
            {run.output ? (
              <CopyButton
                value={JSON.stringify(run.output, null, 2)}
                label=""
                className="h-5 w-5 p-0"
              />
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {run.output ? (
            <pre className="mt-1 max-h-[360px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed">
              {JSON.stringify(run.output, null, 2)}
            </pre>
          ) : needsLargeOutputFetch ? (
            <FullOutputPanel
              fetchFullOutput={fetchFullOutput}
              onLoad={() => setFetchFullOutput(true)}
              query={fullOutputQuery}
            />
          ) : (
            <p className="mt-1 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
              {run.status === "succeeded" ? "Empty output." : "No output yet."}
            </p>
          )}
        </CollapsibleContent>
      </Collapsible>

      <LogsPanel runId={run.id} isActive={isActive} />

      <Collapsible open={showResource} onOpenChange={setShowResource}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          >
            {showResource ? (
              <ChevronDownIcon className="size-3" />
            ) : (
              <ChevronRightIcon className="size-3" />
            )}
            Resource usage & metadata
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-2">
          <div className="rounded-lg border">
            <div className="grid grid-cols-1 gap-x-4 px-3 sm:grid-cols-2">
              <StatField label="Run ID" value={run.id} mono copy={run.id} />
              <StatField
                label="Expires"
                value={run.expires_at ? formatDateTime(run.expires_at) : "—"}
              />
            </div>
          </div>
          {Object.keys(run.resource_usage ?? {}).length > 0 ? (
            <pre className="max-h-[160px] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed">
              {JSON.stringify(run.resource_usage, null, 2)}
            </pre>
          ) : null}
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

// Re-export so callers can render an empty placeholder without importing icons:
export function RunDetailEmpty() {
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      <Trash2Icon className="mb-2 size-4 opacity-50" />
      <p className="font-medium">No run selected</p>
      <p className="mt-1 max-w-sm text-xs">
        Run the skill from the left panel or pick a run from the history below.
      </p>
    </div>
  )
}
