import * as React from "react"

import {
  CheckCircle2Icon,
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CircleIcon,
  XIcon,
} from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useOnboardingProgress,
  useTeams,
  useUpdateOnboardingPreference,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath } from "@/lib/format"
import type { OnboardingStep } from "@/types"

const COMPLETION_LINGER_MS = 5000

export function OnboardingGuide() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isAdmin } = useAuth()
  const { data, isLoading, isError } = useOnboardingProgress(Boolean(isAdmin))
  const updatePreference = useUpdateOnboardingPreference()
  const teamsQuery = useTeams()
  const [expanded, setExpanded] = React.useState(false)
  const [observedIncomplete, setObservedIncomplete] = React.useState(false)
  const [hideAfterComplete, setHideAfterComplete] = React.useState(false)
  const completedDismissedRef = React.useRef(false)

  const isComplete = Boolean(data?.is_complete)
  // Only celebrate when we've actually seen the transition from incomplete →
  // complete during this session. Otherwise reloading an already-onboarded
  // workspace would replay the "You're all set" card every time.
  const showCelebration = isComplete && observedIncomplete && !hideAfterComplete

  const dismissCompletedGuide = React.useCallback(() => {
    setHideAfterComplete(true)
    if (completedDismissedRef.current || data?.is_dismissed) {
      return
    }
    completedDismissedRef.current = true
    updatePreference.mutate(
      { dismissed: true },
      {
        onError: () => {
          completedDismissedRef.current = false
        },
      },
    )
  }, [data?.is_dismissed, updatePreference])

  React.useEffect(() => {
    if (data && !data.is_complete) {
      setObservedIncomplete(true)
    }
  }, [data])

  React.useEffect(() => {
    if (showCelebration) {
      const t = setTimeout(() => dismissCompletedGuide(), COMPLETION_LINGER_MS)
      return () => clearTimeout(t)
    }
  }, [dismissCompletedGuide, showCelebration])

  if (!isAdmin || isLoading || isError || !data || data.is_dismissed || !workspace) {
    return null
  }
  if (isComplete && !showCelebration) {
    return null
  }

  // Step 1 (workspace creation) is always satisfied by the time the guide
  // mounts inside AppLayout — drop it from the user-visible list.
  const visibleSteps = data.steps.filter((s) => s.step !== 1)
  if (visibleSteps.length === 0) {
    return null
  }

  const firstNonSystemTeamSlug = teamsQuery.data?.[0]?.slug
  const ctaPathFor = (step: OnboardingStep) => {
    if (step.key === "department" && firstNonSystemTeamSlug) {
      return `/teams/${firstNonSystemTeamSlug}`
    }
    if (step.key === "skill_read") {
      return "/settings/mcp"
    }
    return step.cta_path
  }

  const currentStep = data.steps.find((s) => s.step === data.current_step) ?? null
  const handleDismiss = () => {
    updatePreference.mutate({ dismissed: true })
    toast("Setup guide hidden", {
      description: "Restore it anytime from the user menu in the top right.",
      duration: 5000,
    })
  }

  return (
    <div className="pointer-events-auto fixed bottom-4 right-4 z-30 hidden w-[min(100vw-2rem,20rem)] sm:block">
      <Card
        className="border shadow-lg duration-200 animate-in fade-in slide-in-from-bottom-2"
        role="region"
        aria-label="Workspace setup guide"
      >
        {isComplete ? (
          <CompletedCard onDismiss={dismissCompletedGuide} />
        ) : currentStep ? (
          <ActiveCard
            data={data}
            visibleSteps={visibleSteps}
            currentStep={currentStep}
            ctaPathFor={ctaPathFor}
            workspace={workspace}
            expanded={expanded}
            onToggleExpanded={setExpanded}
            onDismiss={handleDismiss}
            isDismissPending={updatePreference.isPending}
          />
        ) : null}
      </Card>
    </div>
  )
}

