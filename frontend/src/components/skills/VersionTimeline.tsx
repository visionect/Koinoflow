import { UserIcon } from "lucide-react"
import { useNavigate, useParams } from "react-router-dom"

import { useVersions, type SkillSystemKind } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  buildWorkspacePath,
  formatDateTime,
  formatRelativeDate,
  getDisplayName,
} from "@/lib/format"
import type { SkillVersionBrief } from "@/types"

type VersionTimelineProps = {
  skillSlug: string
  publishedVersionNumber: number | null
  systemKind?: SkillSystemKind
}

export function VersionTimeline({
  skillSlug,
  publishedVersionNumber,
  systemKind,
}: VersionTimelineProps) {
  const versionsQuery = useVersions(skillSlug, systemKind)
  const navigate = useNavigate()
  const { workspace } = useParams<{ workspace: string }>()

  if (versionsQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    )
  }

  if (!versionsQuery.data?.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No versions yet. Save the skill to create the first version.
      </p>
    )
  }

  function handleClick() {
    navigate(
      buildWorkspacePath(
        workspace,
        systemKind === "agents"
          ? `/agents/skills/${skillSlug}/history`
          : `/skills/${skillSlug}/history`,
      ),
    )
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="relative cursor-pointer space-y-0 rounded-md transition-colors hover:bg-muted/40"
        onClick={handleClick}
        role="link"
      >
        <div className="absolute left-[11px] top-2 h-[calc(100%-16px)] w-px bg-border" />

        {versionsQuery.data.map((version) => (
          <VersionTimelineItem
            key={version.id}
            version={version}
            isCurrent={version.version_number === publishedVersionNumber}
          />
        ))}
      </div>
    </TooltipProvider>
  )
}

type VersionTimelineItemProps = {
  version: SkillVersionBrief
  isCurrent: boolean
}

function VersionTimelineItem({ version, isCurrent }: VersionTimelineItemProps) {
  return (
    <div className="relative pl-8 pb-4">
      <div
        className={`absolute left-1.5 top-1.5 z-10 size-3 rounded-full border-2 ${
          isCurrent
            ? "border-emerald-500 bg-emerald-500"
            : "border-muted-foreground/40 bg-background"
        }`}
      />

      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">v{version.version_number}</span>
          {isCurrent ? (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              LIVE
            </Badge>
          ) : null}
        </div>

        {version.change_summary ? (
          <p className="text-xs text-foreground/80 leading-relaxed">{version.change_summary}</p>
        ) : null}

        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <UserIcon className="size-3" aria-hidden />
          <span>{getDisplayName(version.authored_by)}</span>
          <span className="mx-0.5">&middot;</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="cursor-default">{formatRelativeDate(version.created_at)}</span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-xs">
              {formatDateTime(version.created_at)}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}
