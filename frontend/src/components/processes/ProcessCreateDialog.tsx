import * as React from "react"

import { ChevronDownIcon, ChevronRightIcon, FileTextIcon, FolderArchiveIcon } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { apiFetch, useCreateProcess, useDepartments, useWorkspaceMembers } from "@/api/client"
import type { SkillImportData } from "@/hooks/use-skill-import"
import { FileTreeBrowser } from "@/components/processes/FileTreeBrowser"
import { VisibilityScopeSelector } from "@/components/processes/VisibilityScopeSelector"
import { groupDepartmentsByTeam } from "@/lib/process-visibility"
import { buildWorkspacePath, getDisplayName, slugify } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { ProcessVersion, ProcessVisibility, VersionFile } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"

type ProcessCreateDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  workspaceSlug: string | undefined
  defaultDepartmentId?: string
  lockDepartment?: boolean
  importData?: SkillImportData | null
  onImportConsumed?: () => void
}

function ImportFrontmatterPreview({ data }: { data: SkillImportData }) {
  const [expanded, setExpanded] = React.useState(false)
  const { frontmatter } = data
  const otherKeys = Object.entries(frontmatter).filter(
    ([key]) => key !== "name" && key !== "description" && key !== "tags",
  )
  const hasExtra = otherKeys.length > 0 || frontmatter.tags.length > 0

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-lg border border-muted bg-muted/30 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50">
        <FileTextIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="flex-1 font-medium">Frontmatter detected</span>
        {hasExtra ? (
          <span className="text-xs text-muted-foreground">
            {frontmatter.tags.length + otherKeys.length} field
            {frontmatter.tags.length + otherKeys.length !== 1 ? "s" : ""}
          </span>
        ) : null}
        <ChevronRightIcon
          className={cn(
            "size-3.5 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 space-y-2 rounded-lg border bg-card p-3 text-xs">
          <div>
            <p className="text-muted-foreground">name</p>
            <code className="font-mono">{frontmatter.name || "—"}</code>
          </div>
          {frontmatter.tags.length > 0 ? (
            <div>
              <p className="text-muted-foreground">tags</p>
              <div className="flex flex-wrap gap-1">
                {frontmatter.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-[10px]">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
          {otherKeys.length > 0 ? (
            <div>
              <p className="text-muted-foreground">other keys (preserved on save)</p>
              <ul className="space-y-0.5 font-mono">
                {otherKeys.map(([key, value]) => (
                  <li key={key} className="flex items-start gap-2">
                    <span className="shrink-0 text-muted-foreground">{key}:</span>
                    <span className="min-w-0 break-words">
                      {Array.isArray(value)
                        ? (value as unknown[]).join(", ")
                        : typeof value === "object" && value !== null
                          ? JSON.stringify(value)
                          : String(value)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function ImportFilePreview({
  files,
}: {
  files: {
    path: string
    content?: string | null
    content_base64?: string | null
    file_type: string
    mime_type?: string | null
    encoding?: string | null
    size_bytes?: number
  }[]
}) {
  const [expanded, setExpanded] = React.useState(false)

  const previewFiles: VersionFile[] = files.map((f, i) => ({
    id: `preview-${i}`,
    path: f.path,
    file_type: f.file_type,
    mime_type: f.mime_type ?? "application/octet-stream",
    encoding: f.encoding ?? (f.content_base64 ? "base64" : "utf-8"),
    size_bytes:
      f.size_bytes ?? (f.content !== undefined && f.content !== null ? new Blob([f.content]).size : 0),
  }))

  const totalSize = previewFiles.reduce((sum, f) => sum + f.size_bytes, 0)
  const totalLabel = totalSize < 1024 ? `${totalSize} B` : `${(totalSize / 1024).toFixed(1)} KB`

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-lg border border-muted bg-muted/30 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50">
        <FolderArchiveIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="flex-1 font-medium">
          {files.length} support file{files.length !== 1 ? "s" : ""}
        </span>
        <span className="text-xs text-muted-foreground">{totalLabel}</span>
        <ChevronRightIcon
          className={cn(
            "size-3.5 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border bg-card px-2 py-1.5">
          <FileTreeBrowser files={previewFiles} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function ProcessCreateDialog({
  open,
  onOpenChange,
  workspaceSlug,
  defaultDepartmentId,
  lockDepartment = false,
  importData,
  onImportConsumed,
}: ProcessCreateDialogProps) {
  const navigate = useNavigate()
  const createProcess = useCreateProcess()
  const departmentsQuery = useDepartments()
  const membersQuery = useWorkspaceMembers()

  const [departmentId, setDepartmentId] = React.useState(defaultDepartmentId ?? "")
  const [selectedTeamSlug, setSelectedTeamSlug] = React.useState("")
  const [visibility, setVisibility] = React.useState<ProcessVisibility>("department")
  const [sharedWithIds, setSharedWithIds] = React.useState<Set<string>>(new Set())
  const [title, setTitle] = React.useState("")
  const [slug, setSlug] = React.useState("")
  const [slugTouched, setSlugTouched] = React.useState(false)
  const [description, setDescription] = React.useState("")
  const [ownerId, setOwnerId] = React.useState<string>("unassigned")
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  const isImport = Boolean(importData)

  const selectedDepartment = React.useMemo(
    () => departmentsQuery.data?.find((d) => d.id === departmentId),
    [departmentsQuery.data, departmentId],
  )

  const teams = React.useMemo(
    () => groupDepartmentsByTeam(departmentsQuery.data ?? []),
    [departmentsQuery.data],
  )

  const selectedTeam = React.useMemo(
    () => teams.find((t) => t.teamSlug === selectedTeamSlug),
    [teams, selectedTeamSlug],
  )

  React.useEffect(() => {
    if (open) {
      setDepartmentId(defaultDepartmentId ?? "")
      setSelectedTeamSlug("")
      setVisibility("department")
      setSharedWithIds(new Set())
    }
  }, [defaultDepartmentId, open])

  React.useEffect(() => {
    if (open && importData) {
      setTitle(importData.title)
      setSlug(slugify(importData.title))
      setSlugTouched(false)
      setDescription(importData.description)
      setOwnerId("unassigned")
    }
  }, [open, importData])

  React.useEffect(() => {
    if (!slugTouched) {
      setSlug(slugify(title))
    }
  }, [slugTouched, title])

  function resetForm() {
    setTitle("")
    setSlug("")
    setSlugTouched(false)
    setDescription("")
    setOwnerId("unassigned")
    setVisibility("department")
    setSelectedTeamSlug("")
    setSharedWithIds(new Set())
    onImportConsumed?.()
  }

  async function handleCreateProcess() {
    setIsSubmitting(true)
    try {
      const process = await createProcess.mutateAsync({
        department_id:
          visibility === "team"
            ? (selectedTeam?.departments[0]?.id ?? "")
            : visibility === "workspace"
              ? (defaultDepartmentId ?? departmentsQuery.data?.[0]?.id ?? "")
              : departmentId,
        title,
        slug,
        description,
        owner_id: ownerId === "unassigned" ? null : ownerId,
        visibility,
        shared_with_ids: [...sharedWithIds],
      })

      if (importData?.contentMd) {
        await apiFetch<ProcessVersion>(`/processes/${process.slug}/versions`, {
          method: "POST",
          body: JSON.stringify({
            content_md: importData.contentMd,
            frontmatter_yaml: importData.frontmatterYaml ?? "",
            change_summary: "Imported from .skill file",
            files: importData.supportFiles?.length ? importData.supportFiles : undefined,
          }),
        })
      }

      toast.success(isImport ? "Process imported successfully" : "Process created")
      onOpenChange(false)
      resetForm()
      navigate(buildWorkspacePath(workspaceSlug, `/processes/${process.slug}`))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create process")
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleClose(nextOpen: boolean) {
    if (!nextOpen) {
      resetForm()
    }
    onOpenChange(nextOpen)
  }

  const pending = createProcess.isPending || isSubmitting

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isImport ? "Import process" : "Create process"}</DialogTitle>
          <DialogDescription>
            {isImport
              ? "Review the pre-filled details from the imported file, then confirm to create the process."
              : "Capture the metadata first, then jump into the editor to write the operational runbook."}
          </DialogDescription>
        </DialogHeader>

        {isImport ? (
          <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
            <FileTextIcon className="size-4 shrink-0" aria-hidden />
            Pre-filled from imported file. Content will be saved as the first version.
          </div>
        ) : null}

        {isImport && importData ? <ImportFrontmatterPreview data={importData} /> : null}

        {isImport && importData?.supportFiles && importData.supportFiles.length > 0 ? (
          <ImportFilePreview files={importData.supportFiles} />
        ) : null}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="process-title">Title</Label>
            <Input
              id="process-title"
              placeholder="Deploy to production"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="process-description">Description</Label>
            <Textarea
              id="process-description"
              placeholder="Short summary shown in the process list"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          {!lockDepartment ? (
            <div className="space-y-2">
              <Label htmlFor="process-department">Department</Label>
              <Select
                value={visibility === "department" ? departmentId : ""}
                onValueChange={(next) => {
                  setVisibility("department")
                  setSelectedTeamSlug("")
                  setDepartmentId(next)
                }}
              >
                <SelectTrigger id="process-department">
                  <SelectValue placeholder="Select a department" />
                </SelectTrigger>
                <SelectContent>
                  {departmentsQuery.data?.map((department) => (
                    <SelectItem key={department.id} value={department.id}>
                      {department.team_name} / {department.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Who owns this process. Use &ldquo;Sharing &amp; visibility&rdquo; below to also
                share it with a team or the whole workspace.
              </p>
            </div>
          ) : selectedDepartment ? (
            <p className="text-xs text-muted-foreground">
              Creating in{" "}
              <span className="font-medium text-foreground">
                {selectedDepartment.team_name} / {selectedDepartment.name}
              </span>
              .
            </p>
          ) : null}

          <div className="space-y-2">
            <Label>Owner</Label>
            <Select value={ownerId} onValueChange={setOwnerId}>
              <SelectTrigger>
                <SelectValue placeholder="Select an owner" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unassigned">Unassigned</SelectItem>
                {membersQuery.data?.map((member) => (
                  <SelectItem key={member.id} value={member.id}>
                    {getDisplayName(member)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Collapsible className="rounded-lg border bg-muted/30">
            <CollapsibleTrigger className="group flex w-full items-center justify-between gap-2 px-4 py-3 text-left">
              <div className="min-w-0">
                <p className="text-sm font-medium">Sharing &amp; visibility</p>
                <p className="truncate text-xs text-muted-foreground">
                  {visibility === "workspace"
                    ? "Visible to the whole workspace"
                    : visibility === "team"
                      ? `Shared with the ${selectedTeam?.teamName ?? "selected"} team`
                      : sharedWithIds.size > 0
                        ? `Department + ${sharedWithIds.size} more department${sharedWithIds.size !== 1 ? "s" : ""}`
                        : "Department only (default)"}
                </p>
              </div>
              <ChevronDownIcon
                className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                aria-hidden
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="space-y-4 border-t px-4 py-4">
                <VisibilityScopeSelector
                  ownerDepartmentId={departmentId}
                  ownerTeamSlug={
                    visibility === "team" ? selectedTeamSlug : (selectedDepartment?.team_slug ?? "")
                  }
                  ownerTeamName={
                    visibility === "team" ? selectedTeam?.teamName : selectedDepartment?.team_name
                  }
                  visibility={visibility}
                  onVisibilityChange={(next) => {
                    setVisibility(next)
                    if (next === "team") setDepartmentId("")
                    else setSelectedTeamSlug("")
                  }}
                  sharedWithIds={sharedWithIds}
                  onSharedWithIdsChange={setSharedWithIds}
                  allDepartments={departmentsQuery.data ?? []}
                  excludeTeamSlug={selectedTeamSlug}
                />

                {visibility === "team" ? (
                  <div className="space-y-2">
                    <Label>Team</Label>
                    <Select value={selectedTeamSlug} onValueChange={setSelectedTeamSlug}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a team" />
                      </SelectTrigger>
                      <SelectContent>
                        {teams.map((team) => (
                          <SelectItem key={team.teamSlug} value={team.teamSlug}>
                            {team.teamName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}
              </div>
            </CollapsibleContent>
          </Collapsible>

          <Collapsible className="rounded-lg border bg-muted/30">
            <CollapsibleTrigger className="group flex w-full items-center justify-between gap-2 px-4 py-3 text-left">
              <div className="min-w-0">
                <p className="text-sm font-medium">Advanced</p>
                <p className="truncate text-xs text-muted-foreground">
                  Slug: <code className="font-mono">{slug || slugify(title) || "…"}</code>
                </p>
              </div>
              <ChevronDownIcon
                className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                aria-hidden
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="space-y-2 border-t px-4 py-4">
                <Label htmlFor="process-slug">Slug</Label>
                <Input
                  id="process-slug"
                  placeholder="deploy-to-production"
                  value={slug}
                  onChange={(event) => {
                    setSlugTouched(true)
                    setSlug(slugify(event.target.value))
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  Short ID used in URLs and the skill&rsquo;s <code>name</code> field. Defaults to a
                  slugified title.
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button
            disabled={
              (visibility === "department" && !departmentId) ||
              (visibility === "team" && !selectedTeamSlug) ||
              (visibility === "workspace" &&
                !defaultDepartmentId &&
                !departmentsQuery.data?.length) ||
              !title.trim() ||
              !slug.trim() ||
              pending
            }
            onClick={() => void handleCreateProcess()}
          >
            {pending ? "Creating..." : isImport ? "Import and view" : "Create and edit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
