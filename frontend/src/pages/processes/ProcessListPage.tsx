import * as React from "react"

import {
  AlertTriangleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FilePlusIcon,
  PlusIcon,
  SearchIcon,
  UploadIcon,
} from "lucide-react"
import { Link, useParams, useSearchParams } from "react-router-dom"

import { useDepartments, useProcesses, useTeams } from "@/api/client"
import { DiscoveryEmbeddingStatusBadge } from "@/components/processes/DiscoveryEmbeddingStatusBadge"
import { ProcessCreateDialog } from "@/components/processes/ProcessCreateDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { useAuth } from "@/hooks/useAuth"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { type SkillImportData, useSkillImport } from "@/hooks/use-skill-import"
import { buildWorkspacePath } from "@/lib/format"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const PAGE_SIZE = 20

export function ProcessListPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isEditor } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [createOpen, setCreateOpen] = React.useState(false)
  const [importData, setImportData] = React.useState<SkillImportData | null>(null)

  const { fileInput, openFilePicker } = useSkillImport((data) => {
    setImportData(data)
    setCreateOpen(true)
  })

  const team = searchParams.get("team") ?? ""
  const department = searchParams.get("department") ?? ""
  const status = searchParams.get("status") ?? ""
  const search = searchParams.get("search") ?? ""
  const page = Number(searchParams.get("page") ?? "1")
  const safePage = Number.isNaN(page) || page < 1 ? 1 : page

  const debouncedSearch = useDebouncedValue(search, 300)

  const teamsQuery = useTeams()
  const departmentsQuery = useDepartments(team || undefined)
  const processesQuery = useProcesses({
    team: team || undefined,
    department: department || undefined,
    status: status === "draft" || status === "published" ? status : undefined,
    search: debouncedSearch || undefined,
    limit: PAGE_SIZE,
    offset: (safePage - 1) * PAGE_SIZE,
  })

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)

    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }

    if (key !== "page") {
      next.set("page", "1")
    }

    setSearchParams(next)
  }

  const totalPages = Math.max(1, Math.ceil((processesQuery.data?.count ?? 0) / PAGE_SIZE))

  return (
    <div className="space-y-8">
      <PageHeader
        title="All processes"
        description="Search, filter, and manage the operating procedures available across the workspace."
        action={
          isEditor ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button>
                  <PlusIcon />
                  New process
                  <ChevronDownIcon className="ml-1 size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() => {
                    setImportData(null)
                    setCreateOpen(true)
                  }}
                >
                  <FilePlusIcon className="mr-2 size-4" />
                  Create from scratch
                </DropdownMenuItem>
                <DropdownMenuItem onClick={openFilePicker}>
                  <UploadIcon className="mr-2 size-4" />
                  Import .skill file
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null
        }
      />

      <div className="grid gap-3 rounded-2xl border bg-card p-4 md:grid-cols-2 xl:grid-cols-4">
        <Select
          value={team}
          onValueChange={(value) => setParam("team", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by team" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All teams</SelectItem>
            {teamsQuery.data?.map((teamItem) => (
              <SelectItem key={teamItem.id} value={teamItem.slug}>
                {teamItem.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={department}
          onValueChange={(value) => setParam("department", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by department" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All departments</SelectItem>
            {departmentsQuery.data?.map((departmentItem) => (
              <SelectItem key={departmentItem.id} value={departmentItem.slug}>
                {departmentItem.team_name} / {departmentItem.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={status}
          onValueChange={(value) => setParam("status", value === "all" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="published">Published</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
          </SelectContent>
        </Select>

        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search processes..."
            value={search}
            onChange={(event) => setParam("search", event.target.value)}
          />
        </div>
      </div>

      {processesQuery.isError ? (
        <ErrorState
          message={
            processesQuery.error instanceof Error
              ? processesQuery.error.message
              : "Unable to load processes"
          }
          onRetry={() => void processesQuery.refetch()}
        />
      ) : processesQuery.isLoading || !processesQuery.data ? (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[34%]">Title</TableHead>
                <TableHead className="w-[20%]">Team / Department</TableHead>
                <TableHead className="w-[12%]">Status</TableHead>
                <TableHead className="w-[12%]">Review</TableHead>
                <TableHead className="w-[13%]">Discovery</TableHead>
                <TableHead className="w-[9%]">Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Array.from({ length: 5 }).map((_, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-2/3" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-16" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-20" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-24" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-10" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : processesQuery.data?.items?.length ? (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-2xl border bg-card">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[34%]">Title</TableHead>
                  <TableHead className="w-[20%]">Team / Department</TableHead>
                  <TableHead className="w-[12%]">Status</TableHead>
                  <TableHead className="w-[12%]">Review</TableHead>
                  <TableHead className="w-[13%]">Discovery</TableHead>
                  <TableHead className="w-[9%]">Version</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {processesQuery.data.items.map((process) => {
                  const rowHref = buildWorkspacePath(workspace, `/processes/${process.slug}`)
                  return (
                    <TableRow
                      key={process.id}
                      className="group cursor-pointer transition-colors hover:bg-muted/40"
                    >
                      <TableCell className="relative p-0">
                        <Link
                          to={rowHref}
                          className="flex min-w-0 items-center gap-2 px-4 py-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <div className="min-w-0">
                            <span className="block truncate font-medium text-foreground">
                              {process.title}
                            </span>
                            <p className="mt-1 truncate text-xs text-muted-foreground">
                              {process.description || "No description yet"}
                            </p>
                          </div>
                        </Link>
                      </TableCell>
                      <TableCell className="truncate text-sm text-muted-foreground">
                        {process.team_name} / {process.department_name}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={process.status} />
                      </TableCell>
                      <TableCell>
                        {process.needs_audit ? (
                          <TooltipProvider delayDuration={200}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge
                                  variant="outline"
                                  className="gap-1 border-destructive/40 text-destructive"
                                >
                                  <AlertTriangleIcon className="size-3" aria-hidden />
                                  Needs validation
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>
                                  The owner hasn&rsquo;t re-confirmed this process is still
                                  accurate.
                                </p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : (
                          <span className="text-xs text-muted-foreground">&mdash;</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <DiscoveryEmbeddingStatusBadge
                          status={process.discovery_embedding_status}
                          compact
                        />
                      </TableCell>
                      <TableCell className="truncate text-sm text-muted-foreground">
                        {process.current_version_number
                          ? `v${process.current_version_number}`
                          : "Unpublished"}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {(safePage - 1) * PAGE_SIZE + 1} to{" "}
              {Math.min(safePage * PAGE_SIZE, processesQuery.data.count)} of{" "}
              {processesQuery.data.count}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={safePage <= 1}
                onClick={() => setParam("page", String(safePage - 1))}
              >
                <ChevronLeftIcon />
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={safePage >= totalPages}
                onClick={() => setParam("page", String(safePage + 1))}
              >
                Next
                <ChevronRightIcon />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState
          title="No processes found"
          description="Adjust your filters or create a new process to start building a reusable operations library."
          action={
            isEditor ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button>
                    <PlusIcon />
                    New process
                    <ChevronDownIcon className="ml-1 size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="center">
                  <DropdownMenuItem
                    onClick={() => {
                      setImportData(null)
                      setCreateOpen(true)
                    }}
                  >
                    <FilePlusIcon className="mr-2 size-4" />
                    Create from scratch
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={openFilePicker}>
                    <UploadIcon className="mr-2 size-4" />
                    Import .skill file
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : undefined
          }
        />
      )}

      {fileInput}

      <ProcessCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        workspaceSlug={workspace}
        importData={importData}
        onImportConsumed={() => setImportData(null)}
      />
    </div>
  )
}
