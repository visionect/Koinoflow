import { ClockIcon } from "lucide-react"

import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"

const PRICING_URL = import.meta.env.VITE_PRICING_URL ?? ""

function daysRemaining(trialEnd: string): number {
  const end = new Date(trialEnd)
  const now = new Date()
  const diff = end.getTime() - now.getTime()
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)))
}

export function TrialBanner() {
  const { billingEnabled, subscriptionStatus, trialEnd } = useAuth()

  if (!billingEnabled || subscriptionStatus !== "in_trial" || !trialEnd) {
    return null
  }

  const days = daysRemaining(trialEnd)
  const expiry = new Date(trialEnd).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })

  const message =
    days > 0
      ? `You're on a free trial — ${days} day${days !== 1 ? "s" : ""} left (expires ${expiry}).`
      : `Your free trial expires today (${expiry}).`

  const urgent = days <= 3

  return (
    <div
      role="status"
      aria-live={urgent ? "assertive" : "polite"}
      className={
        urgent
          ? "flex flex-col items-start gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive sm:flex-row sm:items-center sm:justify-center sm:gap-3"
          : "flex flex-col items-start gap-2 border-b border-warning/40 bg-warning/10 px-4 py-2 text-sm text-foreground sm:flex-row sm:items-center sm:justify-center sm:gap-3"
      }
    >
      <span className="flex min-w-0 items-center gap-2">
        <ClockIcon className="size-4 shrink-0" aria-hidden />
        <span className="truncate">{message}</span>
      </span>
      {PRICING_URL ? (
        <Button
          asChild
          size="sm"
          variant="outline"
          className={
            urgent
              ? "h-7 border-destructive/50 bg-transparent px-3 text-destructive hover:bg-destructive/20"
              : "h-7 border-warning/60 bg-transparent px-3 text-foreground hover:bg-warning/20"
          }
        >
          <a href={PRICING_URL} target="_blank" rel="noopener noreferrer">
            View plans
          </a>
        </Button>
      ) : null}
    </div>
  )
}
