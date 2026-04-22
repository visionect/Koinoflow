import * as React from "react"

import {
  ArrowLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CornerUpLeftIcon,
  UserIcon,
} from "lucide-react"
import { Link, useParams } from "react-router-dom"

import {
  useFileDiff,
  useProcess,
  useRevertVersion,
  useVersionDiff,
  useVersions,
} from "@/api/client"
import { FileDiffSummary, UnifiedDiffViewer } from "@/components/shared/DiffViewer"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusBadge } from "@/components/shared/StatusBadge"
import {
  buildWorkspacePath,
  formatRelativeDate,
  formatDateTime,
  getDisplayName,
} from "@/lib/format"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { ProcessVersionBrief } from "@/types"

export function ProcessHistoryPage() {
  const { workspace, processSlug } = useParams<{ workspace: string; processSlug: string }>()
  const processQuery = useProcess(processSlug ?? "")
  const versionsQuery = useVersions(processSlug ?? "")

  const [selectedVersionNumber, setSelectedVersionNumber] = React.useState<number | null>(null)
  const [revertDialogOpen, setRevertDialogOpen] = React.useState(false)

  const publishedVersionNumber = processQuery.data?.current_version?.version_number ?? null
  const latestVersionNumber = versionsQuery.data?.[0]?.version_number ?? null

  React.useEffect(() => {
    if (publishedVersionNumber !== null && selectedVersionNumber === null) {
      setSelectedVersionNumber(publishedVersionNumber)
    } else if (selectedVersionNumber === null) {
      const first = versionsQuery.data?.[0]
      if (first) {
        setSelectedVersionNumber(first.version_number)
      }
    }
  }, [publishedVersionNumber, selectedVersionNumber, versionsQuery.data])

  const selectedVersion = versionsQuery.data?.find(
    (v) => v.version_number === selectedVersionNumber,
  )

  if (versionsQuery.isError) {
    return (
      <ErrorState
        message={
          versionsQuery.error instanceof Error
            ? versionsQuery.error.message
            : "Unable to load version history"
        }
        onRetry={() => void versionsQuery.refetch()}
      />
    )
  }

  if (!processQuery.data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-9 w-56" />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="space-y-6">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="space-y-2 pl-8">
                <Skeleton className="h-6 w-20" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            ))}
          </div>
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
              <Skeleton className="mt-2 h-3 w-48" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-20" />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Button asChild size="sm" variant="ghost">
        <Link to={buildWorkspacePath(workspace, `/processes/${processQuery.data.slug}`)}>
          <ArrowLeftIcon aria-hidden />
          Back to process
        </Link>
      </Button>

      <PageHeader
        title="Full history"
        description="Select a version to see its metadata; expand any entry to view its diff."
      />

      {versionsQuery.isLoading || !versionsQuery.data ? (
        <div className="space-y-6 pl-8">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          ))}
        </div>
      ) : versionsQuery.data?.length ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
          <TooltipProvider delayDuration={300}>
            <div className="relative space-y-0">
              <div className="absolute left-[11px] top-2 h-[calc(100%-16px)] w-px bg-border" />

              {versionsQuery.data.map((version) => (
                <HistoryTimelineItem
                  key={version.id}
                  version={version}
                  processSlug={processQuery.data.slug}
                  isPublished={version.version_number === publishedVersionNumber}
                  isSelected={version.version_number === selectedVersionNumber}
                  onSelect={() => setSelectedVersionNumber(version.version_number)}
                />
              ))}
            </div>
          </TooltipProvider>

          {selectedVersion ? (
            <div className="sticky top-6">
              <Card>
                <CardHeader>
                  <CardTitle>Selected version</CardTitle>
                  <CardDescription>Details for the entry highlighted on the left.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div className="space-y-1">
                    <p className="text-muted-foreground">Status</p>
                    <StatusBadge
                      status={
                        selectedVersion.version_number === publishedVersionNumber
                          ? "published"
                          : "draft"
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground">Version</p>
                    <p className="font-medium">
                      {selectedVersion.version_number === publishedVersionNumber
                        ? `Published v${selectedVersion.version_number}`
                        : `v${selectedVersion.version_number}`}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground">Saved by</p>
                    <p className="font-medium">{getDisplayName(selectedVersion.authored_by)}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(selectedVersion.created_at)}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground">Current process owner</p>
                    <p className="font-medium">{getDisplayName(processQuery.data.owner)}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground">Last validated</p>
                    <p className="font-medium">
                      {formatRelativeDate(processQuery.data.last_reviewed_at, "Not validated yet")}
                    </p>
                  </div>
                  {selectedVersion.version_number !== latestVersionNumber ? (
                    <div className="pt-2 border-t">
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full"
                        onClick={() => setRevertDialogOpen(true)}
                      >
                        <CornerUpLeftIcon className="size-3.5 mr-2" aria-hidden />
                        Revert to this version
                      </Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
              {selectedVersion && selectedVersion.version_number !== latestVersionNumber ? (
                <RevertConfirmDialog
                  open={revertDialogOpen}
                  onOpenChange={setRevertDialogOpen}
                  targetVersionNumber={selectedVersion.version_number}
                  processSlug={processQuery.data.slug}
                  onSuccess={() => {
                    setSelectedVersionNumber(null)
                  }}
                />
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <EmptyState
          title="No saved versions yet"
          description="Version history will appear here as soon as the process is saved."
        />
      )}
    </div>
  )
}

type HistoryTimelineItemProps = {
  version: ProcessVersionBrief
  processSlug: string
  isPublished: boolean
  isSelected: boolean
  onSelect: () => void
}

function HistoryTimelineItem({
  version,
  processSlug,
  isPublished,
  isSelected,
  onSelect,
}: HistoryTimelineItemProps) {
  const [showDiff, setShowDiff] = React.useState(false)
  const hasDiff = version.version_number > 1

  function toggleDiff(e: React.MouseEvent) {
    e.stopPropagation()
    setShowDiff((prev) => !prev)
  }

  return (
    <div
      className={`relative cursor-pointer rounded-lg pl-8 pb-6 pr-3 pt-2 transition-colors ${
        isSelected ? "bg-primary/5" : "hover:bg-muted/30"
      }`}
      onClick={onSelect}
    >
      <div
        className={`absolute left-1.5 top-3.5 z-10 size-3 rounded-full border-2 ${
          isPublished
            ? "border-emerald-500 bg-emerald-500"
            : isSelected
              ? "border-primary bg-primary"
              : "border-muted-foreground/40 bg-background"
        }`}
        aria-hidden
      />

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold">v{version.version_number}</span>
          {isPublished ? (
            <Badge variant="default" className="text-[10px] px-1.5 py-0">
              LIVE
            </Badge>
          ) : null}
          {isSelected ? (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              Selected
            </Badge>
          ) : null}
          {version.reverted_from_version_number !== null ? (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-1">
              <CornerUpLeftIcon className="size-2.5" aria-hidden />
              Reverted from v{version.reverted_from_version_number}
            </Badge>
          ) : null}
        </div>

        <p className="text-sm text-muted-foreground">
          {version.change_summary ||
            (version.version_number === 1 ? "Process created" : "No summary provided")}
        </p>

        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
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

        {hasDiff ? (
          <Card
            className={`cursor-pointer overflow-hidden transition-colors ${showDiff ? "" : "hover:bg-muted/30"}`}
            onClick={toggleDiff}
            aria-expanded={showDiff}
          >
            <CardHeader className="flex flex-row items-center justify-between bg-muted/50 py-2 px-4">
              <CardTitle className="text-sm font-medium">Diff vs previous version</CardTitle>
              {showDiff ? (
                <ChevronDownIcon className="size-4 text-muted-foreground" aria-hidden />
              ) : (
                <ChevronRightIcon className="size-4 text-muted-foreground" aria-hidden />
              )}
            </CardHeader>
            <CardContent className="px-4 py-3 space-y-3">
              <p className="text-sm leading-relaxed">
                {version.change_summary || "No summary provided"}
              </p>
              {!showDiff ? (
                <p className="text-xs text-muted-foreground">Click to expand the unified diff.</p>
              ) : null}
            </CardContent>
            {showDiff ? (
              <div className="border-t px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <InlineDiffBlock processSlug={processSlug} versionNumber={version.version_number} />
              </div>
            ) : null}
          </Card>
        ) : null}
      </div>
    </div>
  )
}

type InlineDiffBlockProps = {
  processSlug: string
  versionNumber: number
}

function InlineDiffBlock({ processSlug, versionNumber }: InlineDiffBlockProps) {
  const diffQuery = useVersionDiff(processSlug, versionNumber)
  const fileDiffQuery = useFileDiff(processSlug, versionNumber)

  if (diffQuery.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (diffQuery.isError) {
    return (
      <p className="text-xs text-destructive">
        Unable to load diff.{" "}
        <button className="underline" onClick={() => void diffQuery.refetch()}>
          Retry
        </button>
      </p>
    )
  }

  if (!diffQuery.data) {
    return null
  }

  return (
    <div className="space-y-4">
      <UnifiedDiffViewer
        hunks={diffQuery.data.hunks}
        stats={diffQuery.data.stats}
        oldLabel={`v${diffQuery.data.old_version.version_number}`}
        newLabel={`v${diffQuery.data.new_version.version_number}`}
      />
      {fileDiffQuery.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : fileDiffQuery.isError ? (
        <p className="text-xs text-destructive">
          Unable to load support file diff.{" "}
          <button className="underline" onClick={() => void fileDiffQuery.refetch()}>
            Retry
          </button>
        </p>
      ) : fileDiffQuery.data && fileDiffQuery.data.entries.length > 0 ? (
        <FileDiffSummary entries={fileDiffQuery.data.entries} />
      ) : null}
    </div>
  )
}

type RevertConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  targetVersionNumber: number
  processSlug: string
  onSuccess: () => void
}

function RevertConfirmDialog({
  open,
  onOpenChange,
  targetVersionNumber,
  processSlug,
  onSuccess,
}: RevertConfirmDialogProps) {
  const revertMutation = useRevertVersion(processSlug)

  async function handleConfirm() {
    await revertMutation.mutateAsync({ targetVersionNumber, payload: {} })
    onOpenChange(false)
    onSuccess()
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revert to v{targetVersionNumber}?</AlertDialogTitle>
          <AlertDialogDescription>
            A new version will be created with the content and files from v{targetVersionNumber}.
            The full version history is preserved — no data will be lost.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={revertMutation.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={revertMutation.isPending}
            onClick={(e) => {
              e.preventDefault()
              void handleConfirm()
            }}
          >
            {revertMutation.isPending ? "Reverting…" : "Revert"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
