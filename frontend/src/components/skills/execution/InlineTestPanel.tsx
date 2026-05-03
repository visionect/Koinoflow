import * as React from "react"
import {
  CheckCircle2Icon,
  ClockIcon,
  PlayIcon,
  XCircleIcon,
  ZapIcon,
} from "lucide-react"
import { toast } from "sonner"

import {
  useExecuteSkill,
  useSkillExecutionSpec,
  type SkillSystemKind,
} from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import type { SkillExecutionRun } from "@/types"

import { InputsForm, type InputsFormHandle } from "./InputsForm"
import { RunStatusBadge } from "./RunStatusBadge"
import { isActiveStatus } from "./runStatus"

/**
 * Inline test panel that lets you test a skill's inputs/outputs directly
 * inside the IDE tab without switching to the Run tab.
 *
 * This is used inside SkillMiniIde to provide a "preview" execution experience.
 */
export function InlineTestPanel({
  skillSlug,
  systemKind,
  canWrite,
}: {
  skillSlug: string
  systemKind?: SkillSystemKind
  versionNumber: number | null
  canWrite: boolean
}) {
  const specQuery = useSkillExecutionSpec(skillSlug, systemKind)
  const executeSkill = useExecuteSkill(skillSlug, systemKind)

  const [isRunning, setIsRunning] = React.useState(false)
  const [lastRun, setLastRun] = React.useState<SkillExecutionRun | null>(null)
  const [jsonInput, setJsonInput] = React.useState("")
  const [jsonMode, setJsonMode] = React.useState(false)
  const [showRawOutput, setShowRawOutput] = React.useState(false)

  const inputsFormRef = React.useRef<InputsFormHandle | null>(null)
  const spec = specQuery.data
  const isEnabled = spec?.enabled === true

  const hasSchema = spec?.input_schema !== null && spec?.input_schema !== undefined

  // Reset JSON mode when schema changes
  React.useEffect(() => {
    if (!hasSchema) {
      setJsonMode(true)
    }
  }, [hasSchema])

  async function handleTestRun() {
    if (!isEnabled) {
      toast.error("Enable execution on this skill before testing.")
      return
    }
    if (!canWrite) {
      toast.error("You need write access to test a skill.")
      return
    }

    let inputs: Record<string, unknown> | null = null

    if (jsonMode) {
      const trimmed = jsonInput.trim()
      if (trimmed === "") {
        toast.info("Empty input — sending an empty object.")
        inputs = {}
      } else {
        try {
          const parsed = JSON.parse(trimmed)
          if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
            toast.error("Input must be a JSON object (not array or primitive).")
            return
          }
          inputs = parsed
        } catch {
          toast.error("Invalid JSON in input editor.")
          return
        }
      }
    } else {
      const serialized = inputsFormRef.current?.serialize()
      if (serialized === null) {
        toast.error("Fix the input validation errors before testing.")
        return
      }
      inputs = serialized as Record<string, unknown>
    }

    setIsRunning(true)
    try {
      const run = await executeSkill.mutateAsync({ inputs: inputs ?? {}, approved: false })
      setLastRun(run)
      if (run.status === "pending_approval") {
        toast.info("Execution needs approval. Switch to the Run tab to approve.")
      } else {
        toast.success(`Test run started: ${run.status}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start test run")
    } finally {
      setIsRunning(false)
    }
  }

  // Poll for run updates
  const runId = lastRun?.id
  const [polling, setPolling] = React.useState(false)
  React.useEffect(() => {
    if (!runId || !isActiveStatus(lastRun?.status)) {
      setPolling(false)
      return
    }
    setPolling(true)
    const interval = setInterval(() => {
      // Re-fetch run detail via API
      const scopeQuery = systemKind ? `?system_kind=${systemKind}` : ""
      fetch(`/skills/${skillSlug}/runs/${runId}${scopeQuery}`)
        .then((res) => res.json())
        .then((data) => {
          setLastRun((prev) => (prev?.id === data.id ? data : prev))
          if (!isActiveStatus(data.status)) {
            setPolling(false)
            toast.success(`Test run ${data.status}`)
          }
        })
        .catch(() => setPolling(false))
    }, 3000)
    return () => clearInterval(interval)
  }, [runId, lastRun?.status, skillSlug, systemKind])

  function handleJsonChange(text: string) {
    setJsonInput(text)
  }

  function handleLoadSample() {
    // Build a sample input from the schema defaults
    if (!spec?.input_schema?.properties) {
      toast.info("No schema properties available for a sample.")
      return
    }
    const sample: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(spec.input_schema.properties)) {
      const schema = val as Record<string, unknown>
      if (schema.default !== undefined) {
        sample[key] = schema.default
      } else if (schema.examples && Array.isArray(schema.examples) && schema.examples.length > 0) {
        sample[key] = schema.examples[0]
      } else if (schema.type === "string") {
        sample[key] = ""
      } else if (schema.type === "number" || schema.type === "integer") {
        sample[key] = 0
      } else if (schema.type === "boolean") {
        sample[key] = false
      }
    }
    const json = JSON.stringify(sample, null, 2)
    setJsonInput(json)
    toast.success("Sample input loaded")
  }

  return (
    <div className="space-y-3 rounded-lg border bg-card p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ZapIcon className="size-4 text-amber-500" />
          <h4 className="text-sm font-semibold">Quick test</h4>
          {!isEnabled ? (
            <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
              Disabled
            </Badge>
          ) : null}
          {lastRun && isActiveStatus(lastRun.status) ? (
            <Badge variant="secondary" className="h-4 gap-1 px-1.5 text-[10px]">
              <ClockIcon className="size-2.5 animate-pulse" /> Running
            </Badge>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            onClick={handleTestRun}
            disabled={!canWrite || !isEnabled || isRunning || polling}
            className="h-7 gap-1.5 px-2 text-xs"
          >
            {isRunning ? (
              <ZapIcon className="size-3 animate-pulse" />
            ) : (
              <PlayIcon className="size-3" />
            )}
            {isRunning ? "Running…" : "Run"}
          </Button>
        </div>
      </div>

      {/* Input section */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">Input parameters</Label>
          {hasSchema ? (
            <Tabs
              value={jsonMode ? "json" : "form"}
              onValueChange={(v) => setJsonMode(v === "json")}
              className="w-auto"
            >
              <TabsList className="h-6 gap-0 p-0.5">
                <TabsTrigger value="form" className="h-5 text-[10px] px-1.5">
                  Form
                </TabsTrigger>
                <TabsTrigger value="json" className="h-5 text-[10px] px-1.5">
                  JSON
                </TabsTrigger>
              </TabsList>
            </Tabs>
          ) : null}
        </div>

        {jsonMode ? (
          <div className="space-y-1.5">
            <Textarea
              value={jsonInput}
              onChange={(e) => handleJsonChange(e.target.value)}
              rows={6}
              spellCheck={false}
              className="font-mono text-xs"
              placeholder={hasSchema ? JSON.stringify(buildSampleFromSpec(spec), null, 2) : "{}"}
            />
            <div className="flex items-center justify-between">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLoadSample}
                className="h-6 gap-1 px-1.5 text-[10px] text-muted-foreground"
              >
                Load sample
              </Button>
              <span className="text-[10px] text-muted-foreground">
                {jsonInput.trim() === "" ? "empty" : `${jsonInput.length} chars`}
              </span>
            </div>
          </div>
        ) : hasSchema ? (
          <InputsForm
            ref={inputsFormRef}
            schema={spec.input_schema}
            onChange={() => {}}
          />
        ) : (
          <p className="text-xs text-muted-foreground">
            No input schema defined. Use JSON mode to provide inputs.
          </p>
        )}
      </div>

      {/* Output section */}
      {lastRun && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label className="text-xs font-medium">Output</Label>
              <RunStatusBadge status={lastRun.status} />
              {lastRun.finished_at ? (
                <span className="text-[10px] text-muted-foreground">
                  {new Date(lastRun.finished_at).toLocaleTimeString()}
                </span>
              ) : null}
            </div>
            {lastRun.output !== null ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowRawOutput(!showRawOutput)}
                className="h-6 gap-1 px-1.5 text-[10px] text-muted-foreground"
              >
                {showRawOutput ? "Formatted" : "Raw JSON"}
              </Button>
            ) : null}
          </div>

          {lastRun.status === "running" || lastRun.status === "queued" || lastRun.status === "pending_approval" ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed bg-muted/30 p-4 text-center">
              <ZapIcon className="size-4 animate-pulse text-amber-500" />
              <div>
                <p className="text-xs font-medium">
                  {lastRun.status === "pending_approval"
                    ? "Waiting for approval…"
                    : lastRun.status === "queued"
                      ? "Queued for execution…"
                      : "Executing…"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Results will appear here automatically
                </p>
              </div>
            </div>
          ) : lastRun.output !== null ? (
            <div className={cn(
              "max-h-[200px] overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-[11px]",
            )}>
              {showRawOutput ? (
                <pre>{JSON.stringify(lastRun.output, null, 2)}</pre>
              ) : (
                <OutputPreview output={lastRun.output} />
              )}
            </div>
          ) : null}

          {lastRun.error_message ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2">
              <XCircleIcon className="size-3.5 shrink-0 text-destructive mt-0.5" />
              <div>
                <p className="text-xs font-medium text-destructive">Execution failed</p>
                <p className="text-[11px] text-muted-foreground">{lastRun.error_message}</p>
              </div>
            </div>
          ) : null}

          {lastRun.status === "succeeded" && !lastRun.error_message && lastRun.output === null ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed bg-muted/30 p-3 text-center">
              <CheckCircle2Icon className="size-4 text-green-500" />
              <p className="text-xs text-muted-foreground">
                Skill completed successfully but produced no output payload.
              </p>
            </div>
          ) : null}
        </div>
      )}

      {/* Status hint when no run yet */}
      {!lastRun && (
        <div className="rounded-lg border border-dashed bg-muted/20 p-3 text-center">
          <p className="text-xs text-muted-foreground">
            Fill in the input parameters above and click <strong>Run</strong> to test this skill.
            {isEnabled
              ? " Results will appear here after execution."
              : " Enable the skill first to run tests."}
          </p>
        </div>
      )}
    </div>
  )
}

function buildSampleFromSpec(spec: { input_schema?: Record<string, unknown> } | null): string {
  if (!spec?.input_schema?.properties) {
    return "{}"
  }
  const sample: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(spec.input_schema.properties)) {
    const schema = val as Record<string, unknown>
    if (schema.default !== undefined) {
      sample[key] = schema.default
    } else if (schema.examples && Array.isArray(schema.examples) && schema.examples.length > 0) {
      sample[key] = schema.examples[0]
    } else if (schema.type === "string") {
      sample[key] = ""
    } else if (schema.type === "number" || schema.type === "integer") {
      sample[key] = 0
    } else if (schema.type === "boolean") {
      sample[key] = false
    }
  }
  return JSON.stringify(sample, null, 2)
}

/**
 * Renders a user-friendly preview of structured output.
 * Shows top-level keys with truncated values, expandable to full JSON.
 */
function OutputPreview({ output }: { output: unknown }) {
  const [expandedKey, setExpandedKey] = React.useState<string | null>(null)

  if (typeof output !== "object" || output === null) {
    return <pre>{String(output)}</pre>
  }

  const entries = Object.entries(output as Record<string, unknown>)
  if (entries.length === 0) {
    return <pre>{JSON.stringify(output, null, 2)}</pre>
  }

  function truncateValue(val: unknown, maxLen = 120): string {
    const str = typeof val === "string" ? val : JSON.stringify(val, null, 2)
    if (str.length <= maxLen) return str
    return str.slice(0, maxLen) + "…"
  }

  return (
    <div className="space-y-1">
      {entries.map(([key, val]) => (
        <div key={key}>
          <button
            type="button"
            className="flex w-full items-center justify-between text-left text-[11px]"
            onClick={() => setExpandedKey(expandedKey === key ? null : key)}
          >
            <span className="font-semibold text-foreground">{key}</span>
            <span className="text-muted-foreground">
              {expandedKey === key ? "▲" : "▼"}
            </span>
          </button>
          {expandedKey === key ? (
            <pre className="mt-1 rounded bg-muted/50 p-1.5 text-[10px]">
              {JSON.stringify(val, null, 2)}
            </pre>
          ) : (
            <p className="ml-2 text-[10px] text-muted-foreground">
              {truncateValue(val)}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}