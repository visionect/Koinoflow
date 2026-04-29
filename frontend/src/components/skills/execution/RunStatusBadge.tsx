import { Loader2Icon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { SkillExecutionRunStatus } from "@/types"

import { isActiveStatus, runStatusLabel, runStatusTone } from "./runStatus"

const TONE_CLASSES: Record<ReturnType<typeof runStatusTone>, string> = {
  success:
    "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  danger:
    "border-destructive/40 bg-destructive/10 text-destructive dark:text-destructive",
  warning:
    "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  neutral: "border-muted-foreground/30 bg-muted text-muted-foreground",
}

export function RunStatusBadge({
  status,
  className,
}: {
  status: SkillExecutionRunStatus
  className?: string
}) {
  const tone = runStatusTone(status)
  const showSpinner = status === "running" || status === "queued"

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5 px-2 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {showSpinner ? <Loader2Icon className="size-3 animate-spin" /> : null}
      {runStatusLabel(status)}
    </Badge>
  )
}

export function RunStatusDot({ status }: { status: SkillExecutionRunStatus }) {
  const tone = runStatusTone(status)
  const dotClass: Record<typeof tone, string> = {
    success: "bg-emerald-500",
    danger: "bg-destructive",
    warning: "bg-amber-500",
    info: "bg-sky-500",
    neutral: "bg-muted-foreground/40",
  }
  return (
    <span
      className={cn(
        "inline-block size-2 rounded-full",
        dotClass[tone],
        isActiveStatus(status) ? "animate-pulse" : "",
      )}
      aria-label={runStatusLabel(status)}
    />
  )
}