function CompletedCard({ onDismiss }: { onDismiss: () => void }) {
  return (
    <>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2 pr-2">
          <CheckCircle2Icon className="h-5 w-5 text-primary" />
          <CardTitle className="text-base font-semibold leading-snug">
            You&rsquo;re all set
          </CardTitle>
        </div>
        <Button
          aria-label="Close"
          className="h-8 w-8 shrink-0"
          onClick={onDismiss}
          size="icon"
          type="button"
          variant="ghost"
        >
          <XIcon className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Your workspace is connected end to end. This guide will close shortly.
        </p>
        <p className="text-xs text-muted-foreground">
          You can also explore{" "}
          <span className="font-medium text-foreground">Agents</span> for dedicated AI
          connections or the{" "}
          <span className="font-medium text-foreground">Executable</span> tab on the
          Skills page for sandboxed execution.
        </p>
      </CardContent>
    </>
  )
}

interface ActiveCardProps {
  data: { steps: OnboardingStep[]; current_step: number }
  visibleSteps: OnboardingStep[]
  currentStep: OnboardingStep
  ctaPathFor: (step: OnboardingStep) => string
  workspace: string
  expanded: boolean
  onToggleExpanded: (next: boolean) => void
  onDismiss: () => void
  isDismissPending: boolean
}

function ActiveCard({
  data,
  visibleSteps,
  currentStep,
  ctaPathFor,
  workspace,
  expanded,
  onToggleExpanded,
  onDismiss,
}: ActiveCardProps) {
  const visibleIndex = visibleSteps.findIndex((s) => s.step === currentStep.step) + 1
  const total = visibleSteps.length

  return (
    <>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <div className="space-y-1 pr-2">
          <p className="text-xs text-muted-foreground">
            Step {Math.max(visibleIndex, 1)} of {total}
          </p>
          <CardTitle className="text-base font-semibold leading-snug">
            {currentStep.title}
          </CardTitle>
        </div>
        <Button
          aria-label="Hide onboarding guide"
          className="h-8 w-8 shrink-0"
          onClick={onDismiss}
          size="icon"
          type="button"
          variant="ghost"
        >
          <XIcon className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{currentStep.description}</p>
        {currentStep.key === "skill_read" ? (
          <p className="text-xs text-muted-foreground">
            Open your MCP client (Cursor, Claude, etc.) and read any skill — we&rsquo;ll
            detect it automatically.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild size="sm" type="button">
            <Link to={buildWorkspacePath(workspace, ctaPathFor(currentStep))}>
              {currentStep.key === "skill_read" ? "View connection" : "Get started"}
              <ChevronRightIcon className="ml-1 h-4 w-4" />
            </Link>
          </Button>
        </div>

        <div className="flex gap-1 pt-1" role="list" aria-label="Onboarding progress">
          {visibleSteps.map((step) => {
            const isCurrent = step.step === data.current_step
            const label = `Step ${step.step}: ${step.title} — ${
              step.completed ? "complete" : isCurrent ? "in progress" : "not started"
            }`
            return (
              <div
                key={step.step}
                aria-label={label}
                className={`h-1.5 w-1.5 rounded-full ${
                  step.completed
                    ? "bg-primary"
                    : isCurrent
                      ? "bg-primary/50"
                      : "bg-muted"
                }`}
                role="listitem"
              />
            )
          })}
        </div>

        <Collapsible open={expanded} onOpenChange={onToggleExpanded}>
          <CollapsibleTrigger asChild>
            <Button
              className="h-7 w-full justify-between px-2 text-xs text-muted-foreground"
              size="sm"
              type="button"
              variant="ghost"
            >
              <span>{expanded ? "Hide all steps" : "Show all steps"}</span>
              <ChevronDownIcon
                className={`h-3.5 w-3.5 transition-transform ${
                  expanded ? "rotate-180" : ""
                }`}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2">
            <ul className="space-y-1.5">
              {visibleSteps.map((step) => {
                const isCurrent = step.step === data.current_step
                return (
                  <li
                    key={step.step}
                    className={`flex items-start gap-2 text-xs ${
                      step.completed
                        ? "text-muted-foreground"
                        : isCurrent
                          ? "font-medium text-foreground"
                          : "text-muted-foreground"
                    }`}
                  >
                    {step.completed ? (
                      <CheckIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                    ) : (
                      <CircleIcon
                        className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                          isCurrent ? "text-primary" : "text-muted-foreground/60"
                        }`}
                      />
                    )}
                    <span
                      className={
                        step.completed ? "line-through decoration-muted-foreground/50" : ""
                      }
                    >
                      {step.title}
                    </span>
                  </li>
                )
              })}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </>
  )
}
