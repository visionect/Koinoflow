import type { SkillExecutionRunStatus } from "@/types"

export type RunStatusTone = "neutral" | "info" | "success" | "warning" | "danger"

export function runStatusTone(status: SkillExecutionRunStatus): RunStatusTone {
  switch (status) {
    case "succeeded":
      return "success"
    case "failed":
    case "timeout":
      return "danger"
    case "pending_approval":
      return "warning"
    case "queued":
    case "running":
      return "info"
    case "cancelled":
    default:
      return "neutral"
  }
}

export function runStatusLabel(status: SkillExecutionRunStatus): string {
  switch (status) {
    case "pending_approval":
      return "Needs approval"
    case "queued":
      return "Queued"
    case "running":
      return "Running"
    case "succeeded":
      return "Succeeded"
    case "failed":
      return "Failed"
    case "timeout":
      return "Timed out"
    case "cancelled":
      return "Cancelled"
    default:
      return status
  }
}

export const ACTIVE_RUN_STATUSES: readonly SkillExecutionRunStatus[] = [
  "pending_approval",
  "queued",
  "running",
]

export function isActiveStatus(status: SkillExecutionRunStatus): boolean {
  return ACTIVE_RUN_STATUSES.includes(status)
}

export function formatRunDuration(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—"
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`
}

