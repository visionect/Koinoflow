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

export function buildCloudLoggingUrl(externalJobName: string): string | null {
  if (!externalJobName) return null
  // External job name format: projects/{project}/locations/{loc}/jobs/{job}/executions/{exec}
  const match = externalJobName.match(
    /^projects\/([^/]+)\/locations\/([^/]+)\/jobs\/([^/]+)\/executions\/([^/]+)$/,
  )
  if (!match) return null
  const [, project, , jobName, executionName] = match
  const filter =
    `resource.type%3D%22cloud_run_job%22 ` +
    `resource.labels.job_name%3D%22${jobName}%22 ` +
    `labels.%22run.googleapis.com%2Fexecution_name%22%3D%22${executionName}%22`
  return `https://console.cloud.google.com/logs/query;query=${filter}?project=${project}`
}

export function buildGcsConsoleUrl(uri: string): string | null {
  if (!uri.startsWith("gs://")) return null
  const path = uri.slice(5)
  return `https://console.cloud.google.com/storage/browser/_details/${path}`
}
