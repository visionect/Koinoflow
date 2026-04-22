import { Link } from "react-router-dom"
import { AlertTriangleIcon, ShieldCheckIcon, UsersIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { buildWorkspacePath } from "@/lib/format"
import type { KoinoflowMetadata, RiskLevel } from "@/types"

const RISK_LABELS: Record<RiskLevel, { label: string; className: string }> = {
  low: {
    label: "Low risk",
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200",
  },
  medium: {
    label: "Medium risk",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  },
  high: {
    label: "High risk",
    className: "border-orange-500/40 bg-orange-500/10 text-orange-900 dark:text-orange-200",
  },
  critical: {
    label: "Critical risk",
    className: "border-destructive/40 bg-destructive/10 text-destructive",
  },
}

type Props = {
  metadata: KoinoflowMetadata
  workspaceSlug: string | undefined
}

function isEmpty(metadata: KoinoflowMetadata): boolean {
  return (
    metadata.retrieval_keywords.length === 0 &&
    metadata.risk_level === null &&
    metadata.requires_human_approval === false &&
    metadata.prerequisites.length === 0 &&
    metadata.audience.length === 0
  )
}

export function KoinoflowMetadataStrip({ metadata, workspaceSlug }: Props) {
  if (isEmpty(metadata)) return null

  const risk = metadata.risk_level ? RISK_LABELS[metadata.risk_level] : null

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border bg-card px-4 py-3 text-xs">
      {risk ? (
        <Badge variant="outline" className={`gap-1 ${risk.className}`}>
          <AlertTriangleIcon className="size-3" aria-hidden />
          {risk.label}
        </Badge>
      ) : null}

      {metadata.requires_human_approval ? (
        <Badge variant="outline" className="gap-1 border-primary/40 bg-primary/10 text-primary">
          <ShieldCheckIcon className="size-3" aria-hidden />
          Requires human approval
        </Badge>
      ) : null}

      {metadata.prerequisites.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 text-muted-foreground">
          <span className="font-medium text-foreground">Prerequisites:</span>
          {metadata.prerequisites.map((slug, index) => (
            <span key={slug} className="flex items-center gap-1">
              <Link
                to={buildWorkspacePath(workspaceSlug, `/processes/${slug}`)}
                className="underline decoration-dotted underline-offset-2 hover:text-foreground"
              >
                {slug}
              </Link>
              {index < metadata.prerequisites.length - 1 ? <span aria-hidden="true">·</span> : null}
            </span>
          ))}
        </div>
      ) : null}

      {metadata.audience.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 text-muted-foreground">
          <UsersIcon className="size-3" aria-hidden />
          {metadata.audience.map((entry) => (
            <Badge key={entry} variant="secondary" className="text-[10px]">
              {entry}
            </Badge>
          ))}
        </div>
      ) : null}

      {metadata.retrieval_keywords.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 text-muted-foreground">
          <span className="font-medium text-foreground">Keywords:</span>
          {metadata.retrieval_keywords.map((kw) => (
            <Badge key={kw} variant="secondary" className="text-[10px]">
              {kw}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}
