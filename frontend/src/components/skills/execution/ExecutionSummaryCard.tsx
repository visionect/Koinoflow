import * as React from "react"
import { ExternalLinkIcon, ShieldCheckIcon, ZapIcon } from "lucide-react"
import { toast } from "sonner"

import {
  useSkillExecutionRuns,
  useSkillExecutionSpec,
  useUpdateSkillExecutionSpec,
  type SkillSystemKind,
} from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { formatRelativeDate } from "@/lib/format"

import { ExecutionDebugger } from "./ExecutionDebugger"
import { RunStatusDot } from "./RunStatusBadge"
import { formatRunDuration, runStatusLabel } from "./runStatus"

export function ExecutionSummaryCard({
  skillSlug,
  skillTitle,
  canWrite,
  systemKind,
}: {
  skillSlug: string
  skillTitle: string
  canWrite: boolean
  systemKind?: SkillSystemKind
}) {
  const specQuery = useSkillExecutionSpec(skillSlug, systemKind)
  const runsQuery = useSkillExecutionRuns(skillSlug, systemKind)
  const updateSpec = useUpdateSkillExecutionSpec(skillSlug, systemKind)

  const [debuggerOpen, setDebuggerOpen] = React.useState(false)

  const spec = specQuery.data
  const isEnabled = spec?.enabled === true
  const runs = runsQuery.data?.items ?? []
  const latest = runs[0]

  async function handleToggleExecution(enabled: boolean) {
    if (!spec) return
    try {
      await updateSpec.mutateAsync({
        enabled,
        runtime: spec.runtime,
        latency_class: spec.latency_class,
        entrypoint_path: spec.entrypoint_path,
        input_schema: spec.input_schema,
        output_schema: spec.output_schema,
        secrets_scope: spec.secrets_scope,
        secret_refs: spec.secret_refs,
        network: spec.network,
        limits: spec.limits,
      })
      toast.success(enabled ? "Sandbox execution enabled" : "Sandbox execution disabled")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update sandbox setting")
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="space-y-1 pb-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheckIcon className="size-4 text-primary" />
                Sandboxed execution
              </CardTitle>
              <CardDescription>Run this skill in an isolated executor.</CardDescription>
            </div>
            <Badge variant={isEnabled ? "default" : "secondary"}>
              {isEnabled ? "Executable" : "Disabled"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/30 p-2.5">
            <div>
              <p className="text-xs font-medium">Enable execution</p>
              <p className="text-[11px] text-muted-foreground">
                Off by default. Required before agents or you can run.
              </p>
            </div>
            <Switch
              checked={isEnabled}
              disabled={!canWrite || !spec || updateSpec.isPending}
              onCheckedChange={(checked) => void handleToggleExecution(checked)}
              aria-label="Enable sandbox execution"
            />
          </div>

          {latest ? (
            <button
              type="button"
              onClick={() => setDebuggerOpen(true)}
              className="flex w-full items-start justify-between gap-2 rounded-md border bg-background p-2.5 text-left text-xs hover:bg-muted/40"
            >
              <div className="space-y-0.5">
                <span className="flex items-center gap-1.5 font-medium">
                  <RunStatusDot status={latest.status} />
                  Latest: {runStatusLabel(latest.status)}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {formatRelativeDate(latest.created_at)} · {formatRunDuration(latest.duration_ms)}
                </span>
              </div>
              <ExternalLinkIcon className="size-3 text-muted-foreground" />
            </button>
          ) : isEnabled ? (
            <p className="rounded-md border border-dashed p-2.5 text-[11px] text-muted-foreground">
              No runs yet. Open the debugger to test the skill in the sandbox.
            </p>
          ) : null}

          <Button
            type="button"
            variant={isEnabled ? "default" : "outline"}
            className="w-full gap-2"
            onClick={() => setDebuggerOpen(true)}
          >
            <ZapIcon className="size-4" />
            Open sandbox debugger
          </Button>
        </CardContent>
      </Card>

      <ExecutionDebugger
        open={debuggerOpen}
        onOpenChange={setDebuggerOpen}
        skillSlug={skillSlug}
        skillTitle={skillTitle}
        systemKind={systemKind}
        canWrite={canWrite}
        onToggleEnabled={(checked) => void handleToggleExecution(checked)}
        toggleEnabledPending={updateSpec.isPending}
      />
    </>
  )
}
