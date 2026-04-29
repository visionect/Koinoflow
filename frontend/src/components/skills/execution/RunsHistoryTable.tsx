import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { formatRelativeDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { SkillExecutionRun } from "@/types"

import { RunStatusDot } from "./RunStatusBadge"
import { formatRunDuration, runStatusLabel } from "./runStatus"

export function RunsHistoryTable({
  runs,
  selectedRunId,
  onSelect,
  isLoading,
}: {
  runs: SkillExecutionRun[]
  selectedRunId: string | null
  onSelect: (runId: string) => void
  isLoading?: boolean
}) {
  if (isLoading && runs.length === 0) {
    return (
      <div className="rounded-lg border p-4 text-xs text-muted-foreground">Loading run history…</div>
    )
  }
  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
        No runs yet. Trigger one from the left panel to see it appear here.
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border">
      <ScrollArea className="max-h-[260px]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-muted/60 text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium">Status</th>
              <th className="px-3 py-1.5 text-left font-medium">Started</th>
              <th className="px-3 py-1.5 text-left font-medium">Duration</th>
              <th className="px-3 py-1.5 text-left font-medium">Caller</th>
              <th className="px-3 py-1.5 text-left font-medium">Version</th>
              <th className="px-3 py-1.5 text-right font-medium">ID</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const selected = run.id === selectedRunId
              return (
                <tr
                  key={run.id}
                  className={cn(
                    "cursor-pointer border-t hover:bg-muted/40",
                    selected ? "bg-primary/10 hover:bg-primary/15" : "",
                  )}
                  onClick={() => onSelect(run.id)}
                >
                  <td className="px-3 py-1.5">
                    <span className="flex items-center gap-2">
                      <RunStatusDot status={run.status} />
                      <span>{runStatusLabel(run.status)}</span>
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">
                    {formatRelativeDate(run.created_at, "—")}
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">
                    {formatRunDuration(run.duration_ms)}
                  </td>
                  <td className="max-w-[160px] truncate px-3 py-1.5 text-muted-foreground">
                    {run.caller_label}
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">
                    {run.version_number ? `v${run.version_number}` : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-[10px] text-muted-foreground">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1 font-mono text-[10px]"
                      onClick={(event) => {
                        event.stopPropagation()
                        onSelect(run.id)
                      }}
                    >
                      {run.id.slice(0, 8)}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </ScrollArea>
    </div>
  )
}
