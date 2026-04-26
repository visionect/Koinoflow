import * as React from "react"

import {
  ArrowLeftIcon,
  ChevronDownIcon,
  FilePlusIcon,
  GlobeIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  UploadIcon,
  UsersIcon,
} from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useDeleteDepartment,
  useDepartment,
  useSkills,
  useUpdateDepartment,
  useWorkspaceMembers,
} from "@/api/client"
import { SkillCreateDialog } from "@/components/skills/SkillCreateDialog"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { useAuth } from "@/hooks/useAuth"
import { type SkillImportData, useSkillImport } from "@/hooks/use-skill-import"
import { buildWorkspacePath, formatRelativeDate, getDisplayName } from "@/lib/format"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
import { Skeleton } from "@/components/ui/skeleton"

export function DepartmentDetailPage() {
  const navigate = useNavigate()
  const { workspace, departmentId } = useParams<{ workspace: string; departmentId: string }>()
  const { isAdmin, isEditor } = useAuth()

  const departmentQuery = useDepartment(departmentId ?? "")
  const membersQuery = useWorkspaceMembers()
  const updateDepartment = useUpdateDepartment(departmentId ?? "")
  const deleteDepartment = useDeleteDepartment()

  const skillsQuery = useSkills(
    departmentQuery.data
      ? {
          department: departmentQuery.data.slug,
          limit: 100,
        }
      : undefined,
  )

  const [editOpen, setEditOpen] = React.useState(false)
  const [deleteOpen, setDeleteOpen] = React.useState(false)
  const [createProcessOpen, setCreateProcessOpen] = React.useState(false)
  const [importData, setImportData] = React.useState<SkillImportData | null>(null)

  const { fileInput, openFilePicker } = useSkillImport((data) => {
    setImportData(data)
    setCreateProcessOpen(true)
  })

  const [name, setName] = React.useState("")
  const [ownerId, setOwnerId] = React.useState("unassigned")

  React.useEffect(() => {
    if (departmentQuery.data) {
      setName(departmentQuery.data.name)
      setOwnerId(departmentQuery.data.owner?.id ?? "unassigned")
    }
  }, [departmentQuery.data])

  async function handleUpdateDepartment() {
    try {
      await updateDepartment.mutateAsync({
        name,
        owner_id: ownerId === "unassigned" ? null : ownerId,
      })
      toast.success("Department updated")
      setEditOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update department")
    }
  }

  async function handleDeleteDepartment() {
    if (!departmentQuery.data) {
      return
    }

    try {
      await deleteDepartment.mutateAsync(departmentQuery.data.id)
      toast.success("Department deleted")
      navigate(buildWorkspacePath(workspace, `/teams/${departmentQuery.data.team_slug}`), {
        replace: true,
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to delete department")
    }
  }

  if (departmentQuery.isError) {
    return (
      <ErrorState
        message={
          departmentQuery.error instanceof Error
            ? departmentQuery.error.message
            : "Unable to load department"
        }
        onRetry={() => void departmentQuery.refetch()}
      />
    )
  }

  if (!departmentQuery.data) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-8 w-40" />
        <div className="space-y-3">
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index}>
              <CardHeader>
                <Skeleton className="h-5 w-48" />
                <Skeleton className="mt-2 h-3 w-64" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <Button asChild size="sm" variant="ghost">
        <Link to={buildWorkspacePath(workspace, `/teams/${departmentQuery.data.team_slug}`)}>
          <ArrowLeftIcon />
          Back to {departmentQuery.data.team_name}
        </Link>
      </Button>

      <PageHeader
        title={departmentQuery.data.name}
        description={`Owner: ${getDisplayName(departmentQuery.data.owner)} • Team: ${departmentQuery.data.team_name}`}
        action={
          <div className="flex flex-wrap gap-2">
            {isEditor ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button>
                    <PlusIcon />
                    New skill
                    <ChevronDownIcon className="ml-1 size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => {
                      setImportData(null)
                      setCreateProcessOpen(true)
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
            ) : null}
            {isEditor ? (
              <Button variant="outline" onClick={() => setEditOpen(true)}>
                <PencilIcon />
                Edit
              </Button>
            ) : null}
            {isAdmin ? (
              <Button variant="outline" onClick={() => setDeleteOpen(true)}>
                <Trash2Icon />
                Delete
              </Button>
            ) : null}
          </div>
        }
      />

      {skillsQuery.isLoading || !skillsQuery.data ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <Card key={index}>
              <CardHeader className="space-y-3">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-3 w-full" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : skillsQuery.data?.items?.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {skillsQuery.data.items.map((skill) => (
            <Link key={skill.id} to={buildWorkspacePath(workspace, `/skills/${skill.slug}`)}>
              <Card className="h-full transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                <CardHeader className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <CardTitle>{skill.title}</CardTitle>
                      <CardDescription>
                        {skill.description || "No description yet."}
                      </CardDescription>
                    </div>
                    <StatusBadge status={skill.status} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">
                      {skill.current_version_number
                        ? `v${skill.current_version_number}`
                        : "Unpublished"}
                    </Badge>
                    <Badge variant="outline">Owner: {getDisplayName(skill.owner)}</Badge>
                    {skill.visibility === "team" && (
                      <Badge
                        variant="outline"
                        className="gap-1 text-blue-600 border-blue-300 dark:text-blue-400 dark:border-blue-700"
                      >
                        <UsersIcon className="size-3" />
                        Team-wide
                      </Badge>
                    )}
                    {skill.visibility === "workspace" && (
                      <Badge
                        variant="outline"
                        className="gap-1 text-green-600 border-green-300 dark:text-green-400 dark:border-green-700"
                      >
                        <GlobeIcon className="size-3" />
                        Workspace
                      </Badge>
                    )}
                  </div>
                  {skill.department_slug !== departmentQuery.data?.slug && (
                    <p className="text-xs">
                      From:{" "}
                      <span className="font-medium text-foreground">
                        {skill.team_name} / {skill.department_name}
                      </span>
                    </p>
                  )}
                  <p>
                    Last validated:{" "}
                    <span className="font-medium text-foreground">
                      {formatRelativeDate(skill.last_reviewed_at, "Not validated yet")}
                    </span>
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No skills in this department"
          description="Create the first skill to start documenting critical workflows."
          action={
            isEditor ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button>
                    <PlusIcon />
                    Create skill
                    <ChevronDownIcon className="ml-1 size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="center">
                  <DropdownMenuItem
                    onClick={() => {
                      setImportData(null)
                      setCreateProcessOpen(true)
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

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit department</DialogTitle>
            <DialogDescription>Update ownership and naming for this department.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="department-edit-name">Department name</Label>
              <Input
                id="department-edit-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
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
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!name.trim() || updateDepartment.isPending}
              onClick={() => void handleUpdateDepartment()}
            >
              {updateDepartment.isPending ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        entityName={departmentQuery.data.name}
        description="Deleting a department also removes every skill and version stored inside it."
        pending={deleteDepartment.isPending}
        onConfirm={handleDeleteDepartment}
      />

      {fileInput}

      <SkillCreateDialog
        open={createProcessOpen}
        onOpenChange={setCreateProcessOpen}
        workspaceSlug={workspace}
        defaultDepartmentId={departmentQuery.data.id}
        lockDepartment
        importData={importData}
        onImportConsumed={() => setImportData(null)}
      />
    </div>
  )
}
