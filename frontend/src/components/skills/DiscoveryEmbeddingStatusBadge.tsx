import { CheckCircle2Icon, CircleDashedIcon, Clock3Icon } from "lucide-react"

import type { DiscoveryEmbeddingStatus } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const STATUS_CONFIG: Record<
  DiscoveryEmbeddingStatus,
  {
    label: string
    description: string
    className: string
    icon: typeof CheckCircle2Icon
  }
> = {
  ready: {
    label: "Semantic ready",
    description: "This published version is indexed for semantic skill discovery.",
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    icon: CheckCircle2Icon,
  },
  pending: {
    label: "Indexing",
    description:
      "Semantic discovery is preparing this published version. Keyword matching still works while indexing finishes.",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    icon: Clock3Icon,
  },
  not_applicable: {
    label: "Not indexed",
    description: "Only published skill versions are indexed for semantic discovery.",
    className: "border-muted-foreground/30 text-muted-foreground",
    icon: CircleDashedIcon,
  },
}

type DiscoveryEmbeddingStatusBadgeProps = {
  status: DiscoveryEmbeddingStatus
  compact?: boolean
}

export function DiscoveryEmbeddingStatusBadge({
  status,
  compact = false,
}: DiscoveryEmbeddingStatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={`gap-1 whitespace-nowrap ${config.className} ${compact ? "text-[10px]" : ""}`}
          >
            <Icon className="size-3" aria-hidden />
            {compact && status === "not_applicable" ? "Not indexed" : config.label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p>{config.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
