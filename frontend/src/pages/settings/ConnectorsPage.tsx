import * as React from "react"

import { useQueryClient } from "@tanstack/react-query"
import { ExternalLinkIcon, RefreshCwIcon, SparklesIcon, Trash2Icon, ZapIcon } from "lucide-react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { toast } from "sonner"

import {
  apiFetch,
  queryKeys,
  useConnectors,
  useDisconnectConnector,
  useExtractionJobs,
  useTriggerExtraction,
  useTriggerSync,
} from "@/api/client"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { PageHeader } from "@/components/shared/PageHeader"
import { buildWorkspacePath } from "@/lib/format"
import type { ConnectorCredential } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function ConnectorsPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: connectors = [], isLoading } = useConnectors()
  const disconnect = useDisconnectConnector()
  const sync = useTriggerSync()
  const extract = useTriggerExtraction()
  const [disconnectTarget, setDisconnectTarget] = React.useState<ConnectorCredential | null>(null)
  const [connecting, setConnecting] = React.useState(false)

  const confluence = connectors.find((c) => c.provider === "confluence")

  const queryClient = useQueryClient()
  const { data: extractionJobs = [] } = useExtractionJobs(confluence?.id ?? "", Boolean(confluence))
  const latestJob = extractionJobs[0]
  const isExtracting = latestJob?.status === "pending" || latestJob?.status === "running"
  const needsExtractionBanner =
    Boolean(confluence) &&
    (confluence?.synced_pages_count ?? 0) > 0 &&
    (confluence?.changed_pages_count ?? 0) > 0 &&
    !isExtracting

  const prevExtractingRef = React.useRef(isExtracting)
  React.useEffect(() => {
    if (prevExtractingRef.current && !isExtracting) {
      queryClient.invalidateQueries({ queryKey: queryKeys.connectors.all })
    }
    prevExtractingRef.current = isExtracting
  }, [isExtracting, queryClient])

  React.useEffect(() => {
    if (searchParams.get("connected") === "confluence") {
      toast.success("Confluence connected! Initial sync is running.")
      setSearchParams({}, { replace: true })
    }
    if (searchParams.get("error")) {
      toast.error(`Connection failed: ${searchParams.get("error")}`)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  async function handleConnect() {
    setConnecting(true)
    try {
      const { redirect_url } = await apiFetch<{ redirect_url: string }>(
        "/connectors/confluence/connect",
      )
      window.location.href = redirect_url
    } catch {
      toast.error("Failed to initiate Confluence connection.")
      setConnecting(false)
    }
  }

  function handleExtract() {
    if (!confluence) return
    extract.mutate(confluence.id, {
      onSuccess: (data) => {
        toast.success("Extraction started", {
          description: `Job ${data.job_id.slice(0, 8)} queued`,
          action: {
            label: "View candidates",
            onClick: () => {
              window.location.href = buildWorkspacePath(workspace, "/capture/candidates")
            },
          },
        })
      },
      onError: (err) =>
        toast.error(err instanceof Error ? err.message : "Failed to start extraction"),
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Connectors"
        description="Connect external documentation sources to sync content into Koinoflow."
      />

      <Card>
        <CardHeader className="flex flex-row items-center gap-4 space-y-0">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-info/10">
            <ConfluenceIcon />
          </div>
          <div className="flex-1">
            <CardTitle>Confluence</CardTitle>
            <CardDescription>
              Sync spaces and pages from your Atlassian Confluence instance.
            </CardDescription>
          </div>
          {!isLoading && !confluence && (
            <Button onClick={handleConnect} disabled={connecting} className="gap-2 shrink-0">
              <ZapIcon className="size-4" />
              {connecting ? "Redirecting…" : "Connect"}
            </Button>
          )}
          {isLoading && <Skeleton className="h-9 w-24" />}
        </CardHeader>

        {confluence && (
          <CardContent>
            <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
              <div className="space-y-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={confluence.site_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 font-medium hover:underline truncate"
                  >
                    {confluence.site_url}
                    <ExternalLinkIcon className="size-3 shrink-0" />
                  </a>
                  <StatusBadge status={confluence.status} />
                </div>
                {confluence.connected_by_email && (
                  <p className="text-sm text-muted-foreground">
                    Connected by {confluence.connected_by_email}
                  </p>
                )}
                <SyncStatus job={confluence.last_sync_job} />
                {confluence.synced_pages_count > 0 && !needsExtractionBanner && (
                  <ExtractionStatus
                    job={latestJob}
                    changedPages={confluence.changed_pages_count}
                    totalPages={confluence.synced_pages_count}
                  />
                )}
              </div>

              <div className="flex shrink-0 flex-wrap gap-2 justify-end">
                {confluence.synced_pages_count > 0 && !needsExtractionBanner && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1"
                    disabled={
                      isExtracting || extract.isPending || confluence.status === "disconnected"
                    }
                    onClick={handleExtract}
                  >
                    <SparklesIcon className={`size-3 ${isExtracting ? "animate-pulse" : ""}`} />
                    {isExtracting
                      ? "Extracting…"
                      : confluence.changed_pages_count > 0
                        ? `Extract (${confluence.changed_pages_count} changed)`
                        : "Extract processes"}
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1"
                  disabled={sync.isPending || confluence.status === "disconnected"}
                  onClick={() =>
                    sync.mutate(confluence.id, {
                      onSuccess: () => toast.success("Sync started"),
                      onError: () => toast.error("Failed to start sync"),
                    })
                  }
                >
                  <RefreshCwIcon className={`size-3 ${sync.isPending ? "animate-spin" : ""}`} />
                  Sync now
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1 text-destructive hover:text-destructive"
                  onClick={() => setDisconnectTarget(confluence)}
                >
                  <Trash2Icon className="size-3" />
                  Disconnect
                </Button>
              </div>
            </div>

            {needsExtractionBanner && (
              <ReadyForExtractionBanner
                changedPages={confluence.changed_pages_count}
                extractDisabled={extract.isPending || confluence.status === "disconnected"}
                extractPending={extract.isPending}
                onExtract={handleExtract}
              />
            )}

            {isExtracting && <ExtractionProgress job={latestJob} />}

            {latestJob && !isExtracting && latestJob.candidates_created > 0 && (
              <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                <SparklesIcon className="size-4 text-green-500" />
                Last extraction found <strong>
                  {latestJob.candidates_created} candidates
                </strong>.{" "}
                <Link
                  to={buildWorkspacePath(workspace, "/capture/candidates")}
                  className="text-primary hover:underline"
                >
                  Review candidates →
                </Link>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {!isLoading && connectors.length === 0 && (
        <EmptyState
          title="No connectors yet"
          description="Connect a documentation source to start syncing content."
        />
      )}

      <DeleteConfirmDialog
        open={disconnectTarget !== null}
        onOpenChange={(open) => !open && setDisconnectTarget(null)}
        entityName="Confluence"
        title="Disconnect Confluence?"
        description="This will stop syncing. Existing synced pages will remain but no new updates will be fetched."
        confirmLabel="Disconnect"
        requireTyping={false}
        pending={disconnect.isPending}
        onConfirm={() => {
          if (!disconnectTarget) return
          disconnect.mutate(disconnectTarget.id, {
            onSuccess: () => {
              toast.success("Confluence disconnected")
              setDisconnectTarget(null)
            },
            onError: () => toast.error("Failed to disconnect"),
          })
        }}
      />
    </div>
  )
}

function StatusBadge({ status }: { status: ConnectorCredential["status"] }) {
  if (status === "active") return <Badge>active</Badge>
  if (status === "expired") return <Badge variant="destructive">expired — reconnect needed</Badge>
  if (status === "error") return <Badge variant="destructive">error</Badge>
  return <Badge variant="secondary">{status}</Badge>
}

function SyncStatus({ job }: { job: ConnectorCredential["last_sync_job"] }) {
  if (!job) return <p className="text-sm text-muted-foreground">No sync run yet</p>

  const finishedAt = job.finished_at ? new Date(job.finished_at).toLocaleString() : null

  return (
    <p className="text-sm text-muted-foreground">
      Last sync:{" "}
      <span className={job.status === "failed" ? "text-destructive" : undefined}>{job.status}</span>
      {job.status === "completed" && ` · ${job.pages_updated} pages updated`}
      {finishedAt && ` · ${finishedAt}`}
    </p>
  )
}

function ExtractionStatus({
  job,
  changedPages,
  totalPages,
}: {
  job: import("@/types").ExtractionJob | undefined
  changedPages: number
  totalPages: number
}) {
  if (!job) {
    return (
      <p className="text-sm text-muted-foreground">
        {totalPages} pages synced ·{" "}
        <span className="text-foreground/90">run extraction to discover workflow candidates</span>
      </p>
    )
  }

  const finishedAt = job.finished_at ? new Date(job.finished_at).toLocaleString() : null

  return (
    <p className="text-sm text-muted-foreground">
      Last extraction:{" "}
      <span className={job.status === "failed" ? "text-destructive" : undefined}>{job.status}</span>
      {job.status === "completed" && ` · ${job.candidates_created} candidates`}
      {finishedAt && ` · ${finishedAt}`}
      {changedPages > 0 && job.status === "completed" && (
        <span className="ml-1 text-amber-600 dark:text-amber-400">
          ({changedPages} page{changedPages !== 1 ? "s" : ""} changed)
        </span>
      )}
    </p>
  )
}

function ReadyForExtractionBanner({
  changedPages,
  extractDisabled,
  extractPending,
  onExtract,
}: {
  changedPages: number
  extractDisabled: boolean
  extractPending: boolean
  onExtract: () => void
}) {
  const pageLabel = changedPages === 1 ? "1 page" : `${changedPages} pages`

  return (
    <div
      className="mt-4 flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
      role="status"
    >
      <div className="flex min-w-0 gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-warning/20 text-warning-foreground">
          <SparklesIcon className="size-4" aria-hidden />
        </div>
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium text-foreground">Capture ready — run extraction</p>
          <p className="text-sm text-muted-foreground">
            {pageLabel} with new or updated content. Extract processes to score pages and create
            candidates.
          </p>
        </div>
      </div>
      <Button
        size="sm"
        className="shrink-0 gap-1.5 self-start sm:self-center"
        disabled={extractDisabled}
        onClick={onExtract}
      >
        <SparklesIcon className={`size-3.5 ${extractPending ? "animate-pulse" : ""}`} />
        {extractPending ? "Starting…" : `Extract (${changedPages} changed)`}
      </Button>
    </div>
  )
}

function ExtractionProgress({ job }: { job: import("@/types").ExtractionJob | undefined }) {
  if (!job) return null

  let message = "Queued…"
  if (job.status === "running") {
    if (job.pages_scored === 0) {
      message = "Scoring pages…"
    } else if (job.pages_extracted === 0) {
      message = `Scored ${job.pages_scored} pages · extracting processes…`
    } else {
      message = `Extracted from ${job.pages_extracted} pages · found ${job.candidates_created} candidates so far…`
    }
  }

  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg border border-info/30 bg-info/10 px-3 py-2 text-sm text-info">
      <SparklesIcon className="size-4 shrink-0 animate-pulse" />
      {message}
    </div>
  )
}

function ConfluenceIcon() {
  return (
    <svg viewBox="0 0 32 32" className="size-5" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M1.5 23.3c-.4.6-.8 1.3-.8 1.8 0 .7.5 1.2 1.2 1.2h5.2c.4 0 .8-.2 1-.6C9.6 23.6 11 22 14 22c3 0 4.4 1.6 5.9 3.7.2.4.6.6 1 .6h5.2c.7 0 1.2-.5 1.2-1.2 0-.5-.4-1.2-.8-1.8C24.3 20.3 20.7 17 14 17c-6.7 0-10.3 3.3-12.5 6.3z"
        fill="#2684FF"
      />
      <path
        d="M26.5 8.7c.4-.6.8-1.3.8-1.8C27.3 6.2 26.8 5.7 26.1 5.7h-5.2c-.4 0-.8.2-1 .6C18.4 8.4 17 10 14 10c-3 0-4.4-1.6-5.9-3.7C7.9 5.9 7.5 5.7 7.1 5.7H1.9C1.2 5.7.7 6.2.7 6.9c0 .5.4 1.2.8 1.8C3.7 11.7 7.3 15 14 15c6.7 0 10.3-3.3 12.5-6.3z"
        fill="#2684FF"
      />
    </svg>
  )
}
